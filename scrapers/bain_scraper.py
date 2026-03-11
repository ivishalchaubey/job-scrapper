import hashlib
import html
import json
import re
import subprocess
from urllib.parse import urlencode

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

try:
    import requests
except ImportError:
    requests = None

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE
from scrapers.csv_url_resolver import get_company_url

logger = setup_logger('bain_scraper')


class BainScraper:
    def __init__(self):
        self.company_name = "Bain & Company"
        default_url = "https://www.bain.com/careers/find-a-role/?filters=offices(275,276,274)|"
        self.url = get_company_url(self.company_name, default_url)
        # Internal API endpoint (requires Cloudflare bypass via cloudscraper)
        self._api_url = 'https://www.bain.com/en/api/jobsearch/keyword/get'
        self._job_detail_base = 'https://www.bain.com/careers/find-a-role/position/'
        # Office filter IDs: 275=Mumbai, 276=New Delhi, 274=Bengaluru
        self._office_ids = '275,276,274'
        self._ignore_location_tokens = {
            'americas | apac | emea',
            'americas|apac|emea',
        }

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Bain India jobs via internal API."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping via API")

            scraper = None
            if cloudscraper is not None:
                scraper = cloudscraper.create_scraper(
                    browser={'browser': 'chrome', 'platform': 'darwin', 'mobile': False}
                )
            elif requests is not None:
                scraper = requests.Session()
                scraper.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                })
            else:
                logger.warning("Neither cloudscraper nor requests available; using curl fallback only")

            # Now query the job search API
            page = 1
            results_per_page = 10

            while page <= max_pages:
                start_offset = (page - 1) * results_per_page
                params = {
                    'keyword': '',
                    'start': start_offset,
                    'resultsPerPage': results_per_page,
                    'offices': self._office_ids,
                }

                try:
                    data = self._fetch_api_page(params=params, scraper=scraper)
                    if not data:
                        logger.warning(f"API returned empty/unreadable data on page {page}")
                        break

                    if not isinstance(data, dict):
                        logger.error(f"Unexpected API response type: {type(data).__name__}")
                        break

                    results = data.get('results', [])
                    total_results = data.get('totalResults', 0)

                    if page == 1:
                        logger.info(
                            f"API reports {total_results} total results, got {len(results)} on first page (start={start_offset})"
                        )

                    if not results:
                        logger.info(f"No results on page {page}, stopping")
                        break

                    new_count = 0
                    for job_raw in results:
                        job_data = self._parse_job(job_raw)
                        if job_data and job_data['external_id'] not in seen_ids:
                            all_jobs.append(job_data)
                            seen_ids.add(job_data['external_id'])
                            new_count += 1

                    logger.info(
                        f"Page {page} (start={start_offset}): {len(results)} results, {new_count} new. Total: {len(all_jobs)}"
                    )

                    # If no new jobs were found, pagination isn't working or we got all results
                    if new_count == 0:
                        logger.info("No new jobs found, stopping pagination")
                        break

                    page += 1

                except Exception as e:
                    logger.error(f"API request failed on page {page}: {str(e)}")
                    break

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs

    def _parse_job(self, job_raw):
        """Parse a single job entry from the API response."""
        try:
            job_id = str(job_raw.get('JobId', ''))
            title = job_raw.get('JobTitle', '').strip()

            if not title:
                return None

            # Build job URL
            link = job_raw.get('Link', '')
            if link:
                if link.startswith('/'):
                    apply_url = f'https://www.bain.com{link}'
                elif link.startswith('http'):
                    apply_url = link
                else:
                    apply_url = f'https://www.bain.com/{link}'
            elif job_id:
                apply_url = f'{self._job_detail_base}?jobid={job_id}'
            else:
                apply_url = self.url

            # Parse locations - API returns a list of office names
            locations_raw = job_raw.get('Location', [])
            location_str = ''
            if isinstance(locations_raw, list):
                cleaned_locations = []
                for loc in locations_raw:
                    clean_loc = str(loc).strip()
                    if not clean_loc:
                        continue
                    if clean_loc.lower() in self._ignore_location_tokens:
                        continue
                    if clean_loc not in cleaned_locations:
                        cleaned_locations.append(clean_loc)
                location_str = ', '.join(cleaned_locations[:10])
            elif isinstance(locations_raw, str):
                location_str = locations_raw.strip()

            # Parse employment type
            employment_type = ''
            emp_type_raw = job_raw.get('EmployeeType', '')
            if isinstance(emp_type_raw, str):
                employment_type = emp_type_raw.strip()

            # Parse categories/department
            department = ''
            categories = job_raw.get('Categories', [])
            if isinstance(categories, list) and categories:
                department = ', '.join(str(c).strip() for c in categories if c)
            elif isinstance(categories, str):
                department = categories.strip()

            # Clean description (strip HTML)
            description = job_raw.get('JobDescription', '')
            if description:
                description = re.sub(r'<[^>]+>', '', description).strip()
                description = re.sub(r'\s+', ' ', description)
                description = description[:15000]

            # Parse location
            location_parts = self.parse_location(location_str)

            job_data = {
                'external_id': self.generate_external_id(job_id if job_id else title, self.company_name),
                'job_id': job_id,
                'company_name': self.company_name,
                'title': title,
                'apply_url': apply_url,
                'location': location_str,
                'employment_type': employment_type,
                'department': department,
                'description': description,
                'posted_date': '',
                'city': location_parts['city'],
                'state': location_parts['state'],
                'country': location_parts['country'],
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            if apply_url and apply_url != self.url:
                try:
                    details = self._fetch_job_details(apply_url)
                    if details:
                        detail_location = (details.get('location') or '').lower()
                        if any(token in detail_location for token in self._ignore_location_tokens):
                            details.pop('location', None)
                            details.pop('city', None)
                            details.pop('state', None)
                            details.pop('country', None)
                        job_data.update(details)
                except Exception as e:
                    logger.warning(f"Could not fetch Bain detail page for job {job_id or title}: {str(e)}")

            return job_data

        except Exception as e:
            logger.error(f"Error parsing job: {str(e)}")
            return None

    def parse_location(self, location_str):
        """Parse location string into city, state, country."""
        result = {
            'city': '',
            'state': '',
            'country': ''
        }

        if not location_str:
            return result

        # Clean up location string
        location_str = location_str.strip()
        parts = [p.strip() for p in location_str.split(',') if p.strip()]
        if len(parts) > 3:
            return result
        if parts:
            result['city'] = parts[0]
        if len(parts) >= 2:
            result['state'] = parts[1]
        if len(parts) >= 3:
            result['country'] = parts[-1]
        if not result['country'] and re.search(r'\b(India|IND)\b', location_str, flags=re.IGNORECASE):
            result['country'] = 'India'

        return result

    def _fetch_job_details(self, job_url):
        """Fetch full details from Bain job detail page."""
        details = {}
        try:
            page = self._fetch_text(url=job_url)
            if not page:
                return details

            script_matches = re.findall(
                r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                page,
                flags=re.IGNORECASE | re.DOTALL
            )
            for script_content in script_matches:
                try:
                    payload = json.loads(script_content.strip())
                except Exception:
                    continue

                blocks = payload if isinstance(payload, list) else [payload]
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    raw_desc = block.get('description')
                    if raw_desc and not details.get('description'):
                        details['description'] = self._clean_text(raw_desc)
                    job_loc = block.get('jobLocation')
                    if job_loc and not details.get('location'):
                        loc = self._extract_ld_json_location(job_loc)
                        if loc:
                            details['location'] = loc
                            details.update(self.parse_location(loc))
                    if details.get('description') and details.get('location'):
                        break

            if not details.get('description'):
                fallback_patterns = [
                    r'<div[^>]+class=["\'][^"\']*job-description[^"\']*["\'][^>]*>(.*?)</div>',
                    r'<section[^>]+class=["\'][^"\']*job-description[^"\']*["\'][^>]*>(.*?)</section>',
                ]
                for pattern in fallback_patterns:
                    match = re.search(pattern, page, flags=re.IGNORECASE | re.DOTALL)
                    if match:
                        cleaned = self._clean_text(match.group(1))
                        if cleaned:
                            details['description'] = cleaned
                            break

        except Exception as e:
            logger.debug(f"Error in Bain detail page scrape: {str(e)}")

        return details

    def _fetch_api_page(self, params, scraper=None):
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': self.url,
            'User-Agent': 'Mozilla/5.0',
        }

        if scraper is not None:
            try:
                response = scraper.get(
                    self._api_url,
                    params=params,
                    headers=headers,
                    timeout=SCRAPE_TIMEOUT
                )
                if response.status_code == 200:
                    return response.json()
                logger.warning(f"Bain API non-200 via python client: {response.status_code}; trying curl fallback")
            except Exception as e:
                logger.warning(f"Bain API python client failed: {str(e)}; trying curl fallback")

        text = self._fetch_text(url=self._api_url, headers=headers, params=params)
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Bain API curl JSON parse failed: {str(e)}")
            return None

    def _fetch_text(self, url, headers=None, params=None):
        headers = headers or {}

        if requests is not None:
            try:
                response = requests.get(url, headers=headers, params=params, timeout=SCRAPE_TIMEOUT)
                if response.status_code == 200:
                    return response.text
                logger.debug(f"requests.get returned {response.status_code} for {url}; trying curl")
            except Exception as e:
                logger.debug(f"requests.get failed for {url}: {str(e)}")

        curl_cmd = ['curl', '-s']
        for key, value in headers.items():
            curl_cmd.extend(['-H', f'{key}: {value}'])

        final_url = url
        if params:
            query = urlencode(params, doseq=True)
            separator = '&' if '?' in url else '?'
            final_url = f"{url}{separator}{query}"

        curl_cmd.append(final_url)

        try:
            proc = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=SCRAPE_TIMEOUT)
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
            logger.debug(f"curl failed for {url}: rc={proc.returncode}, stderr={proc.stderr[:300]}")
        except Exception as e:
            logger.debug(f"curl execution failed for {url}: {str(e)}")

        return ''

    def _extract_ld_json_location(self, job_location):
        locations = []
        location_entries = job_location if isinstance(job_location, list) else [job_location]
        for entry in location_entries:
            if not isinstance(entry, dict):
                continue
            address = entry.get('address', {})
            if isinstance(address, dict):
                city = (address.get('addressLocality') or '').strip()
                state = (address.get('addressRegion') or '').strip()
                country = (address.get('addressCountry') or '').strip()
                pieces = [p for p in [city, state, country] if p]
                if pieces:
                    locations.append(', '.join(pieces))
        return ', '.join(locations)

    def _clean_text(self, value):
        text = value if isinstance(value, str) else str(value)
        text = html.unescape(text)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<li[^>]*>', '\n- ', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'[ \t\r\f\v]+', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        return text.strip()[:15000]


if __name__ == "__main__":
    scraper = BainScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job.get('employment_type', '')}")

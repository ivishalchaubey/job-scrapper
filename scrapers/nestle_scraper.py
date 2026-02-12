import requests
import hashlib
import re
from pathlib import Path


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('nestle_scraper')


class NestleScraper:
    def __init__(self):
        self.company_name = 'Nestle'
        # Original URL (Cloudflare-blocked, kept for reference)
        self.url = 'https://www.nestle.in/jobs/search-jobs?keyword=&country=IN'
        # SuccessFactors API URL that bypasses Cloudflare
        self._api_base = 'https://jobdetails.nestle.com'
        self._search_url = f'{self._api_base}/job/search'
        self._results_per_page = 10

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _get_headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Nestle India jobs via SuccessFactors HTML API (bypasses Cloudflare)."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping via SuccessFactors API")
            headers = self._get_headers()

            # First request to determine total count
            first_url = f'{self._search_url}?q=&locationsearch=India&startrow=0'
            response = requests.get(first_url, headers=headers, timeout=SCRAPE_TIMEOUT)
            if response.status_code != 200:
                logger.error(f"Initial request failed with status {response.status_code}")
                return all_jobs

            # Extract total count - SuccessFactors uses "of X" pattern
            total_jobs = 0
            # Try "X - Y of Z" pattern first
            total_match = re.search(r'(\d+)\s*[-\u2013]\s*(\d+)\s+of\s+(\d+)', response.text)
            if total_match:
                total_jobs = int(total_match.group(3))
            else:
                # Fallback: find all "of N" patterns and take the largest number
                of_matches = re.findall(r'of\s+(\d+)', response.text)
                if of_matches:
                    total_jobs = max(int(m) for m in of_matches)

            if total_jobs > 0:
                logger.info(f"Total India jobs available: {total_jobs}")
            else:
                logger.warning("Could not determine total job count, will scrape available pages")

            # Calculate max pages needed
            max_startrow = min(total_jobs, max_pages * self._results_per_page) if total_jobs > 0 else max_pages * self._results_per_page

            # Scrape page by page
            page_num = 0
            startrow = 0
            while startrow < max_startrow:
                page_num += 1
                logger.info(f"Scraping page {page_num} (startrow={startrow})")

                if startrow == 0:
                    page_text = response.text
                else:
                    page_url = f'{self._search_url}?q=&locationsearch=India&startrow={startrow}'
                    try:
                        page_response = requests.get(page_url, headers=headers, timeout=SCRAPE_TIMEOUT)
                        if page_response.status_code != 200:
                            logger.warning(f"Page {page_num} returned status {page_response.status_code}")
                            break
                        page_text = page_response.text
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Request failed for page {page_num}: {str(e)}")
                        break

                # Parse jobs from HTML
                page_jobs = self._parse_jobs_from_html(page_text)

                if not page_jobs:
                    logger.info(f"No jobs found on page {page_num}, stopping")
                    break

                new_count = 0
                for job in page_jobs:
                    if job['external_id'] not in seen_ids:
                        all_jobs.append(job)
                        seen_ids.add(job['external_id'])
                        new_count += 1

                logger.info(f"Page {page_num}: {len(page_jobs)} jobs parsed, {new_count} new. Total: {len(all_jobs)}")

                if new_count == 0:
                    logger.info("No new jobs found, stopping pagination")
                    break

                startrow += self._results_per_page

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs

    def _parse_jobs_from_html(self, html):
        """Parse job listings from SuccessFactors HTML response."""
        jobs = []

        # Extract data rows - SuccessFactors uses <tr> with class containing "data-row"
        rows = re.findall(r'<tr[^>]*class="[^"]*data-row[^"]*"[^>]*>(.*?)</tr>', html, re.DOTALL)

        for idx, row in enumerate(rows, 1):
            try:
                # Extract title and URL from jobTitle cell
                title_match = re.search(
                    r'class="[^"]*jobTitle[^"]*"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                    row, re.DOTALL
                )
                if not title_match:
                    continue

                href = title_match.group(1)
                title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()
                if not title:
                    continue

                # Clean up href
                href = href.replace('&amp;', '&')
                if href.startswith('/'):
                    apply_url = f'{self._api_base}{href}'
                elif href.startswith('http'):
                    apply_url = href
                else:
                    apply_url = f'{self._api_base}/{href}'

                # Extract job ID from URL (format: /job/City-Title/JOBID/)
                job_id = ''
                id_match = re.search(r'/(\d{5,})/', href)
                if id_match:
                    job_id = id_match.group(1)
                if not job_id:
                    job_id = f"nestle_{hashlib.md5(href.encode()).hexdigest()[:10]}"

                # Extract location from jobLocation cell
                location = ''
                loc_match = re.search(
                    r'class="[^"]*jobLocation[^"]*"[^>]*>(.*?)</(?:td|div)',
                    row, re.DOTALL
                )
                if loc_match:
                    location = re.sub(r'<[^>]+>', '', loc_match.group(1)).strip()
                    # Clean up extra whitespace and distance info
                    location = re.sub(r'\s+', ' ', location)
                    location = re.sub(r'\d+\.\d+\s*mi', '', location).strip()

                # Extract department/function from jobFacility cell
                department = ''
                dept_match = re.search(
                    r'class="[^"]*jobFacility[^"]*"[^>]*>(.*?)</(?:td|div)',
                    row, re.DOTALL
                )
                if dept_match:
                    department = re.sub(r'<[^>]+>', '', dept_match.group(1)).strip()
                    department = re.sub(r'\s+', ' ', department)

                # Extract date from jobDate cell
                posted_date = ''
                date_match = re.search(
                    r'class="[^"]*jobDate[^"]*"[^>]*>(.*?)</(?:td|div)',
                    row, re.DOTALL
                )
                if date_match:
                    posted_date = re.sub(r'<[^>]+>', '', date_match.group(1)).strip()
                    posted_date = re.sub(r'\s+', ' ', posted_date)
                    # Clean up distance info
                    posted_date = re.sub(r'\d+\.\d+\s*mi', '', posted_date).strip()

                # Parse location
                location_parts = self.parse_location(location)

                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'apply_url': apply_url,
                    'location': location,
                    'department': department,
                    'employment_type': '',
                    'description': '',
                    'posted_date': posted_date,
                    'city': location_parts['city'],
                    'state': location_parts['state'],
                    'country': location_parts['country'],
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }

                jobs.append(job_data)

            except Exception as e:
                logger.error(f"Error parsing job row {idx}: {str(e)}")
                continue

        return jobs

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result

        location_str = location_str.strip()
        # Remove postal codes (e.g., "560103")
        location_str = re.sub(r'\b\d{6}\b', '', location_str).strip().rstrip(',').strip()

        parts = [p.strip() for p in location_str.split(',')]

        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) == 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            # Second part could be country code "IN" or state
            if parts[1].upper() in ('IN', 'IND', 'INDIA'):
                result['country'] = 'India'
            else:
                result['state'] = parts[1]

        if 'IN' in location_str.split(',')[-1].strip().upper() or 'India' in location_str:
            result['country'] = 'India'

        return result


if __name__ == "__main__":
    scraper = NestleScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

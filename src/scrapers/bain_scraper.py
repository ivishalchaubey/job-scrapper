import hashlib
import re
import sys
from pathlib import Path

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

try:
    import requests
except ImportError:
    requests = None

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('bain_scraper')


class BainScraper:
    def __init__(self):
        self.company_name = 'Bain'
        # Original URL (Cloudflare-blocked, kept for reference)
        self.url = 'https://www.bain.com/careers/find-a-role/?filters=offices(275,276,274)%7C'
        # Internal API endpoint (requires Cloudflare bypass via cloudscraper)
        self._api_url = 'https://www.bain.com/en/api/jobsearch/keyword/get'
        self._job_detail_base = 'https://www.bain.com/careers/find-a-role/position/'
        # Office filter IDs: 275=Mumbai, 276=New Delhi, 274=Bengaluru
        self._office_ids = '275,276,274'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Bain India jobs via internal API with cloudscraper for Cloudflare bypass."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping via API with Cloudflare bypass")

            if cloudscraper is None:
                logger.error("cloudscraper library not available. Install with: pip install cloudscraper")
                return all_jobs

            # Create cloudscraper session to bypass Cloudflare
            scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'darwin', 'mobile': False}
            )

            # First visit the careers page to get Cloudflare cookies
            logger.info("Fetching Cloudflare cookies from careers page...")
            try:
                cookie_response = scraper.get(
                    'https://www.bain.com/careers/find-a-role/',
                    timeout=SCRAPE_TIMEOUT
                )
                if cookie_response.status_code != 200:
                    logger.warning(f"Cookie page returned {cookie_response.status_code}")
            except Exception as e:
                logger.warning(f"Cookie fetch failed: {str(e)}")

            # Now query the job search API
            page = 1
            results_per_page = 50  # Request more per page

            while page <= max_pages:
                params = {
                    'keyword': '',
                    'page': page,
                    'resultsPerPage': results_per_page,
                    'offices': self._office_ids,
                }

                try:
                    response = scraper.get(
                        self._api_url,
                        params=params,
                        headers={
                            'Accept': 'application/json, text/plain, */*',
                            'X-Requested-With': 'XMLHttpRequest',
                            'Referer': self.url,
                        },
                        timeout=SCRAPE_TIMEOUT
                    )

                    if response.status_code != 200:
                        logger.warning(f"API returned status {response.status_code} on page {page}")
                        break

                    data = response.json()

                    if not isinstance(data, dict):
                        logger.error(f"Unexpected API response type: {type(data).__name__}")
                        break

                    results = data.get('results', [])
                    total_results = data.get('totalResults', 0)

                    if page == 1:
                        logger.info(f"API reports {total_results} total results, got {len(results)} on first page")

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

                    logger.info(f"Page {page}: {len(results)} results, {new_count} new. Total: {len(all_jobs)}")

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
                # Filter for India offices
                india_cities = ['Mumbai', 'New Delhi', 'Bengaluru', 'Bangalore', 'Delhi',
                                'Gurgaon', 'Gurugram', 'Hyderabad', 'Chennai', 'Pune', 'Kolkata']
                india_offices = [loc.strip() for loc in locations_raw
                                 if any(city.lower() in loc.strip().lower() for city in india_cities)]
                if india_offices:
                    location_str = ', '.join(india_offices)
                else:
                    # If no India-specific offices, use all locations
                    location_str = ', '.join(loc.strip() for loc in locations_raw[:5])
                    if len(locations_raw) > 5:
                        location_str += f' + {len(locations_raw) - 5} more offices'
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
                description = description[:3000]

            # Parse location
            location_parts = self.parse_location(location_str)

            job_data = {
                'external_id': self.generate_external_id(job_id if job_id else title, self.company_name),
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
        location_str = re.sub(r'\+\s*\d+\s*(?:more\s+)?offices?', '', location_str).strip().rstrip(',').strip()

        # Check for India cities
        india_cities = ['Mumbai', 'New Delhi', 'Bengaluru', 'Bangalore', 'Delhi',
                        'Gurgaon', 'Gurugram', 'Hyderabad', 'Chennai', 'Pune', 'Kolkata']
        found_cities = [city for city in india_cities if city.lower() in location_str.lower()]

        if found_cities:
            result['city'] = ', '.join(found_cities)
            result['country'] = 'India'
        else:
            # Try to parse as comma-separated
            parts = [p.strip() for p in location_str.split(',') if p.strip()]
            if parts:
                result['city'] = parts[0]
            if len(parts) >= 2:
                result['state'] = parts[1]
            if len(parts) >= 3:
                result['country'] = parts[2]

        # Default to India for our filtered results
        if not result['country'] and any(city.lower() in location_str.lower() for city in india_cities):
            result['country'] = 'India'

        return result


if __name__ == "__main__":
    scraper = BainScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job.get('employment_type', '')}")

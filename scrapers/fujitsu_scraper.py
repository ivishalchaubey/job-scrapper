import requests
import hashlib
import time

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('fujitsu_scraper')

PAGE_SIZE = 10  # SuccessFactors RMK API returns 10 per page


class FujitsuScraper:
    def __init__(self):
        self.company_name = "Fujitsu"
        self.url = "https://www.jobs.global.fujitsu.com/search/?q=&locationsearch=&searchResultView=LIST&markerViewed=&carouselIndex=&facetFilters=%7B%22jobLocationCountry%22%3A%5B%22India%22%5D%7D&pageNumber=0"
        self.base_url = 'https://www.jobs.global.fujitsu.com'
        self.api_url = 'https://www.jobs.global.fujitsu.com/services/recruiting/v1/jobs'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*',
            'Content-Type': 'application/json',
            'Referer': 'https://www.jobs.global.fujitsu.com/search/',
            'Origin': 'https://www.jobs.global.fujitsu.com',
        })

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result

    def _expand_state_code(self, code):
        """Expand Indian state abbreviations to full names."""
        state_map = {
            'KA': 'Karnataka', 'TN': 'Tamil Nadu', 'TG': 'Telangana',
            'MH': 'Maharashtra', 'UP': 'Uttar Pradesh', 'DL': 'Delhi',
            'HR': 'Haryana', 'GJ': 'Gujarat', 'RJ': 'Rajasthan',
            'WB': 'West Bengal', 'AP': 'Andhra Pradesh', 'KL': 'Kerala',
            'PB': 'Punjab', 'OR': 'Odisha', 'MP': 'Madhya Pradesh',
        }
        return state_map.get(code, code)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        try:
            logger.info(f"Starting {self.company_name} scraping via RMK API: {self.api_url}")

            for page in range(max_pages):
                payload = {
                    'keywords': '',
                    'locale': 'en_US',
                    'location': 'India',
                    'pageNumber': page,
                    'sortBy': 'recent',
                }

                logger.info(f"Fetching page {page + 1} (pageNumber={page})")
                response = self.session.post(self.api_url, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()

                total_jobs = data.get('totalJobs', 0)
                if page == 0:
                    logger.info(f"Total jobs available: {total_jobs}")

                job_results = data.get('jobSearchResult', [])
                if not job_results:
                    logger.info(f"No more jobs on page {page + 1}, stopping.")
                    break

                page_jobs = self._extract_jobs(job_results)
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                # Check if we've fetched all available jobs
                if len(all_jobs) >= total_jobs:
                    break

                if page + 1 < max_pages:
                    time.sleep(1)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")

        return all_jobs

    def _extract_jobs(self, job_results):
        """Parse job objects from SuccessFactors RMK API response."""
        jobs = []
        seen_ids = set()

        for item in job_results:
            try:
                job = item.get('response', {})
                if not job:
                    continue

                title = (job.get('unifiedStandardTitle') or '').strip()
                if not title or len(title) < 3:
                    continue

                job_id = str(job.get('id', '')).strip()
                if not job_id:
                    continue
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                # Parse locations - can be multiple
                location_list = job.get('jobLocationShort', [])
                # Take the first location as primary, clean up trailing comma/space
                primary_location = ''
                city = ''
                state = ''
                country = 'India'
                if location_list:
                    primary_location = location_list[0].strip().rstrip(',').strip()
                    parts = [p.strip() for p in primary_location.split(',')]
                    if len(parts) >= 1:
                        city = parts[0]
                    if len(parts) >= 2:
                        state = self._expand_state_code(parts[1].strip())
                    if len(parts) >= 3:
                        country_code = parts[2].strip()
                        country = 'India' if country_code == 'IND' else country_code

                # Build clean location string
                clean_parts = []
                if city:
                    clean_parts.append(city)
                if state and state != city:
                    clean_parts.append(state)
                location = ', '.join(clean_parts) if clean_parts else primary_location

                # If multiple locations, note them
                if len(location_list) > 1:
                    other_cities = []
                    for loc in location_list[1:]:
                        loc_clean = loc.strip().rstrip(',').strip()
                        loc_city = loc_clean.split(',')[0].strip()
                        if loc_city and loc_city not in other_cities:
                            other_cities.append(loc_city)
                    if other_cities:
                        location = f"{location} (+{', '.join(other_cities)})"

                department = ''
                bu_list = job.get('businessUnit_obj', [])
                if bu_list:
                    department = bu_list[0]

                posted_date = (job.get('unifiedStandardStart') or '').strip()

                # Build apply URL from URL title
                url_title = job.get('urlTitle') or job.get('unifiedUrlTitle', '')
                apply_url = f"{self.base_url}/job/{url_title}" if url_title else self.url

                jobs.append({
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': country,
                    'employment_type': '',
                    'department': department,
                    'apply_url': apply_url,
                    'posted_date': posted_date,
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                })

            except Exception as e:
                logger.error(f"Error parsing job: {str(e)}")
                continue

        return jobs


if __name__ == "__main__":
    scraper = FujitsuScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

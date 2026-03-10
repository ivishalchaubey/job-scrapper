import requests
import hashlib
import time

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE

logger = setup_logger('experian_scraper')


class ExperianScraper:
    def __init__(self):
        self.company_name = "Experian"
        self.url = "https://careers.smartrecruiters.com/experian"
        self.api_base = 'https://api.smartrecruiters.com/v1/companies'
        self.company_id = 'Experian'
        self.page_size = 100

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Experian via SmartRecruiters API"""
        all_jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name} via SmartRecruiters API")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            }

            current_page = 0
            total_found = None

            while current_page < max_pages:
                offset = current_page * self.page_size
                logger.info(f"Fetching page {current_page + 1} (offset={offset})")

                api_url = f"{self.api_base}/{self.company_id}/postings"
                params = {
                    'limit': self.page_size,
                    'offset': offset,
                }

                try:
                    response = requests.get(
                        api_url,
                        params=params,
                        headers=headers,
                        timeout=SCRAPE_TIMEOUT
                    )
                    response.raise_for_status()
                    data = response.json()
                except requests.exceptions.RequestException as e:
                    logger.error(f"API request failed on page {current_page + 1}: {str(e)}")
                    break
                except ValueError as e:
                    logger.error(f"Failed to parse JSON on page {current_page + 1}: {str(e)}")
                    break

                postings = data.get('content', [])
                if total_found is None:
                    total_found = data.get('totalFound', 0)
                    logger.info(f"Total jobs available: {total_found}")

                if not postings:
                    logger.info(f"No more postings on page {current_page + 1}")
                    break

                logger.info(f"Page {current_page + 1}: {len(postings)} postings")

                for posting in postings:
                    try:
                        job_data = self._parse_posting(posting)
                        if job_data:
                            all_jobs.append(job_data)
                    except Exception as e:
                        logger.error(f"Error parsing posting: {str(e)}")
                        continue

                if offset + len(postings) >= total_found:
                    logger.info("Reached end of available jobs")
                    break

                current_page += 1
                time.sleep(1)

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _parse_posting(self, posting):
        """Parse a single posting from SmartRecruiters API response"""
        posting_id = posting.get('id', '') or posting.get('uuid', '')
        title = posting.get('name', '')

        if not title or not posting_id:
            return None

        # Build apply URL
        ref_url = posting.get('ref', '')
        if ref_url:
            apply_url = ref_url
        else:
            apply_url = f"{self.url}/{posting_id}"

        # Location
        location_data = posting.get('location', {})
        city = location_data.get('city', '') or ''
        region = location_data.get('region', '') or ''
        country = location_data.get('country', '') or ''
        remote = location_data.get('remote', False)

        location_parts = []
        if city:
            location_parts.append(city)
        if region:
            location_parts.append(region)
        if country:
            location_parts.append(country)
        location_str = ', '.join(location_parts)

        # Department
        department_data = posting.get('department', {})
        department = department_data.get('label', '') or ''

        # Employment type
        type_data = posting.get('typeOfEmployment', {})
        employment_type = type_data.get('label', '') or ''

        # Experience level
        exp_data = posting.get('experienceLevel', {})
        experience_level = exp_data.get('label', '') or ''

        # Job function / category
        function_data = posting.get('function', {}) or posting.get('category', {})
        job_function = ''
        if isinstance(function_data, dict):
            job_function = function_data.get('label', '') or ''

        # Remote type
        remote_type = ''
        if remote:
            remote_type = 'Remote'

        # Posted date
        posted_date = posting.get('releasedDate', '') or posting.get('createdOn', '') or ''

        # Country normalization
        country_name = country
        if country == 'in' or country == 'IN' or country == 'India':
            country_name = 'India'

        city_parsed, state_parsed, country_parsed = self.parse_location(location_str)

        job_data = {
            'external_id': self.generate_external_id(str(posting_id), self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': '',
            'location': location_str,
            'city': city_parsed if city_parsed else city,
            'state': state_parsed if state_parsed else region,
            'country': country_name if country_name else 'India',
            'employment_type': employment_type,
            'department': department,
            'apply_url': apply_url,
            'posted_date': posted_date,
            'job_function': job_function,
            'experience_level': experience_level,
            'salary_range': '',
            'remote_type': remote_type,
            'status': 'active'
        }

        return job_data

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        country = parts[2] if len(parts) > 2 else ''

        if not country and 'India' in location_str:
            country = 'India'

        return city, state, country


if __name__ == "__main__":
    scraper = ExperianScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']} | {job['apply_url']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

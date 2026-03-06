import requests
import hashlib
import time

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('mcdonalds_scraper')


class McDonaldsScraper:
    def __init__(self):
        self.company_name = "McDonald's India"
        self.api_url = 'https://prod-warmachine.talent500.co/api/jobs/'
        self.company_slug = 'mcdonaldsindia'
        self.base_url = 'https://talent500.com/jobs/mcdonaldsindia/'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from McDonald's India via Talent500 REST API."""
        all_jobs = []
        page_size = 20
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': self.base_url,
        })

        try:
            logger.info(f"Starting API scrape for {self.company_name}")

            for page in range(1, max_pages + 1):
                params = {
                    'company_slug': self.company_slug,
                    'page': page,
                    'size': page_size,
                }

                response = session.get(self.api_url, params=params, timeout=30)
                if response.status_code != 200:
                    logger.error(f"API returned status {response.status_code}")
                    break

                data = response.json()
                total = data.get('total', 0)
                job_list = data.get('data', [])

                if not job_list:
                    logger.info(f"No more jobs on page {page}")
                    break

                for job_item in job_list:
                    parsed = self._parse_job(job_item)
                    if parsed:
                        all_jobs.append(parsed)

                logger.info(f"Page {page}: {len(job_list)} jobs (total fetched: {len(all_jobs)}/{total})")

                if len(job_list) < page_size:
                    break

                time.sleep(1)

            logger.info(f"Successfully scraped {len(all_jobs)} jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _parse_job(self, job_item):
        """Parse a single job item from the Talent500 API response."""
        try:
            if not isinstance(job_item, dict):
                return None

            title = (job_item.get('title') or job_item.get('title_alias_1') or '').strip()
            if not title:
                return None

            # Check if the job is active
            if not job_item.get('is_active', True):
                return None

            job_id = job_item.get('id', '') or job_item.get('external_id', '')
            if not job_id:
                job_id = hashlib.md5(title.encode()).hexdigest()[:12]

            slug = job_item.get('slug', '')
            apply_url = f"https://talent500.com/jobs/{slug}" if slug else self.base_url

            location = (job_item.get('location') or '').strip()
            city, state, country = self.parse_location(location)

            # Extract country info
            country_info = job_item.get('country', {})
            if isinstance(country_info, dict):
                country = country_info.get('name', 'India')

            department = (job_item.get('job_function') or '').strip()
            job_category = (job_item.get('job_category') or '').strip()
            employment_type = (job_item.get('employment_type') or '').strip()

            min_exp = job_item.get('min_experience_years')
            max_exp = job_item.get('max_experience_years')
            experience_level = ''
            if min_exp is not None and max_exp is not None:
                experience_level = f"{min_exp}-{max_exp} years"
            elif min_exp is not None:
                experience_level = f"{min_exp}+ years"

            is_remote = job_item.get('is_remote')
            remote_type = ''
            if is_remote is True:
                remote_type = 'Remote'
            elif is_remote is False:
                remote_type = 'On-site'

            return {
                'external_id': self.generate_external_id(str(job_id), self.company_name),
                'company_name': self.company_name,
                'title': title,
                'description': '',
                'location': location if location else 'India',
                'city': city,
                'state': state,
                'country': country,
                'employment_type': employment_type,
                'department': department,
                'apply_url': apply_url,
                'posted_date': job_item.get('posted_on', ''),
                'job_function': job_category or department,
                'experience_level': experience_level,
                'salary_range': '',
                'remote_type': remote_type,
                'status': 'active'
            }
        except Exception as e:
            logger.error(f"Error parsing job: {str(e)}")
            return None


if __name__ == "__main__":
    scraper = McDonaldsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

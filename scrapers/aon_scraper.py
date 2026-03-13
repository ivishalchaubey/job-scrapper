import hashlib

try:
    import requests
except ImportError:
    requests = None

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import MAX_PAGES_TO_SCRAPE, HEADLESS_MODE

logger = setup_logger('aon_scraper')

class AonScraper:
    def __init__(self):
        self.company_name = "Aon"
        self.url = "https://jobs.aon.com/jobs?locations=Bangalore,Karnataka,India%7CBengaluru,Karnataka,India%7CGreater%20Noida,Uttar%20Pradesh,India%7CGurgaon,Haryana,India%7CGurugram,Haryana,India%7CMumbai,Maharashtra,India%7CNOIDA,Uttar%20Pradesh,India&page=1"
        self.base_url = 'https://jobs.aon.com'
        self.api_url = 'https://jobs.aon.com/api/jobs'
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Aon jobs using the Jibe/iCIMS REST API directly."""
        all_jobs = []

        if requests is None:
            logger.error("requests library not available, cannot scrape Aon")
            return all_jobs

        try:
            all_jobs = self._scrape_via_api(max_pages)
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")

        logger.info(f"Total jobs scraped: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_api(self, max_pages):
        """Scrape Aon jobs using the Jibe/iCIMS JSON API."""
        all_jobs = []
        scraped_ids = set()
        per_page = 20

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': self.url,
        }

        for page_num in range(1, max_pages + 1):
            params = {
                'page': page_num,
                'limit': per_page,
                'location': 'India',
            }

            logger.info(f"API request page {page_num}")

            try:
                response = requests.get(self.api_url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.error(f"API request failed on page {page_num}: {str(e)}")
                break

            total_count = data.get('totalCount', 0)
            jobs_list = data.get('jobs', [])

            if not jobs_list:
                logger.info(f"No more jobs on page {page_num}")
                break

            logger.info(f"Page {page_num}: received {len(jobs_list)} jobs (total available: {total_count})")

            for item in jobs_list:
                job_data = item.get('data', {})
                if not job_data:
                    continue

                job = self._parse_job(job_data)
                if job and job['external_id'] not in scraped_ids:
                    all_jobs.append(job)
                    scraped_ids.add(job['external_id'])

            # Check if we've fetched all available
            if len(all_jobs) >= total_count:
                logger.info("Fetched all available jobs")
                break

            if len(jobs_list) < per_page:
                logger.info("Last page reached (fewer results than limit)")
                break

        return all_jobs

    def _parse_job(self, job_data):
        """Parse a single job from the Jibe/iCIMS API response."""
        title = job_data.get('title', '').strip()
        if not title:
            return None

        req_id = str(job_data.get('req_id', '') or job_data.get('slug', ''))
        if not req_id:
            req_id = hashlib.md5(title.encode()).hexdigest()[:12]

        city = job_data.get('city', '').strip()
        state = job_data.get('state', '').strip()
        country = job_data.get('country', '').strip() or 'India'

        # Use full_location or short_location if available
        location = job_data.get('full_location', '') or job_data.get('short_location', '')
        if not location:
            parts = [p for p in [city, state, country] if p]
            location = ', '.join(parts)

        # Filter for India
        india_markers = ['india', 'bangalore', 'bengaluru', 'mumbai', 'delhi', 'hyderabad',
                         'chennai', 'pune', 'gurgaon', 'gurugram', 'noida', 'kolkata',
                         'karnataka', 'maharashtra']
        location_check = (location + ' ' + country).lower()
        if not any(m in location_check for m in india_markers):
            return None

        apply_url = job_data.get('apply_url', '')
        if not apply_url:
            apply_url = f"{self.base_url}/jobs/{req_id}"

        description = job_data.get('description', '') or job_data.get('responsibilities', '') or ''
        if description:
            description = description[:3000]

        employment_type = job_data.get('employment_type', '')
        if employment_type == 'FULL_TIME':
            employment_type = 'Full Time'
        elif employment_type == 'PART_TIME':
            employment_type = 'Part Time'
        elif employment_type == 'CONTRACT':
            employment_type = 'Contract'

        categories = job_data.get('categories', [])
        department = ''
        if categories and isinstance(categories, list):
            if isinstance(categories[0], dict):
                department = categories[0].get('name', '')
            elif isinstance(categories[0], str):
                department = categories[0]

        posted_date = job_data.get('posted_date', '') or ''

        # Remote type from tags4
        remote_type = ''
        tags4 = job_data.get('tags4', [])
        if tags4 and isinstance(tags4, list):
            for tag in tags4:
                tag_lower = str(tag).lower()
                if 'remote' in tag_lower:
                    remote_type = 'Remote'
                elif 'hybrid' in tag_lower:
                    remote_type = 'Hybrid'
                elif 'office' in tag_lower or 'onsite' in tag_lower:
                    remote_type = 'On-site'

        return {
            'external_id': self.generate_external_id(req_id, self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': description,
            'location': location,
            'city': city,
            'state': state,
            'country': country if country else 'India',
            'employment_type': employment_type,
            'department': department.strip(),
            'apply_url': apply_url,
            'posted_date': posted_date,
            'job_function': '',
            'experience_level': '',
            'salary_range': '',
            'remote_type': remote_type,
            'status': 'active'
        }

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
            if parts[1] in ['IN', 'IND', 'India']:
                result['country'] = 'India'
            else:
                result['state'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result

if __name__ == "__main__":
    scraper = AonScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

import requests
from bs4 import BeautifulSoup
import hashlib
from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import MAX_PAGES_TO_SCRAPE, HEADLESS_MODE

logger = setup_logger('wework_scraper')

class WeWorkScraper:
    def __init__(self):
        self.company_name = "WeWork"
        self.url = "https://weworkindia.hire.trakstar.com/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
        })
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

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

    def _extract_location_fields(self, job_data):
        """Extract city, state, country from the Trakstar Hire location object."""
        location = job_data.get('location', {})
        if isinstance(location, dict):
            city = location.get('city', '') or ''
            state = location.get('state', '') or ''
            country = location.get('country', '') or ''
        elif isinstance(location, str):
            city, state, country = self.parse_location(location)
        else:
            city, state, country = '', '', 'India'

        # Normalize country
        if not country or country.lower() in ('in', 'ind'):
            country = 'India'

        return city.strip(), state.strip(), country.strip()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")

            params = {
                'client_name': 'weworkindia',
            }

            logger.info(f"Fetching job listings from Trakstar Hire API")
            response = self.session.get(self.url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # The response could be a list or dict with 'objects' key
            if isinstance(data, list):
                job_list = data
            elif isinstance(data, dict):
                job_list = data.get('objects', []) or data.get('openings', []) or data.get('results', [])
                if not job_list and 'items' in data:
                    job_list = data['items']
            else:
                job_list = []

            logger.info(f"Found {len(job_list)} total job listings")

            for job_data in job_list:
                try:
                    job_id = str(job_data.get('id', ''))
                    title = job_data.get('title', '').strip()
                    if not title:
                        continue

                    # Location
                    city, state, country = self._extract_location_fields(job_data)

                    # Build location string
                    location_parts = [p for p in [city, state, country] if p]
                    location = ', '.join(location_parts) if location_parts else 'India'

                    # Description
                    description = job_data.get('description', '') or ''
                    if isinstance(description, str):
                        # Strip HTML tags if present
                        if '<' in description and '>' in description:
                            soup = BeautifulSoup(description, 'html.parser')
                            description = soup.get_text(separator=' ', strip=True)
                        description = description[:3000]

                    # Apply URL
                    apply_url = job_data.get('hosted_url', '') or job_data.get('url', '') or ''
                    if not apply_url and job_id:
                        apply_url = f"https://weworkindia.hire.trakstar.com/jobs/{job_id}"

                    # Department / Team
                    department = job_data.get('team', '') or job_data.get('department', '') or ''
                    if isinstance(department, dict):
                        department = department.get('name', '') or department.get('label', '')

                    # Employment type / Position type
                    employment_type = job_data.get('position_type', '') or job_data.get('employment_type', '') or ''
                    if isinstance(employment_type, dict):
                        employment_type = employment_type.get('label', '') or employment_type.get('name', '')

                    # Posted date / Close date
                    posted_date = job_data.get('created_on', '') or job_data.get('published_date', '') or ''

                    # Remote type
                    remote_type = ''
                    if 'remote' in title.lower() or 'remote' in location.lower():
                        remote_type = 'Remote'
                    elif 'hybrid' in title.lower() or 'hybrid' in location.lower():
                        remote_type = 'Hybrid'

                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': description,
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country if country else 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': apply_url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': remote_type,
                        'status': 'active'
                    }
                    jobs.append(job)
                    logger.info(f"Extracted: {title} | {location}")
                except Exception as e:
                    logger.warning(f"Error parsing job: {str(e)}")
                    continue

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs

if __name__ == "__main__":
    scraper = WeWorkScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

import requests
import hashlib
from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE

logger = setup_logger('moveworks_scraper')


class MoveworksScraper:
    def __init__(self):
        self.company_name = 'Moveworks'
        self.url = 'https://boards.greenhouse.io/moveworks'
        self.api_url = 'https://boards-api.greenhouse.io/v1/boards/moveworks/jobs'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }
        india_keywords = [
            'India', 'Bangalore', 'Bengaluru', 'Mumbai', 'Delhi',
            'Hyderabad', 'Chennai', 'Pune', 'Gurugram', 'Gurgaon',
            'Noida', 'Kolkata', 'Ahmedabad', 'Jaipur', 'Kochi',
            'Thiruvananthapuram', 'Chandigarh', 'Lucknow', 'Indore'
        ]
        try:
            logger.info(f"Fetching jobs from Greenhouse API: {self.api_url}")
            response = requests.get(self.api_url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            postings = data.get('jobs', [])
            logger.info(f"API returned {len(postings)} total postings")
            for posting in postings:
                try:
                    title = posting.get('title', '')
                    if not title:
                        continue
                    location_obj = posting.get('location', {})
                    location = location_obj.get('name', '') if isinstance(location_obj, dict) else ''
                    if not any(kw in location for kw in india_keywords):
                        continue
                    job_id = str(posting.get('id', ''))
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]
                    absolute_url = posting.get('absolute_url', '')
                    date_str = posting.get('updated_at', '')
                    posted_date = date_str[:10] if date_str else ''
                    loc = self.parse_location(location)
                    all_jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc.get('city', ''),
                        'state': loc.get('state', ''),
                        'country': loc.get('country', 'India'),
                        'employment_type': '',
                        'department': '',
                        'apply_url': absolute_url or self.url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error processing posting: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"Greenhouse API error: {str(e)}")
        logger.info(f"Total India jobs found: {len(all_jobs)}")
        return all_jobs

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 2:
            result['state'] = parts[1]
        if len(parts) >= 3:
            result['country'] = parts[2]
        if 'India' in location_str:
            result['country'] = 'India'
        return result

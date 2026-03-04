import requests
import hashlib
from datetime import datetime
from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE

logger = setup_logger('cred_scraper')


class CREDScraper:
    def __init__(self):
        self.company_name = 'CRED'
        self.url = 'https://jobs.lever.co/cred'
        self.api_url = 'https://api.lever.co/v0/postings/cred?mode=json'

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
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
            'hyderabad', 'chennai', 'pune', 'gurugram', 'gurgaon',
            'noida', 'kolkata', 'ahmedabad', 'jaipur', 'kochi',
            'lucknow', 'chandigarh', 'indore', 'new delhi',
            'haryana', 'karnataka', 'maharashtra', 'telangana', 'tamil nadu'
        ]
        try:
            logger.info(f"Fetching jobs from Lever API: {self.api_url}")
            response = requests.get(self.api_url, headers=headers, timeout=30)
            response.raise_for_status()
            postings = response.json()
            if not isinstance(postings, list):
                logger.error("Unexpected API response format")
                return all_jobs
            logger.info(f"API returned {len(postings)} total postings")
            for posting in postings:
                try:
                    title = posting.get('text', '')
                    if not title:
                        continue
                    categories = posting.get('categories', {})
                    location = categories.get('location', '')
                    all_locations = str(categories.get('allLocations', ''))
                    combined_loc = (location + ' ' + all_locations).lower()
                    if not any(kw in combined_loc for kw in india_keywords):
                        continue
                    job_id = posting.get('id', '')
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]
                    apply_url = posting.get('hostedUrl', '') or posting.get('applyUrl', '')
                    created_at = posting.get('createdAt', 0)
                    posted_date = ''
                    if created_at:
                        try:
                            posted_date = datetime.fromtimestamp(created_at / 1000).strftime('%Y-%m-%d')
                        except Exception:
                            pass
                    commitment = categories.get('commitment', '')
                    department = categories.get('department', '')
                    team = categories.get('team', '')
                    workplace_type = posting.get('workplaceType', '')
                    remote_type = ''
                    if workplace_type:
                        wt = workplace_type.lower()
                        if 'remote' in wt:
                            remote_type = 'Remote'
                        elif 'hybrid' in wt:
                            remote_type = 'Hybrid'
                        elif 'onsite' in wt or 'on-site' in wt:
                            remote_type = 'On-site'
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
                        'employment_type': commitment,
                        'department': department,
                        'apply_url': apply_url or self.url,
                        'posted_date': posted_date,
                        'job_function': team if department else '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': remote_type,
                        'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error processing posting: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"Lever API error: {str(e)}")
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
        if 'india' in location_str.lower():
            result['country'] = 'India'
        return result

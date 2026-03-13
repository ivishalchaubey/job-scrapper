import requests
import hashlib
from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE, HEADLESS_MODE

logger = setup_logger('hm_scraper')

class HMScraper:
    def __init__(self):
        self.company_name = "H&M"
        self.url = "https://career.hm.com/in-en/search/?l=cou%3Ain"
        self.api_url = 'https://api.smartrecruiters.com/v1/companies/HMGroup/postings'
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        limit = 100
        max_results = max_pages * limit
        offset = 0
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }
        india_keywords = [
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
            'hyderabad', 'chennai', 'pune', 'gurugram', 'gurgaon',
            'noida', 'kolkata', 'ahmedabad', 'jaipur', 'kochi',
            'lucknow', 'chandigarh', 'indore', 'new delhi'
        ]
        try:
            while offset < max_results:
                params = {'limit': limit, 'offset': offset}
                logger.info(f"Fetching jobs offset={offset}")
                response = requests.get(self.api_url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
                total = data.get('totalFound', 0)
                postings = data.get('content', [])
                if not postings:
                    break
                logger.info(f"Page returned {len(postings)} jobs (total={total})")
                for posting in postings:
                    try:
                        title = posting.get('name', '')
                        if not title:
                            continue
                        location_obj = posting.get('location', {})
                        city = location_obj.get('city', '')
                        region = location_obj.get('region', '')
                        country = location_obj.get('country', '')
                        location = ', '.join(filter(None, [city, region, country]))
                        if not any(kw in location.lower() for kw in india_keywords):
                            continue
                        job_id = posting.get('id', '') or posting.get('refNumber', '')
                        if not job_id:
                            job_id = hashlib.md5(title.encode()).hexdigest()[:12]
                        ref_number = posting.get('refNumber', '')
                        apply_url = posting.get('url', {}).get('value', '') if isinstance(posting.get('url'), dict) else ''
                        if not apply_url:
                            apply_url = f"{self.url}/{ref_number}" if ref_number else self.url
                        department = posting.get('department', {}).get('label', '') if isinstance(posting.get('department'), dict) else ''
                        employment_type = posting.get('typeOfEmployment', {}).get('label', '') if isinstance(posting.get('typeOfEmployment'), dict) else ''
                        experience_level = posting.get('experienceLevel', {}).get('label', '') if isinstance(posting.get('experienceLevel'), dict) else ''
                        posted_date = posting.get('releasedDate', '')[:10] if posting.get('releasedDate') else ''
                        remote_type = ''
                        remote_status = posting.get('remotePossible', False)
                        if remote_status:
                            remote_type = 'Remote'
                        all_jobs.append({
                            'external_id': self.generate_external_id(str(job_id), self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': region,
                            'country': 'India',
                            'employment_type': employment_type,
                            'department': department,
                            'apply_url': apply_url,
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': experience_level,
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        })
                    except Exception as e:
                        logger.error(f"Error processing posting: {str(e)}")
                        continue
                offset += limit
                if offset >= total:
                    break
        except Exception as e:
            logger.error(f"SmartRecruiters API error: {str(e)}")
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
        if 'India' in location_str or 'india' in location_str.lower():
            result['country'] = 'India'
        return result

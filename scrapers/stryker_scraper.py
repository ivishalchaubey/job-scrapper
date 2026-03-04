import requests
import hashlib
from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE

logger = setup_logger('stryker_scraper')


class StrykerScraper:
    def __init__(self):
        self.company_name = 'Stryker'
        self.url = 'https://stryker.wd1.myworkdayjobs.com/StrykerCareers?Location_Country=c4f78be1a8f14da0ab49ce1162348a5e'
        self.api_url = 'https://stryker.wd1.myworkdayjobs.com/wday/cxs/stryker/StrykerCareers/jobs'
        self.base_job_url = 'https://stryker.wd1.myworkdayjobs.com/StrykerCareers'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        limit = 20
        max_results = max_pages * limit
        offset = 0
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }
        try:
            while len(all_jobs) < max_results:
                payload = {
                    'appliedFacets': {'Location_Country': ['c4f78be1a8f14da0ab49ce1162348a5e']},
                    'limit': limit,
                    'offset': offset,
                    'searchText': ''
                }
                logger.info(f"Fetching jobs offset={offset}")
                response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
                total = data.get('total', 0)
                job_postings = data.get('jobPostings', [])
                if not job_postings:
                    break
                logger.info(f"Page returned {len(job_postings)} jobs (total={total})")
                for posting in job_postings:
                    try:
                        title = posting.get('title', '')
                        if not title:
                            continue
                        location = posting.get('locationsText', '')
                        posted_on = posting.get('postedOn', '')
                        external_path = posting.get('externalPath', '')
                        job_id = external_path.split('/')[-1] if external_path else ''
                        if not job_id:
                            job_id = hashlib.md5(title.encode()).hexdigest()[:12]
                        bullet_fields = posting.get('bulletFields', [])
                        employment_type = ''
                        remote_type = ''
                        for field in bullet_fields:
                            fl = field.lower() if isinstance(field, str) else ''
                            if any(kw in fl for kw in ['full time', 'full-time', 'part time', 'part-time', 'contract', 'intern', 'temporary']):
                                employment_type = field
                            if any(kw in fl for kw in ['remote', 'hybrid', 'on-site', 'onsite']):
                                remote_type = field
                        apply_url = f"{self.base_job_url}{external_path}" if external_path else self.url
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
                            'employment_type': employment_type,
                            'department': '',
                            'apply_url': apply_url,
                            'posted_date': posted_on,
                            'job_function': '',
                            'experience_level': '',
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
            logger.error(f"Workday API error: {str(e)}")
        logger.info(f"Total jobs found: {len(all_jobs)}")
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
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result

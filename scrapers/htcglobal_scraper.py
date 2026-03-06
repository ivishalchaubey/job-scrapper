import requests
import hashlib

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('htcglobal_scraper')


class HTCGlobalScraper:
    def __init__(self):
        self.company_name = 'HTC Global'
        self.api_url = 'https://www.htcinc.com/wp-content/themes/himalayas-child/job-api-proxy.php'
        self.base_url = 'https://www.htcinc.com'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
        }

    def generate_external_id(self, job_id, company):
        """Generate stable external ID."""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        """Parse location string into dict with city, state, country."""
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        location_str = location_str.strip()
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
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result

    def _is_india_job(self, location_name, state_code):
        """Check if a job is India-based."""
        india_keywords = [
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
            'pune', 'hyderabad', 'noida', 'gurgaon', 'gurugram',
            'chennai', 'kolkata', 'jaipur', 'ahmedabad', 'lucknow',
            'chandigarh', 'indore', 'kochi', 'coimbatore', 'thiruvananthapuram',
            'bhubaneswar', 'nagpur', 'visakhapatnam', 'vadodara', 'mysore',
            'mangalore', 'trivandrum', 'cochin'
        ]
        combined = f"{location_name} {state_code}".lower()
        return any(kw in combined for kw in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from HTC Global via WordPress JSON API proxy."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping from API: {self.api_url}")

            response = requests.get(self.api_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Navigate JSON: data.data.jobs
            jobs_data = data
            if isinstance(data, dict):
                inner = data.get('data', data)
                if isinstance(inner, dict):
                    jobs_list = inner.get('jobs', [])
                else:
                    jobs_list = inner if isinstance(inner, list) else []
            else:
                jobs_list = data if isinstance(data, list) else []

            if not isinstance(jobs_list, list):
                logger.error(f"Unexpected API response structure, got type: {type(jobs_list)}")
                return all_jobs

            logger.info(f"API returned {len(jobs_list)} total job postings")

            for job in jobs_list:
                try:
                    if not isinstance(job, dict):
                        continue

                    job_title = job.get('job_title', '').strip()
                    if not job_title:
                        continue

                    location_name = job.get('location_name', '').strip()
                    state_code = job.get('state_code', '').strip()
                    requisition_number = str(job.get('requisition_number', '')).strip()
                    job_description = job.get('job_description', '').strip()

                    # Filter for India jobs
                    if not self._is_india_job(location_name, state_code):
                        continue

                    # Generate job ID from requisition number
                    if requisition_number:
                        job_id = requisition_number
                    else:
                        job_id = hashlib.md5(job_title.encode()).hexdigest()[:12]

                    external_id = self.generate_external_id(job_id, self.company_name)
                    if external_id in seen_ids:
                        continue

                    # Build apply URL
                    apply_url = f"https://www.htcinc.com/job-detail/?jobcode={requisition_number}" if requisition_number else self.base_url

                    # Build location string
                    location = location_name
                    if state_code and state_code not in location:
                        location = f"{location_name}, {state_code}"

                    location_parts = self.parse_location(location)

                    job_data = {
                        'external_id': external_id,
                        'company_name': self.company_name,
                        'title': job_title,
                        'description': job_description,
                        'location': location,
                        'city': location_parts['city'],
                        'state': location_parts['state'],
                        'country': location_parts['country'],
                        'employment_type': job.get('employment_type', ''),
                        'department': job.get('department', ''),
                        'apply_url': apply_url,
                        'posted_date': job.get('posted_date', ''),
                        'job_function': job.get('job_function', ''),
                        'experience_level': job.get('experience_level', ''),
                        'salary_range': '',
                        'remote_type': job.get('remote_type', ''),
                        'status': 'active'
                    }

                    all_jobs.append(job_data)
                    seen_ids.add(external_id)
                    logger.info(f"Extracted: {job_title} | {location}")

                except Exception as e:
                    logger.error(f"Error parsing job entry: {str(e)}")
                    continue

            logger.info(f"Successfully scraped {len(all_jobs)} India jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs


if __name__ == "__main__":
    scraper = HTCGlobalScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['apply_url']}")

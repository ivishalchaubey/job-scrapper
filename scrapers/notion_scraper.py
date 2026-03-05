import requests
import hashlib
from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT

logger = setup_logger('notion_scraper')


class NotionScraper:
    def __init__(self):
        self.company_name = 'Notion'
        self.api_url = 'https://api.ashbyhq.com/posting-api/job-board/notion'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=1):
        all_jobs = []
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }
        india_keywords = [
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
            'hyderabad', 'chennai', 'pune', 'gurugram', 'gurgaon',
            'noida', 'kolkata', 'ahmedabad', 'jaipur', 'kochi',
        ]
        try:
            logger.info(f"Fetching jobs from Ashby API for {self.company_name}")
            response = requests.get(self.api_url, headers=headers, timeout=SCRAPE_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            jobs = data.get('jobs', [])
            logger.info(f"Total jobs returned: {len(jobs)}")

            for job in jobs:
                try:
                    location = job.get('location', '')
                    address = job.get('address', {}) or {}
                    postal = address.get('postalAddress', {}) or {}
                    country = postal.get('addressCountry', '')

                    is_india = (
                        any(kw in location.lower() for kw in india_keywords)
                        or country.lower() == 'india'
                    )
                    if not is_india:
                        continue

                    title = job.get('title', '')
                    if not title:
                        continue

                    job_id = job.get('id', '')
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    city = postal.get('addressLocality', '')
                    state = postal.get('addressRegion', '')

                    employment_type = job.get('employmentType', '')
                    if employment_type == 'FullTime':
                        employment_type = 'Full-time'
                    elif employment_type == 'PartTime':
                        employment_type = 'Part-time'
                    elif employment_type == 'Contract':
                        employment_type = 'Contract'
                    elif employment_type == 'Intern':
                        employment_type = 'Internship'

                    remote_type = ''
                    workplace = job.get('workplaceType', '')
                    if workplace:
                        if 'remote' in workplace.lower():
                            remote_type = 'Remote'
                        elif 'hybrid' in workplace.lower():
                            remote_type = 'Hybrid'
                        else:
                            remote_type = 'On-site'
                    if job.get('isRemote'):
                        remote_type = 'Remote'

                    posted_date = ''
                    published = job.get('publishedAt', '')
                    if published:
                        posted_date = published[:10]

                    apply_url = job.get('applyUrl', '') or job.get('jobUrl', '')

                    all_jobs.append({
                        'external_id': self.generate_external_id(str(job_id), self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': job.get('department', ''),
                        'apply_url': apply_url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': remote_type,
                        'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error processing job: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Ashby API error: {str(e)}")

        logger.info(f"Total India jobs found: {len(all_jobs)}")
        return all_jobs

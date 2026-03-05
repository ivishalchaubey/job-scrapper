import requests
import hashlib
from datetime import datetime

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT

logger = setup_logger('makemytrip_scraper')


class MakeMyTripScraper:
    def __init__(self):
        self.company_name = 'MakeMyTrip'
        self.api_url = 'https://careers.makemytrip.com/api/jobs'
        self.base_url = 'https://careers.makemytrip.com'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=1):
        all_jobs = []
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }

        try:
            logger.info(f"Fetching jobs from MakeMyTrip API: {self.api_url}")
            response = requests.get(self.api_url, headers=headers, timeout=SCRAPE_TIMEOUT)
            response.raise_for_status()
            data = response.json()

            jobs = data.get('allJobs', [])
            logger.info(f"Total jobs returned: {len(jobs)}")

            for job in jobs:
                try:
                    title = job.get('job_title', '')
                    if not title:
                        continue

                    job_id = job.get('job_id', '')
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    # Location is a list of strings
                    locations = job.get('location', [])
                    if isinstance(locations, list):
                        location = ', '.join(locations)
                    else:
                        location = str(locations)

                    # City is a list
                    cities = job.get('location_city', [])
                    city = cities[0] if cities else ''

                    department = job.get('department', '')
                    division = job.get('division', '')

                    # Employee type
                    employee_type = job.get('employee_type', '')
                    employment_type = ''
                    if employee_type:
                        if 'employee' in employee_type.lower():
                            employment_type = 'Full-time'
                        elif 'intern' in employee_type.lower():
                            employment_type = 'Internship'
                        elif 'contract' in employee_type.lower():
                            employment_type = 'Contract'
                        else:
                            employment_type = employee_type

                    # Remote type
                    is_remote = job.get('is_remote', 0)
                    remote_type = 'Remote' if is_remote else ''

                    # Posted date
                    posted_date = ''
                    created = job.get('job_created_timestamp', '')
                    if created:
                        try:
                            dt = datetime.strptime(created, '%d-%m-%Y %H:%M:%S')
                            posted_date = dt.strftime('%Y-%m-%d')
                        except Exception:
                            pass

                    # Experience
                    exp_from = job.get('experience_from', '')
                    exp_to = job.get('experience_to', '')
                    experience_level = ''
                    if exp_from or exp_to:
                        experience_level = f"{exp_from}-{exp_to} years" if exp_to else f"{exp_from}+ years"

                    apply_url = f"{self.base_url}/prod/jobs/{job_id}"

                    all_jobs.append({
                        'external_id': self.generate_external_id(str(job_id), self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': '',
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': apply_url,
                        'posted_date': posted_date,
                        'job_function': division,
                        'experience_level': experience_level,
                        'salary_range': '',
                        'remote_type': remote_type,
                        'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error processing job: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"MakeMyTrip API error: {str(e)}")

        logger.info(f"Total jobs found: {len(all_jobs)}")
        return all_jobs

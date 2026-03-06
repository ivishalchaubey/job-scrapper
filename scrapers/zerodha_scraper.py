import requests
import hashlib

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('zerodha_scraper')


class ZerodhaScraper:
    def __init__(self):
        self.company_name = 'Zerodha'
        self.url = 'https://careers.zerodha.com/api/jobs'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Zerodha jobs from their Vue.js 3 JSON API.

        API endpoint: GET https://careers.zerodha.com/api/jobs
        Response format: {"count": N, "data": [...], "success": true}

        Note: Zerodha may have 0 jobs currently. The scraper handles that gracefully.
        """
        all_jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name} from {self.url}")

            try:
                response = self.session.get(self.url, timeout=30)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {str(e)}")
                return all_jobs

            try:
                data = response.json()
            except ValueError as e:
                logger.error(f"Failed to parse JSON response: {str(e)}")
                return all_jobs

            success = data.get('success', False)
            if not success:
                logger.warning(f"API returned success=false")

            count = data.get('count', 0)
            job_list = data.get('data', [])

            logger.info(f"API reports {count} jobs, received {len(job_list)} job entries")

            if not job_list:
                logger.info("No jobs currently available at Zerodha")
                return all_jobs

            for job_entry in job_list:
                try:
                    # Extract fields from the job entry
                    title = job_entry.get('title', '') or job_entry.get('name', '') or ''
                    if not title:
                        continue

                    # Job ID - try various field names
                    job_id = str(
                        job_entry.get('id', '') or
                        job_entry.get('job_id', '') or
                        job_entry.get('slug', '') or
                        ''
                    )
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    # Location
                    location = job_entry.get('location', '') or job_entry.get('city', '') or ''
                    if isinstance(location, list):
                        location = ', '.join(str(loc) for loc in location)
                    elif isinstance(location, dict):
                        location = location.get('name', '') or location.get('city', '') or ''

                    # Description
                    description = job_entry.get('description', '') or \
                                  job_entry.get('content', '') or \
                                  job_entry.get('summary', '') or ''
                    if description:
                        description = description[:2000]

                    # Department
                    department = job_entry.get('department', '') or \
                                 job_entry.get('team', '') or \
                                 job_entry.get('category', '') or ''
                    if isinstance(department, dict):
                        department = department.get('name', '') or department.get('title', '') or ''

                    # Employment type
                    employment_type = job_entry.get('employment_type', '') or \
                                      job_entry.get('type', '') or \
                                      job_entry.get('job_type', '') or ''
                    if isinstance(employment_type, dict):
                        employment_type = employment_type.get('name', '') or ''

                    # Apply URL
                    apply_url = job_entry.get('apply_url', '') or \
                                job_entry.get('url', '') or \
                                job_entry.get('link', '') or ''
                    slug = job_entry.get('slug', '') or job_entry.get('id', '')
                    if not apply_url and slug:
                        apply_url = f"https://careers.zerodha.com/jobs/{slug}"
                    if not apply_url:
                        apply_url = 'https://careers.zerodha.com'

                    # Posted date
                    posted_date = job_entry.get('posted_date', '') or \
                                  job_entry.get('created_at', '') or \
                                  job_entry.get('published_at', '') or \
                                  job_entry.get('date', '') or ''
                    if posted_date and len(posted_date) > 10:
                        posted_date = posted_date[:10]

                    # Experience level
                    experience_level = job_entry.get('experience_level', '') or \
                                       job_entry.get('experience', '') or \
                                       job_entry.get('seniority', '') or ''
                    if isinstance(experience_level, dict):
                        experience_level = experience_level.get('name', '') or ''

                    # Remote type
                    remote_type = job_entry.get('remote_type', '') or \
                                  job_entry.get('workplace_type', '') or ''
                    if isinstance(remote_type, dict):
                        remote_type = remote_type.get('name', '') or ''
                    if not remote_type:
                        is_remote = job_entry.get('remote', False) or job_entry.get('is_remote', False)
                        if is_remote:
                            remote_type = 'Remote'

                    # Job function
                    job_function = job_entry.get('job_function', '') or \
                                   job_entry.get('function', '') or ''
                    if isinstance(job_function, dict):
                        job_function = job_function.get('name', '') or ''

                    # Salary range
                    salary_range = job_entry.get('salary_range', '') or \
                                   job_entry.get('salary', '') or \
                                   job_entry.get('compensation', '') or ''

                    # Default location to India since Zerodha is India-based
                    if not location:
                        location = 'Bangalore, India'

                    loc = self.parse_location(location)

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': description,
                        'location': location,
                        'city': loc.get('city', ''),
                        'state': loc.get('state', ''),
                        'country': loc.get('country', 'India'),
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': apply_url,
                        'posted_date': posted_date,
                        'job_function': job_function,
                        'experience_level': experience_level,
                        'salary_range': salary_range,
                        'remote_type': remote_type,
                        'status': 'active'
                    }

                    all_jobs.append(job_data)
                    logger.info(f"Added job: {title} | {location}")

                except Exception as e:
                    logger.error(f"Error processing job entry: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Total jobs found for {self.company_name}: {len(all_jobs)}")
        return all_jobs


if __name__ == "__main__":
    scraper = ZerodhaScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']} | {job['apply_url']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

import requests
import hashlib
from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import MAX_PAGES_TO_SCRAPE, HEADLESS_MODE

logger = setup_logger('grab_scraper')

class GrabScraper:
    def __init__(self):
        self.company_name = "Grab Taxi"
        self.url = "https://www.grab.careers/en/jobs/?search=&country=India&pagesize=20#results"
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Grab India jobs from the SmartRecruiters API.

        The SmartRecruiters API at /v1/companies/Grab/postings returns JSON with
        job postings. We filter for country=India and paginate using offset + limit.

        Response structure:
        {
            "totalFound": N,
            "content": [
                {
                    "id": "...",
                    "name": "Job Title",
                    "refNumber": "...",
                    "releasedDate": "2024-01-01T...",
                    "location": {"city": "...", "region": "...", "country": "..."},
                    "department": {"label": "..."},
                    "typeOfEmployment": {"label": "..."},
                    "experienceLevel": {"label": "..."},
                    "company": {"name": "Grab"}
                }
            ]
        }
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            limit = 100
            seen_ids = set()

            india_keywords = [
                'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
                'hyderabad', 'chennai', 'pune', 'gurugram', 'gurgaon',
                'noida', 'kolkata', 'ahmedabad', 'jaipur', 'kochi',
                'lucknow', 'chandigarh', 'indore', 'new delhi'
            ]

            for page in range(max_pages):
                offset = page * limit
                params = {
                    'offset': offset,
                    'limit': limit,
                    'country': 'India',
                }

                logger.info(f"Fetching page {page + 1} (offset={offset})")
                try:
                    response = self.session.get(self.url, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                except Exception as e:
                    logger.error(f"Failed to fetch page {page + 1}: {str(e)}")
                    break

                total = data.get('totalFound', 0)
                postings = data.get('content', [])

                if not postings:
                    logger.info(f"No postings returned on page {page + 1}, stopping")
                    break

                logger.info(f"Page {page + 1}: {len(postings)} postings (totalFound={total})")

                page_count = 0
                for posting in postings:
                    try:
                        title = posting.get('name', '').strip()
                        if not title:
                            continue

                        # Extract location
                        location_obj = posting.get('location', {})
                        city = location_obj.get('city', '') if isinstance(location_obj, dict) else ''
                        region = location_obj.get('region', '') if isinstance(location_obj, dict) else ''
                        country_val = location_obj.get('country', '') if isinstance(location_obj, dict) else ''

                        location_parts = [p for p in [city, region, country_val] if p]
                        location = ', '.join(location_parts)

                        # Filter for India jobs
                        combined_loc = location.lower()
                        is_india = any(kw in combined_loc for kw in india_keywords)
                        if not is_india:
                            continue

                        # Job ID
                        job_id = str(posting.get('id', ''))
                        ref_number = posting.get('refNumber', '')
                        if not job_id:
                            job_id = ref_number or hashlib.md5(title.encode()).hexdigest()[:12]

                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        # Apply URL
                        apply_url = ''
                        url_obj = posting.get('url')
                        if isinstance(url_obj, dict):
                            apply_url = url_obj.get('value', '')
                        if not apply_url:
                            apply_url = f"https://careers.smartrecruiters.com/Grab/{ref_number}" if ref_number else f"https://careers.smartrecruiters.com/Grab/{job_id}"

                        # Department
                        department = ''
                        dept_obj = posting.get('department')
                        if isinstance(dept_obj, dict):
                            department = dept_obj.get('label', '')

                        # Employment type
                        employment_type = ''
                        emp_obj = posting.get('typeOfEmployment')
                        if isinstance(emp_obj, dict):
                            employment_type = emp_obj.get('label', '')

                        # Experience level
                        experience_level = ''
                        exp_obj = posting.get('experienceLevel')
                        if isinstance(exp_obj, dict):
                            experience_level = exp_obj.get('label', '')

                        # Posted date
                        posted_date = ''
                        released = posting.get('releasedDate', '')
                        if released:
                            posted_date = released[:10]

                        # Job function
                        job_function = ''
                        func_obj = posting.get('function')
                        if isinstance(func_obj, dict):
                            job_function = func_obj.get('label', '')

                        # Remote type
                        remote_type = ''
                        if isinstance(location_obj, dict) and location_obj.get('remote'):
                            remote_type = 'Remote'
                        elif 'remote' in title.lower():
                            remote_type = 'Remote'
                        elif 'hybrid' in title.lower():
                            remote_type = 'Hybrid'

                        # Normalize location string
                        if location and 'india' not in location.lower():
                            location = f"{location}, India"
                        elif not location:
                            location = 'India'

                        parsed_city, parsed_state, parsed_country = self.parse_location(
                            f"{city}, {region}" if city else location
                        )

                        job = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city or parsed_city,
                            'state': region or parsed_state,
                            'country': 'India',
                            'employment_type': employment_type,
                            'department': department,
                            'apply_url': apply_url,
                            'posted_date': posted_date,
                            'job_function': job_function,
                            'experience_level': experience_level,
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        }
                        jobs.append(job)
                        page_count += 1
                        logger.info(f"Extracted: {title} | {location} | {department}")
                    except Exception as e:
                        logger.warning(f"Error processing posting: {str(e)}")
                        continue

                logger.info(f"Page {page + 1}: found {page_count} India jobs (total: {len(jobs)})")

                # Stop if we have fetched all results
                if offset + limit >= total:
                    logger.info("Reached end of results")
                    break

                if page_count == 0 and len(postings) < limit:
                    logger.info("No more results available")
                    break

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs

if __name__ == "__main__":
    scraper = GrabScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

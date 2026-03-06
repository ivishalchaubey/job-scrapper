import requests
import hashlib
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('agility_scraper')


class AgilityScraper:
    def __init__(self):
        self.company_name = 'Agility'
        self.url = 'https://apply.workable.com/api/v3/accounts/agility/jobs'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })

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

    def _is_india_job(self, location, title=''):
        """Check if a job is India-based by its location string."""
        india_keywords = [
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
            'hyderabad', 'chennai', 'pune', 'gurugram', 'gurgaon',
            'noida', 'kolkata', 'ahmedabad', 'jaipur', 'kochi',
            'lucknow', 'chandigarh', 'indore', 'new delhi',
            'thiruvananthapuram', 'bhubaneswar', 'nagpur', 'coimbatore'
        ]
        text = (location + ' ' + title).lower()
        return any(kw in text for kw in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Agility India jobs from the Workable API.

        The Workable API at /api/v3/accounts/agility/jobs accepts POST requests
        with a JSON body. The first request sends:
            {"query":"","location":[],"department":[],"worktype":[],"remote":[]}

        The response includes a "results" array and optionally a "nextPage" token.
        For subsequent pages, send: {"token": "<nextPage_value>"}

        Each job result has:
        - shortcode: unique job identifier
        - title: job title
        - location: {"city": "...", "country": "...", "countryCode": "..."}
        - department: department name
        - worktype: Full-time, Part-time, etc.
        - shortlink: shortened URL

        Apply URL format: https://apply.workable.com/agility/j/{shortcode}/
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            seen_ids = set()

            # Initial request body
            payload = {
                'query': '',
                'location': [],
                'department': [],
                'worktype': [],
                'remote': [],
            }

            for page in range(max_pages):
                logger.info(f"Fetching page {page + 1}")
                try:
                    response = self.session.post(self.url, json=payload, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                except Exception as e:
                    logger.error(f"Failed to fetch page {page + 1}: {str(e)}")
                    break

                results = data.get('results', [])
                next_page = data.get('nextPage')
                total = data.get('total', 0)

                if not results:
                    logger.info(f"No results on page {page + 1}, stopping")
                    break

                logger.info(f"Page {page + 1}: {len(results)} jobs returned (total={total})")

                page_count = 0
                for job_data in results:
                    try:
                        title = job_data.get('title', '').strip()
                        if not title:
                            continue

                        # Extract location
                        location_obj = job_data.get('location', {})
                        if isinstance(location_obj, dict):
                            city = location_obj.get('city', '')
                            country_name = location_obj.get('country', '')
                            country_code = location_obj.get('countryCode', '')
                            location_parts = [p for p in [city, country_name] if p]
                            location = ', '.join(location_parts)
                        elif isinstance(location_obj, str):
                            location = location_obj
                            city = ''
                            country_name = ''
                            country_code = ''
                        else:
                            location = ''
                            city = ''
                            country_name = ''
                            country_code = ''

                        # Filter for India jobs
                        is_india = False
                        if country_code and country_code.upper() == 'IN':
                            is_india = True
                        elif self._is_india_job(location, title):
                            is_india = True

                        if not is_india:
                            continue

                        # Job ID (shortcode)
                        shortcode = job_data.get('shortcode', '')
                        job_id = job_data.get('id', '') or shortcode
                        if not job_id:
                            job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        # Apply URL
                        apply_url = ''
                        if shortcode:
                            apply_url = f"https://apply.workable.com/agility/j/{shortcode}/"
                        elif job_data.get('shortlink'):
                            apply_url = job_data.get('shortlink')
                        elif job_data.get('url'):
                            apply_url = job_data.get('url')
                        else:
                            apply_url = 'https://apply.workable.com/agility/'

                        # Department
                        department = ''
                        dept_val = job_data.get('department')
                        if isinstance(dept_val, str):
                            department = dept_val
                        elif isinstance(dept_val, list) and dept_val:
                            department = dept_val[0] if isinstance(dept_val[0], str) else str(dept_val[0])

                        # Employment type / work type
                        employment_type = ''
                        worktype = job_data.get('worktype', '')
                        if isinstance(worktype, str):
                            employment_type = worktype
                        elif isinstance(worktype, list) and worktype:
                            employment_type = worktype[0] if isinstance(worktype[0], str) else str(worktype[0])

                        # Posted date
                        posted_date = ''
                        published = job_data.get('published', '') or job_data.get('created_at', '')
                        if published:
                            posted_date = published[:10]

                        # Experience level
                        experience_level = ''
                        exp_val = job_data.get('experience', '')
                        if isinstance(exp_val, str):
                            experience_level = exp_val

                        # Remote type
                        remote_type = ''
                        remote_val = job_data.get('remote', False)
                        if remote_val:
                            remote_type = 'Remote'
                        elif 'remote' in title.lower():
                            remote_type = 'Remote'
                        elif 'hybrid' in title.lower():
                            remote_type = 'Hybrid'

                        # Normalize location
                        if location and 'india' not in location.lower():
                            location = f"{location}, India"
                        elif not location:
                            location = 'India'

                        parsed_city, parsed_state, parsed_country = self.parse_location(location)

                        job = {
                            'external_id': self.generate_external_id(str(job_id), self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city or parsed_city,
                            'state': parsed_state,
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
                        }
                        jobs.append(job)
                        page_count += 1
                        logger.info(f"Extracted: {title} | {location} | {department}")
                    except Exception as e:
                        logger.warning(f"Error processing job: {str(e)}")
                        continue

                logger.info(f"Page {page + 1}: found {page_count} India jobs (total: {len(jobs)})")

                # Check for next page
                if not next_page:
                    logger.info("No nextPage token, reached end of results")
                    break

                # Set up payload for next page using the token
                payload = {'token': next_page}

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs


if __name__ == "__main__":
    scraper = AgilityScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

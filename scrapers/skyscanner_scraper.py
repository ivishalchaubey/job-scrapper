import requests
import hashlib
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('skyscanner_scraper')


class SkyscannerScraper:
    def __init__(self):
        self.company_name = 'Skyscanner'
        self.url = 'https://boards-api.greenhouse.io/v1/boards/skyscanner/jobs'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Skyscanner India jobs from the Greenhouse API.

        The Greenhouse boards API at /v1/boards/skyscanner/jobs returns JSON with
        all job postings in a single response (no pagination needed). We filter
        for India jobs by checking location.name for Indian city names.

        Response structure:
        {
            "jobs": [
                {
                    "id": 12345,
                    "title": "Job Title",
                    "location": {"name": "Mumbai, India"},
                    "departments": [{"id": 1, "name": "Engineering"}],
                    "absolute_url": "https://boards.greenhouse.io/skyscanner/jobs/12345",
                    "updated_at": "2024-01-01T00:00:00-05:00",
                    "metadata": [...]
                }
            ]
        }
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            seen_ids = set()

            india_keywords = [
                'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
                'hyderabad', 'chennai', 'pune', 'gurugram', 'gurgaon',
                'noida', 'kolkata', 'ahmedabad', 'jaipur', 'kochi',
                'lucknow', 'chandigarh', 'indore', 'new delhi',
                'thiruvananthapuram', 'bhubaneswar', 'nagpur', 'coimbatore'
            ]

            logger.info(f"Fetching all jobs from Greenhouse API: {self.url}")
            try:
                response = self.session.get(self.url, timeout=30)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.error(f"Failed to fetch Greenhouse API: {str(e)}")
                return jobs

            postings = data.get('jobs', [])
            if not isinstance(postings, list):
                logger.error("Unexpected API response structure")
                return jobs

            logger.info(f"Greenhouse API returned {len(postings)} total postings")

            for posting in postings:
                try:
                    title = posting.get('title', '').strip()
                    if not title:
                        continue

                    # Extract location
                    location_obj = posting.get('location', {})
                    location_name = location_obj.get('name', '') if isinstance(location_obj, dict) else ''

                    # Also check metadata for additional location info
                    metadata_locations = []
                    metadata = posting.get('metadata', [])
                    if isinstance(metadata, list):
                        for meta in metadata:
                            if isinstance(meta, dict):
                                meta_name = meta.get('name', '').lower()
                                if 'location' in meta_name or 'country' in meta_name:
                                    value = meta.get('value')
                                    if isinstance(value, list):
                                        metadata_locations.extend(value)
                                    elif isinstance(value, str):
                                        metadata_locations.append(value)

                    # Build combined location for filtering
                    combined_location = (location_name + ' ' + ' '.join(metadata_locations)).lower()

                    # Filter for India jobs
                    is_india = any(kw in combined_location for kw in india_keywords)
                    if not is_india:
                        continue

                    # Job ID
                    job_id = str(posting.get('id', ''))
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    # Apply URL
                    absolute_url = posting.get('absolute_url', '')
                    if not absolute_url:
                        absolute_url = f"https://boards.greenhouse.io/skyscanner/jobs/{job_id}"

                    # Department
                    department = ''
                    departments = posting.get('departments', [])
                    if isinstance(departments, list) and departments:
                        dept_obj = departments[0]
                        if isinstance(dept_obj, dict):
                            department = dept_obj.get('name', '')

                    # Posted/Updated date
                    posted_date = ''
                    updated_at = posting.get('updated_at', '')
                    first_published = posting.get('first_published_at', '')
                    date_str = first_published or updated_at
                    if date_str:
                        posted_date = date_str[:10]

                    # Employment type from metadata
                    employment_type = ''
                    experience_level = ''
                    job_function = ''
                    if isinstance(metadata, list):
                        for meta in metadata:
                            if isinstance(meta, dict):
                                name = meta.get('name', '')
                                value = meta.get('value')
                                name_lower = name.lower()
                                if 'employment' in name_lower or 'type' in name_lower:
                                    if isinstance(value, list):
                                        employment_type = ', '.join(str(v) for v in value)
                                    elif value:
                                        employment_type = str(value)
                                elif 'experience' in name_lower or 'level' in name_lower or 'seniority' in name_lower:
                                    if isinstance(value, list):
                                        experience_level = ', '.join(str(v) for v in value)
                                    elif value:
                                        experience_level = str(value)
                                elif 'function' in name_lower:
                                    if isinstance(value, list):
                                        job_function = ', '.join(str(v) for v in value)
                                    elif value:
                                        job_function = str(value)

                    # Location parsing
                    location = location_name if location_name else ', '.join(metadata_locations)
                    city, state, country = self.parse_location(location)

                    if location and 'india' not in location.lower():
                        location = f"{location}, India"
                    elif not location:
                        location = 'India'

                    # Remote type
                    remote_type = ''
                    if 'remote' in title.lower() or 'remote' in location.lower():
                        remote_type = 'Remote'
                    elif 'hybrid' in title.lower() or 'hybrid' in location.lower():
                        remote_type = 'Hybrid'
                    # Also check location.name for remote indicators
                    if not remote_type and location_name:
                        loc_lower = location_name.lower()
                        if 'remote' in loc_lower:
                            remote_type = 'Remote'
                        elif 'hybrid' in loc_lower:
                            remote_type = 'Hybrid'

                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': absolute_url,
                        'posted_date': posted_date,
                        'job_function': job_function,
                        'experience_level': experience_level,
                        'salary_range': '',
                        'remote_type': remote_type,
                        'status': 'active'
                    }
                    jobs.append(job)
                    logger.info(f"Extracted: {title} | {location} | {department}")

                except Exception as e:
                    logger.warning(f"Error processing posting: {str(e)}")
                    continue

            logger.info(f"Successfully scraped {len(jobs)} India jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs


if __name__ == "__main__":
    scraper = SkyscannerScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs[:10]:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

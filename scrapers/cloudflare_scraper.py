import requests
import hashlib

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('cloudflare_scraper')


class CloudflareScraper:
    def __init__(self):
        self.company_name = 'Cloudflare'
        self.api_url = 'https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs'
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Cloudflare via Greenhouse JSON API, filtering for India."""
        all_jobs = []
        seen_ids = set()

        # India location keywords for filtering
        india_keywords = [
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
            'pune', 'hyderabad', 'noida', 'gurgaon', 'gurugram',
            'chennai', 'kolkata', 'jaipur', 'ahmedabad', 'lucknow',
            'chandigarh', 'indore', 'kochi', 'coimbatore', 'new delhi',
            'thiruvananthapuram', 'bhubaneswar', 'nagpur'
        ]

        try:
            logger.info(f"Starting {self.company_name} scraping from Greenhouse API: {self.api_url}")

            response = requests.get(self.api_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            postings = data.get('jobs', [])
            if not isinstance(postings, list):
                logger.error("Unexpected API response structure")
                return all_jobs

            logger.info(f"Greenhouse API returned {len(postings)} total postings")

            for posting in postings:
                try:
                    title = posting.get('title', '')
                    if not title:
                        continue

                    # Extract location - Cloudflare uses generic location.name like
                    # "Hybrid", "Distributed", etc. The actual city/country info is in
                    # metadata -> "Job Posting Location" (multi_select value list)
                    location_obj = posting.get('location', {})
                    work_arrangement = location_obj.get('name', '') if isinstance(location_obj, dict) else ''

                    # Check metadata for "Job Posting Location" to find India jobs
                    posting_locations = []
                    metadata = posting.get('metadata', [])
                    if isinstance(metadata, list):
                        for meta in metadata:
                            if isinstance(meta, dict) and meta.get('name') == 'Job Posting Location':
                                value = meta.get('value')
                                if isinstance(value, list):
                                    posting_locations = value
                                elif isinstance(value, str):
                                    posting_locations = [value]

                    # Build combined location string from posting locations
                    location = ', '.join(posting_locations) if posting_locations else work_arrangement

                    # Filter for India jobs using posting locations (primary) and location name (fallback)
                    combined_location = ' '.join(posting_locations).lower() + ' ' + location.lower()
                    is_india = any(kw in combined_location for kw in india_keywords)
                    if not is_india:
                        continue

                    job_id = str(posting.get('id', ''))
                    if not job_id:
                        job_id = f"cloudflare_{hashlib.md5(title.encode()).hexdigest()[:12]}"

                    external_id = self.generate_external_id(job_id, self.company_name)
                    if external_id in seen_ids:
                        continue

                    absolute_url = posting.get('absolute_url', '')
                    updated_at = posting.get('updated_at', '')
                    first_published = posting.get('first_published', '')

                    # Parse date
                    posted_date = ''
                    date_str = first_published or updated_at
                    if date_str:
                        try:
                            posted_date = date_str[:10]
                        except Exception:
                            pass

                    # Extract metadata for department/employment type
                    # (metadata was already fetched above for location filtering)
                    department = ''
                    employment_type = ''
                    if isinstance(metadata, list):
                        for meta in metadata:
                            if isinstance(meta, dict):
                                name = meta.get('name', '')
                                value = meta.get('value')
                                if name == 'Career Site Department' and value:
                                    if isinstance(value, list):
                                        department = ', '.join(str(v) for v in value)
                                    else:
                                        department = str(value)
                                elif 'employment' in name.lower() and value:
                                    employment_type = str(value)

                    # Try departments array from Greenhouse
                    if not department:
                        departments = posting.get('departments', [])
                        if isinstance(departments, list) and departments:
                            dept_obj = departments[0]
                            if isinstance(dept_obj, dict):
                                department = dept_obj.get('name', '')

                    location_parts = self.parse_location(location)

                    job_data = {
                        'external_id': external_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': location_parts['city'],
                        'state': location_parts['state'],
                        'country': location_parts['country'],
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': absolute_url if absolute_url else f'https://boards.greenhouse.io/cloudflare/jobs/{job_id}',
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': work_arrangement,
                        'status': 'active'
                    }

                    all_jobs.append(job_data)
                    seen_ids.add(external_id)
                    logger.info(f"Extracted: {title} | {location}")

                except Exception as e:
                    logger.error(f"Error processing posting: {str(e)}")
                    continue

            logger.info(f"Successfully scraped {len(all_jobs)} India jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs


if __name__ == "__main__":
    scraper = CloudflareScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs[:10]:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

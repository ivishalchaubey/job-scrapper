import requests
import hashlib

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE

logger = setup_logger('godaddy_scraper')


class GoDaddyScraper:
    def __init__(self):
        self.company_name = "GoDaddy"
        self.url = "https://careers.godaddy/jobs/search?page=1&query=&country_codes%5B%5D=IN"
        self.api_url = 'https://boards-api.greenhouse.io/v1/boards/godaddy/jobs'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name} via Greenhouse API")
            headers = {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            }
            response = requests.get(self.api_url, headers=headers, timeout=SCRAPE_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            postings = data.get('jobs', [])
            logger.info(f"Greenhouse API returned {len(postings)} total postings")

            india_keywords = ['India', 'Bangalore', 'Bengaluru', 'Mumbai', 'Delhi',
                            'Hyderabad', 'Chennai', 'Pune', 'Gurugram', 'Gurgaon',
                            'Noida', 'Kolkata', 'Ahmedabad', 'Jaipur', 'Kochi',
                            'Thiruvananthapuram', 'Chandigarh', 'Lucknow', 'Indore']

            for posting in postings:
                try:
                    title = posting.get('title', '')
                    if not title:
                        continue

                    location_obj = posting.get('location', {})
                    location = location_obj.get('name', '') if isinstance(location_obj, dict) else ''

                    # Filter for India jobs
                    if not any(kw in location for kw in india_keywords):
                        continue

                    job_id = str(posting.get('id', ''))
                    if not job_id:
                        job_id = f"godaddy_{hashlib.md5(title.encode()).hexdigest()[:12]}"

                    absolute_url = posting.get('absolute_url', '')
                    updated_at = posting.get('updated_at', '')
                    first_published = posting.get('first_published', '')

                    posted_date = ''
                    date_str = first_published or updated_at
                    if date_str:
                        posted_date = date_str[:10]

                    department = ''
                    employment_type = ''
                    metadata = posting.get('metadata', [])
                    if isinstance(metadata, list):
                        for meta in metadata:
                            if isinstance(meta, dict):
                                name_key = meta.get('name', '').lower()
                                value = meta.get('value')
                                if 'department' in name_key and value:
                                    department = str(value)
                                elif 'employment' in name_key and value:
                                    employment_type = str(value)

                    location_parts = self.parse_location(location)

                    all_jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': location_parts.get('city', ''),
                        'state': location_parts.get('state', ''),
                        'country': location_parts.get('country', 'India'),
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': absolute_url if absolute_url else self.url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error processing posting: {str(e)}")
                    continue

            logger.info(f"Successfully scraped {len(all_jobs)} India jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
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
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = GoDaddyScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs[:10]:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

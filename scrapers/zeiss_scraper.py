import requests
import hashlib
import re
import time

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('zeiss_scraper')


class ZeissScraper:
    def __init__(self):
        self.company_name = 'Zeiss'
        self.workday_api_url = 'https://zeissgroup.wd3.myworkdayjobs.com/wday/cxs/zeissgroup/External/jobs'
        self.workday_base_url = 'https://zeissgroup.wd3.myworkdayjobs.com/External'
        # India country facet ID from Workday
        self.india_country_facet = 'c4f78be1a8f14da0ab49ce1162348a5e'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        location_str = location_str.strip()
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) == 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Zeiss via Workday JSON API."""
        all_jobs = []
        scraped_ids = set()
        page_size = 20
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

        try:
            logger.info(f"Starting Workday API scrape for {self.company_name}")

            for page in range(max_pages):
                offset = page * page_size

                payload = {
                    'appliedFacets': {
                        'locationCountry': [self.india_country_facet]
                    },
                    'limit': page_size,
                    'offset': offset,
                    'searchText': ''
                }

                response = session.post(self.workday_api_url, json=payload, timeout=30)
                if response.status_code != 200:
                    logger.error(f"Workday API returned status {response.status_code}")
                    break

                data = response.json()
                total = data.get('total', 0)
                job_postings = data.get('jobPostings', [])

                if not job_postings:
                    logger.info(f"No more jobs at offset {offset}")
                    break

                for job_item in job_postings:
                    parsed = self._parse_workday_job(job_item, scraped_ids)
                    if parsed:
                        all_jobs.append(parsed)

                logger.info(f"Page {page + 1}: {len(job_postings)} jobs (total fetched: {len(all_jobs)}/{total})")

                if offset + page_size >= total:
                    break

                time.sleep(1)

            logger.info(f"Successfully scraped {len(all_jobs)} jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _parse_workday_job(self, job_item, scraped_ids):
        """Parse a single job posting from the Workday API response."""
        try:
            title = (job_item.get('title') or '').strip()
            if not title:
                return None

            external_path = (job_item.get('externalPath') or '').strip()
            if not external_path:
                return None

            # Extract job ID from externalPath like /job/Bangalore/Title_JR_1047452
            job_id = ''
            bullet_fields = job_item.get('bulletFields', [])
            if bullet_fields:
                job_id = bullet_fields[0]
            if not job_id:
                id_match = re.search(r'_([A-Z]+_\d+)(?:-\d+)?$', external_path)
                if id_match:
                    job_id = id_match.group(1)
                else:
                    job_id = hashlib.md5(external_path.encode()).hexdigest()[:12]

            ext_id = self.generate_external_id(job_id, self.company_name)
            if ext_id in scraped_ids:
                return None
            scraped_ids.add(ext_id)

            # Build apply URL
            apply_url = f"{self.workday_base_url}{external_path}"

            # Location
            locations_text = (job_item.get('locationsText') or '').strip()
            loc_data = self.parse_location(locations_text)

            # Posted date
            posted_on = (job_item.get('postedOn') or '').strip()

            # Remote type
            remote_type = (job_item.get('remoteType') or '').strip()

            return {
                'external_id': ext_id,
                'company_name': self.company_name,
                'title': title,
                'description': '',
                'location': locations_text if locations_text else 'India',
                'city': loc_data.get('city', ''),
                'state': loc_data.get('state', ''),
                'country': 'India',
                'employment_type': '',
                'department': '',
                'apply_url': apply_url,
                'posted_date': posted_on,
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': remote_type,
                'status': 'active'
            }
        except Exception as e:
            logger.error(f"Error parsing Workday job: {str(e)}")
            return None


if __name__ == "__main__":
    scraper = ZeissScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['posted_date']}")

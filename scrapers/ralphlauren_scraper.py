import requests
import hashlib
import re
import html
import time

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('ralphlauren_scraper')


class RalphLaurenScraper:
    def __init__(self):
        self.company_name = "Ralph Lauren Corporation"
        self.base_url = 'https://careers.ralphlauren.com'
        # 3413=3312571 is the country filter for India in Avature
        self.search_url = f'{self.base_url}/CareersCorporate/SearchJobsCorporate/'
        self.india_filter = '3413'
        self.india_value = '3312571'

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
        """Scrape jobs from Ralph Lauren India via Avature server-rendered HTML."""
        all_jobs = []
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        seen_ids = set()
        page_size = 20

        try:
            logger.info(f"Starting scrape for {self.company_name}")

            for page in range(max_pages):
                offset = page * page_size
                params = {
                    self.india_filter: self.india_value,
                }
                if offset > 0:
                    # Avature uses a different parameter format for pagination
                    params = {
                        '3_156_3': self.india_value,
                        '3_156_3_format': '1848',
                        'jobOffset': str(offset),
                    }

                response = session.get(self.search_url, params=params, timeout=30)
                if response.status_code != 200:
                    logger.error(f"Page returned status {response.status_code}")
                    break

                page_jobs = self._parse_html_jobs(response.text, seen_ids)
                if not page_jobs:
                    logger.info(f"No more jobs found on page {page + 1}")
                    break

                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                # Check if there's a next page
                if 'paginationNextLink' not in response.text:
                    logger.info("No more pagination links found")
                    break

                time.sleep(1)

            logger.info(f"Successfully scraped {len(all_jobs)} jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _parse_html_jobs(self, page_html, seen_ids):
        """Parse job listings from Avature HTML."""
        jobs = []

        # Find all JobDetail links - pattern:
        # <a href="https://careers.ralphlauren.com/CareersCorporate/JobDetail/SLUG/ID">Title</a>
        # There are duplicate links (one as title, one as "Read more") - deduplicate by ID
        job_link_pattern = re.compile(
            r'<a\s+href="(https://careers\.ralphlauren\.com/CareersCorporate/JobDetail/[^"]+/(\d+))"'
            r'[^>]*>([^<]+)</a>',
            re.DOTALL
        )

        for match in job_link_pattern.finditer(page_html):
            href = match.group(1)
            job_id = match.group(2)
            link_text = html.unescape(match.group(3)).strip()

            if job_id in seen_ids:
                continue

            # Skip "Read more" links
            if link_text.lower().startswith('read more'):
                continue

            if not link_text or len(link_text) < 3:
                continue

            seen_ids.add(job_id)

            # Try to extract location from title text
            # Many titles include location like "Title, Bangalore , India (Hybrid)"
            title = link_text
            location = ''
            remote_type = ''

            # Check for location patterns in the title
            loc_match = re.search(
                r',\s*((?:Bangalore|Bengaluru|Mumbai|Delhi|Hyderabad|Pune|Chennai|'
                r'Gurugram|Gurgaon|Noida|Kolkata|Ahmedabad|New Delhi|India)[^()]*)',
                title, re.IGNORECASE
            )
            if loc_match:
                location = loc_match.group(1).strip().rstrip(',').strip()
                # Clean up: remove location from title
                title = title[:loc_match.start()].strip().rstrip(',').strip()

            # Check for remote type in parentheses
            remote_match = re.search(r'\((\s*(?:Hybrid|Remote|On-?site)\s*)\)', link_text, re.IGNORECASE)
            if remote_match:
                remote_type = remote_match.group(1).strip()
                # Remove the remote type from location if it's there
                location = re.sub(r'\s*\((?:Hybrid|Remote|On-?site)\)', '', location, flags=re.IGNORECASE).strip()

            if not location:
                location = 'India'

            city, state, country = self.parse_location(location)

            jobs.append({
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'description': '',
                'location': location,
                'city': city,
                'state': state,
                'country': country,
                'employment_type': '',
                'department': '',
                'apply_url': href,
                'posted_date': '',
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': remote_type,
                'status': 'active'
            })

        return jobs


if __name__ == "__main__":
    scraper = RalphLaurenScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['remote_type']}")

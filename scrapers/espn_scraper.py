import requests
from bs4 import BeautifulSoup
import hashlib
import time
import re

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('espn_scraper')


class ESPNScraper:
    def __init__(self):
        self.company_name = 'ESPN'
        self.base_url = 'https://jobs.disneycareers.com'
        # ESPN jobs filtered via TalentBrew ascf parameter
        self.url_template = 'https://jobs.disneycareers.com/search-jobs?ascf=[{{"key":"custom_fields.IndustryCustomField","value":"ESPN"}}]&p={page}'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
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
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result

    def _is_india_job(self, location_str):
        """Check if the job location indicates India."""
        if not location_str:
            return False
        india_keywords = [
            'india', 'mumbai', 'bangalore', 'bengaluru', 'hyderabad', 'chennai',
            'delhi', 'new delhi', 'noida', 'gurugram', 'gurgaon', 'pune',
            'kolkata', 'ahmedabad', 'jaipur', 'kochi', 'thiruvananthapuram',
            'chandigarh', 'lucknow', 'indore', 'bhopal', 'coimbatore',
            'vizag', 'visakhapatnam', 'nagpur', 'surat', 'vadodara'
        ]
        location_lower = location_str.lower()
        return any(kw in location_lower for kw in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        try:
            logger.info(f"Starting {self.company_name} scraping (server-rendered TalentBrew)")

            for page in range(1, max_pages + 1):
                url = self.url_template.format(page=page)
                logger.info(f"Fetching page {page}: {url}")

                response = self.session.get(url, timeout=30)
                response.raise_for_status()

                page_jobs = self._extract_jobs(response.text)
                if not page_jobs:
                    logger.info(f"No more jobs on page {page}, stopping.")
                    break

                all_jobs.extend(page_jobs)
                logger.info(f"Page {page}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if page < max_pages:
                    time.sleep(2)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")

        return all_jobs

    def _extract_jobs(self, html):
        jobs = []
        soup = BeautifulSoup(html, 'html.parser')

        # TalentBrew/Disney Careers structure:
        # <table> with <tbody> containing <tr> rows
        # Each row has: <td> with <a data-job-id="..." href="/job/..."><h2>Title</h2></a>
        #               <td> with <span class="job-date-posted">date</span>
        #               <td> with <span class="job-brand">brand</span>
        #               <td> with <span class="job-location">location</span>
        rows = soup.select('tbody tr')
        if not rows:
            # Fallback: try finding job links directly
            rows = []
            job_links = soup.select('a[data-job-id]')
            for link in job_links:
                row = link.find_parent('tr')
                if row and row not in rows:
                    rows.append(row)

        logger.info(f"Found {len(rows)} job rows in HTML")

        seen_ids = set()
        for row in rows:
            try:
                # Find job link
                link = row.select_one('a[data-job-id]')
                if not link:
                    link = row.select_one('a[href*="/job/"]')
                if not link:
                    continue

                job_id = link.get('data-job-id', '')
                href = link.get('href', '')
                if not href:
                    continue

                if job_id in seen_ids:
                    continue
                if job_id:
                    seen_ids.add(job_id)

                # Get title from h2 inside the link, or link text
                title_el = link.select_one('h2, h3, h4')
                title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                title = title.split('\n')[0].strip()
                if not title or len(title) < 3 or len(title) > 200:
                    continue

                # Get location
                loc_el = row.select_one('.job-location, span[class*="location"]')
                location = loc_el.get_text(strip=True) if loc_el else ''

                # Get date
                date_el = row.select_one('.job-date-posted, span[class*="date"]')
                date_posted = date_el.get_text(strip=True) if date_el else ''

                # Get brand/department
                brand_el = row.select_one('.job-brand, span[class*="brand"]')
                department = brand_el.get_text(strip=True) if brand_el else 'ESPN'

                # Build full URL
                url = href if href.startswith('http') else f"{self.base_url}{href}"

                # Filter for India jobs
                if location and not self._is_india_job(location):
                    continue

                if not job_id:
                    job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                loc_data = self.parse_location(location)
                jobs.append({
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': location,
                    'city': loc_data.get('city', ''),
                    'state': loc_data.get('state', ''),
                    'country': loc_data.get('country', 'India'),
                    'employment_type': '',
                    'department': department,
                    'apply_url': url,
                    'posted_date': date_posted,
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                })

            except Exception as e:
                logger.error(f"Error parsing job row: {str(e)}")
                continue

        if not jobs:
            logger.info("No India-based ESPN jobs found on this page (this may be expected)")

        return jobs


if __name__ == "__main__":
    scraper = ESPNScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

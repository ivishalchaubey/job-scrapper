import requests
import hashlib
from bs4 import BeautifulSoup

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('indegene_scraper')

class IndegeneScraper:
    def __init__(self):
        self.company_name = "Indegene"
        self.base_url = 'https://careers.indegene.com'
        self.search_url = 'https://careers.indegene.com/search/?q=&locationsearch=&optionsFacetsDD_location=&optionsFacetsDD_country=IN&startrow={offset}'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        self.page_size = 25
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

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

    def _extract_job_id(self, job_url):
        """Extract numeric job ID from SAP SuccessFactors URL."""
        job_id = ''
        if '/job/' in job_url:
            parts = job_url.rstrip('/').split('/')
            for part in reversed(parts):
                if part.isdigit():
                    job_id = part
                    break
        if not job_id:
            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]
        return job_id

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Indegene SAP SuccessFactors career site."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping via HTTP requests")

            for page in range(max_pages):
                offset = page * self.page_size
                url = self.search_url.format(offset=offset)
                logger.info(f"Fetching page {page + 1} (startrow={offset})")

                try:
                    response = requests.get(url, headers=self.headers, timeout=30)
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request failed on page {page + 1}: {str(e)}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # SAP SuccessFactors selectors
                results_table = soup.select_one('table#searchresults')
                if results_table:
                    job_rows = results_table.select('tr.data-row')
                else:
                    job_rows = soup.select('tr.data-row')

                if not job_rows:
                    logger.info(f"No job rows found on page {page + 1}, stopping pagination")
                    break

                logger.info(f"Page {page + 1}: found {len(job_rows)} job rows")
                page_jobs = 0

                for row in job_rows:
                    try:
                        # Extract title and URL
                        title_link = row.select_one('a.jobTitle-link') or row.select_one('span.jobTitle a')
                        if not title_link:
                            continue

                        title = title_link.get_text(strip=True)
                        href = title_link.get('href', '')
                        if not title or not href:
                            continue

                        # Build full URL if relative
                        if href.startswith('/'):
                            job_url = self.base_url + href
                        else:
                            job_url = href

                        # Extract job ID
                        job_id = self._extract_job_id(href)
                        external_id = self.generate_external_id(job_id, self.company_name)

                        if external_id in seen_ids:
                            continue

                        # Extract location
                        location = ''
                        loc_elem = row.select_one('span.jobLocation')
                        if loc_elem:
                            location = loc_elem.get_text(strip=True)

                        # Extract posted date
                        posted_date = ''
                        date_elem = row.select_one('span.jobDate')
                        if date_elem:
                            posted_date = date_elem.get_text(strip=True)

                        # Extract department
                        department = ''
                        dept_elem = row.select_one('span.jobDepartment')
                        if dept_elem:
                            department = dept_elem.get_text(strip=True)

                        # Parse location into components
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
                            'employment_type': '',
                            'department': department,
                            'apply_url': job_url,
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }

                        all_jobs.append(job_data)
                        seen_ids.add(external_id)
                        page_jobs += 1
                        logger.info(f"Extracted: {title} | {location}")

                    except Exception as e:
                        logger.error(f"Error parsing job row: {str(e)}")
                        continue

                logger.info(f"Page {page + 1}: extracted {page_jobs} new jobs (total: {len(all_jobs)})")

                if page_jobs == 0:
                    logger.info("No new jobs found on this page, stopping")
                    break

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

if __name__ == "__main__":
    scraper = IndegeneScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['apply_url']}")

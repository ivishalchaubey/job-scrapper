import requests
import hashlib
import re
import time

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import MAX_PAGES_TO_SCRAPE, HEADLESS_MODE

logger = setup_logger('questdiagnostics_scraper')

class QuestDiagnosticsScraper:
    def __init__(self):
        self.company_name = "Quest Diagnostics"
        self.base_url = 'https://indiacareers.questdiagnostics.com'
        self.search_url = f'{self.base_url}/search-jobs/results'
        self.location_url = f'{self.base_url}/location/india-jobs/38852/1269750/2'
    
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
        """Scrape jobs from Quest Diagnostics India via TalentBrew server-rendered HTML."""
        all_jobs = []
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })

        try:
            logger.info(f"Starting scrape for {self.company_name}")

            # First, fetch the location page directly (server-rendered HTML with jobs)
            response = session.get(self.location_url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Location page returned status {response.status_code}")
                return all_jobs

            page_jobs = self._parse_html_jobs(response.text)
            all_jobs.extend(page_jobs)
            logger.info(f"Page 1: {len(page_jobs)} jobs")

            # Check for total pages from search-results section
            total_pages_match = re.search(r'data-total-pages="(\d+)"', response.text)
            total_pages = int(total_pages_match.group(1)) if total_pages_match else 1

            # If there are more pages, use the AJAX search API
            if total_pages > 1:
                for page in range(2, min(total_pages + 1, max_pages + 1)):
                    try:
                        ajax_params = {
                            'ActiveFacetID': '0',
                            'CurrentPage': str(page),
                            'RecordsPerPage': '20',
                            'Distance': '50',
                            'RadiusUnitType': '0',
                            'Keywords': '',
                            'Location': '',
                            'ShowRadius': 'False',
                            'IsPagination': 'True',
                            'SearchResultsModuleName': 'Search Results',
                            'SearchFiltersModuleName': 'Search Filters',
                            'SortCriteria': '0',
                            'SortDirection': '0',
                            'SearchType': '3',
                            'PostalCode': '',
                            'ResultsType': '0',
                            'fc': '',
                            'fl': '1269750',
                            'fcf': '',
                            'afc': '',
                            'afl': '',
                            'afcf': '',
                        }
                        ajax_headers = {
                            'Accept': 'application/json, text/javascript, */*; q=0.01',
                            'X-Requested-With': 'XMLHttpRequest',
                        }
                        resp = session.get(self.search_url, params=ajax_params,
                                           headers=ajax_headers, timeout=30)
                        if resp.status_code == 200:
                            data = resp.json()
                            results_html = data.get('results', '')
                            page_jobs = self._parse_html_jobs(results_html)
                            if not page_jobs:
                                break
                            all_jobs.extend(page_jobs)
                            logger.info(f"Page {page}: {len(page_jobs)} jobs (total: {len(all_jobs)})")
                        else:
                            break
                        time.sleep(1)
                    except Exception as e:
                        logger.error(f"AJAX page {page} failed: {str(e)}")
                        break

            logger.info(f"Successfully scraped {len(all_jobs)} jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _parse_html_jobs(self, html):
        """Parse job listings from TalentBrew HTML."""
        jobs = []
        seen_ids = set()

        # Pattern: <a href="/job/city/title/orgid/jobid" data-job-id="jobid">
        #            <h2>Title</h2>
        #            <span class="job-info">WorkMode</span>
        #            <span class="job-location-info">Location</span>
        #            <span class="job-date-posted">Date</span>
        #          </a>

        # Find all job links with data-job-id
        job_pattern = re.compile(
            r'<a\s+href="(/job/[^"]+)"\s+data-job-id="(\d+)"[^>]*>'
            r'(.*?)</a>',
            re.DOTALL
        )

        for match in job_pattern.finditer(html):
            href = match.group(1)
            job_id = match.group(2)
            inner_html = match.group(3)

            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            # Extract title from <h2>
            title_match = re.search(r'<h2[^>]*>(.*?)</h2>', inner_html, re.DOTALL)
            title = ''
            if title_match:
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

            if not title or len(title) < 3:
                continue

            # Extract location
            loc_match = re.search(r'class="job-location-info"[^>]*>(.*?)</span>', inner_html, re.DOTALL)
            location = ''
            if loc_match:
                location = re.sub(r'<[^>]+>', '', loc_match.group(1)).strip()

            # Extract work mode
            work_mode_match = re.search(r'class="job-info"[^>]*>(.*?)</span>', inner_html, re.DOTALL)
            work_mode = ''
            if work_mode_match:
                work_mode = re.sub(r'<[^>]+>', '', work_mode_match.group(1)).strip()

            # Extract date
            date_match = re.search(r'class="job-date-posted"[^>]*>(.*?)</span>', inner_html, re.DOTALL)
            posted_date = ''
            if date_match:
                posted_date = re.sub(r'<[^>]+>', '', date_match.group(1)).strip()

            apply_url = f"{self.base_url}{href}"
            city, state, country = self.parse_location(location)

            # Determine remote type from work mode
            remote_type = ''
            if work_mode:
                wm_lower = work_mode.lower()
                if 'remote' in wm_lower:
                    remote_type = 'Remote'
                elif 'hybrid' in wm_lower:
                    remote_type = 'Hybrid'
                elif 'on-site' in wm_lower or 'onsite' in wm_lower:
                    remote_type = 'On-site'

            jobs.append({
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'description': '',
                'location': location if location else 'India',
                'city': city,
                'state': state,
                'country': country,
                'employment_type': '',
                'department': '',
                'apply_url': apply_url,
                'posted_date': posted_date,
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': remote_type,
                'status': 'active'
            })

        return jobs

if __name__ == "__main__":
    scraper = QuestDiagnosticsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['posted_date']}")

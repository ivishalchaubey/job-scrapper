from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
from datetime import datetime
from pathlib import Path

try:
    import requests as req_lib
except ImportError:
    req_lib = None

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('phonepe_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class PhonePeScraper:
    def __init__(self):
        self.company_name = 'PhonePe'
        self.url = 'https://www.phonepe.com/careers/'
        self.api_url = 'https://boards-api.greenhouse.io/v1/boards/phonepe/jobs'

    def setup_driver(self):
        """Set up Chrome driver with options"""
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=AppleWebKit/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])

        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Auto-detect failed: {str(e)}, trying explicit path")
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from PhonePe via Greenhouse JSON API (primary) or Selenium (fallback)."""
        # Primary method: Greenhouse JSON API via requests
        if req_lib is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"Greenhouse API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("Greenhouse API returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.warning(f"Greenhouse API method failed: {str(e)}, falling back to Selenium")
        else:
            logger.warning("requests library not available, using Selenium only")

        # Fallback: Selenium-based scraping
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape PhonePe jobs using Greenhouse JSON API directly."""
        all_jobs = []

        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        }

        try:
            logger.info(f"Fetching all PhonePe postings from Greenhouse API: {self.api_url}")
            response = req_lib.get(self.api_url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            postings = data.get('jobs', [])
            if not isinstance(postings, list):
                logger.error(f"Unexpected API response structure")
                return all_jobs

            logger.info(f"Greenhouse API returned {len(postings)} total postings")

            # India location keywords for filtering
            india_keywords = ['india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
                              'pune', 'hyderabad', 'noida', 'gurgaon', 'gurugram',
                              'chennai', 'kolkata', 'jaipur', 'ahmedabad', 'lucknow',
                              'chandigarh', 'indore', 'kochi', 'coimbatore']

            for posting in postings:
                try:
                    title = posting.get('title', '')
                    if not title:
                        continue

                    location_obj = posting.get('location', {})
                    location = location_obj.get('name', '') if isinstance(location_obj, dict) else ''

                    # Filter for India jobs
                    location_lower = location.lower()
                    is_india = any(kw in location_lower for kw in india_keywords)
                    # PhonePe is an Indian company - if location is generic, include it
                    if not location:
                        is_india = True
                    if not is_india:
                        continue

                    job_id = str(posting.get('id', ''))
                    if not job_id:
                        job_id = f"phonepe_{hashlib.md5(title.encode()).hexdigest()[:12]}"

                    absolute_url = posting.get('absolute_url', '')
                    updated_at = posting.get('updated_at', '')
                    requisition_id = posting.get('requisition_id', '')
                    first_published = posting.get('first_published', '')

                    # Parse date
                    posted_date = ''
                    date_str = first_published or updated_at
                    if date_str:
                        try:
                            # Greenhouse format: "2025-01-15T10:30:00-05:00"
                            posted_date = date_str[:10]
                        except Exception:
                            pass

                    # Extract metadata for department/employment type
                    department = ''
                    employment_type = ''
                    metadata = posting.get('metadata', [])
                    if isinstance(metadata, list):
                        for meta in metadata:
                            if isinstance(meta, dict):
                                name = meta.get('name', '').lower()
                                value = meta.get('value')
                                if 'department' in name and value:
                                    department = str(value)
                                elif 'employment' in name and value:
                                    employment_type = str(value)

                    # Try to get employment info from the posting directly
                    if not employment_type:
                        emp = posting.get('employment', {})
                        if isinstance(emp, dict):
                            employment_type = emp.get('name', '')

                    location_parts = self.parse_location(location)

                    job_data = {
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
                    }

                    all_jobs.append(job_data)
                    logger.info(f"Added job: {title} | {location}")

                except Exception as e:
                    logger.error(f"Error processing posting: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Greenhouse API request failed: {str(e)}")

        logger.info(f"Total India jobs from Greenhouse API: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: scrape PhonePe jobs using Selenium on the Greenhouse board."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            greenhouse_url = 'https://boards.greenhouse.io/phonepe'
            logger.info(f"Starting {self.company_name} Selenium scraping from {greenhouse_url}")

            driver.get(greenhouse_url)
            time.sleep(10)

            # Extract jobs from Greenhouse board page
            js_jobs = driver.execute_script("""
                var results = [];
                // Greenhouse board uses sections with department headers and job links
                var sections = document.querySelectorAll('section.level-0');
                for (var s = 0; s < sections.length; s++) {
                    var section = sections[s];
                    var deptEl = section.querySelector('h2, h3');
                    var department = deptEl ? deptEl.innerText.trim() : '';
                    var openings = section.querySelectorAll('.opening a');
                    for (var j = 0; j < openings.length; j++) {
                        var link = openings[j];
                        var title = link.innerText.trim();
                        var url = link.href || '';
                        var locEl = link.closest('.opening');
                        var location = '';
                        if (locEl) {
                            var locSpan = locEl.querySelector('.location');
                            location = locSpan ? locSpan.innerText.trim() : '';
                        }
                        if (title.length >= 3) {
                            results.push({
                                title: title, url: url, location: location,
                                department: department
                            });
                        }
                    }
                }
                // Fallback: generic link extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/jobs/"]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        if (text.length >= 3 && text.length < 200) {
                            results.push({
                                title: text, url: links[i].href,
                                location: '', department: ''
                            });
                        }
                    }
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"Selenium found {len(js_jobs)} Greenhouse postings")
                seen_titles = set()
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    url = job_data.get('url', '')
                    location = job_data.get('location', '')

                    job_id = f"phonepe_{idx}"
                    if url and '/jobs/' in url:
                        parts = url.rstrip('/').split('/')
                        job_id = parts[-1] if parts else job_id

                    city, state, _ = self.parse_location_tuple(location)

                    all_jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': '',
                        'department': job_data.get('department', ''),
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            logger.info(f"Total jobs scraped via Selenium: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during Selenium scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def parse_location(self, location_str):
        """Parse location string into dict with city, state, country."""
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result

        location_str = location_str.strip()
        parts = [p.strip() for p in location_str.split(',')]

        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 2:
            result['state'] = parts[1]
        if len(parts) >= 3:
            result['country'] = parts[2]

        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'

        return result

    def parse_location_tuple(self, location_str):
        """Parse location string into (city, state, country) tuple."""
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'


if __name__ == "__main__":
    scraper = PhonePeScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs[:10]:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

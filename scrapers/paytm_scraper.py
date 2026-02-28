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

logger = setup_logger('paytm_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class PaytmScraper:
    def __init__(self):
        self.company_name = 'Paytm'
        self.url = 'https://jobs.lever.co/paytm'
        self.api_url = 'https://api.lever.co/v0/postings/paytm?mode=json'

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
        """Scrape jobs from Paytm via Lever JSON API (primary) or Selenium (fallback)."""
        # Primary method: Lever JSON API via requests
        if req_lib is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"Lever API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("Lever API returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.warning(f"Lever API method failed: {str(e)}, falling back to Selenium")
        else:
            logger.warning("requests library not available, using Selenium only")

        # Fallback: Selenium-based scraping
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Paytm jobs using Lever JSON API directly."""
        all_jobs = []

        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        }

        try:
            logger.info(f"Fetching all Paytm postings from Lever API: {self.api_url}")
            response = req_lib.get(self.api_url, headers=headers, timeout=30)
            response.raise_for_status()
            postings = response.json()

            if not isinstance(postings, list):
                logger.error(f"Unexpected API response type: {type(postings)}")
                return all_jobs

            logger.info(f"Lever API returned {len(postings)} total postings")

            # Filter for India-based jobs
            india_keywords = ['india', 'noida', 'delhi', 'mumbai', 'bangalore', 'bengaluru',
                              'pune', 'hyderabad', 'gurgaon', 'gurugram', 'chennai', 'kolkata',
                              'jaipur', 'ahmedabad', 'lucknow', 'chandigarh', 'indore',
                              'uttar pradesh', 'maharashtra', 'karnataka', 'telangana',
                              'tamil nadu', 'haryana', 'rajasthan', 'west bengal']

            for posting in postings:
                try:
                    title = posting.get('text', '')
                    if not title:
                        continue

                    categories = posting.get('categories', {})
                    location = categories.get('location', '')
                    country = posting.get('country', '')

                    # Filter for India
                    location_lower = location.lower()
                    is_india = (
                        country == 'IN' or
                        any(kw in location_lower for kw in india_keywords)
                    )
                    if not is_india:
                        continue

                    job_id = posting.get('id', '')
                    if not job_id:
                        job_id = f"paytm_{hashlib.md5(title.encode()).hexdigest()[:12]}"

                    department = categories.get('department', '')
                    team = categories.get('team', '')
                    commitment = categories.get('commitment', '')
                    workplace_type = posting.get('workplaceType', '')
                    hosted_url = posting.get('hostedUrl', '')
                    apply_url = posting.get('applyUrl', hosted_url)
                    created_at = posting.get('createdAt', 0)

                    # Parse createdAt timestamp (milliseconds)
                    posted_date = ''
                    if created_at:
                        try:
                            posted_date = datetime.fromtimestamp(created_at / 1000).strftime('%Y-%m-%d')
                        except Exception:
                            pass

                    # Map workplaceType to remote_type
                    remote_type = ''
                    if workplace_type == 'onsite':
                        remote_type = 'On-site'
                    elif workplace_type == 'remote':
                        remote_type = 'Remote'
                    elif workplace_type == 'hybrid':
                        remote_type = 'Hybrid'

                    # Map commitment to employment_type
                    employment_type = ''
                    if commitment:
                        commitment_lower = commitment.lower()
                        if 'full' in commitment_lower:
                            employment_type = 'Full Time'
                        elif 'part' in commitment_lower:
                            employment_type = 'Part Time'
                        elif 'intern' in commitment_lower:
                            employment_type = 'Intern'
                        elif 'contract' in commitment_lower:
                            employment_type = 'Contract'
                        else:
                            employment_type = commitment

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
                        'department': department if department else team,
                        'apply_url': apply_url if apply_url else self.url,
                        'posted_date': posted_date,
                        'job_function': team if department and team else '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': remote_type,
                        'status': 'active'
                    }

                    all_jobs.append(job_data)
                    logger.info(f"Added job: {title} | {location}")

                except Exception as e:
                    logger.error(f"Error processing posting: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Lever API request failed: {str(e)}")

        logger.info(f"Total India jobs from Lever API: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: scrape Paytm jobs from Lever page using Selenium."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")

            driver.get(self.url)
            time.sleep(10)

            # Scroll to load all Lever postings
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Extract jobs from Lever page using JavaScript
            js_jobs = driver.execute_script("""
                var results = [];
                var postings = document.querySelectorAll('.posting');
                for (var i = 0; i < postings.length; i++) {
                    var posting = postings[i];
                    var titleEl = posting.querySelector('.posting-title h5, h5');
                    var title = titleEl ? titleEl.innerText.trim() : '';
                    var linkEl = posting.querySelector('a.posting-title, a[href*="lever.co"]');
                    var url = linkEl ? linkEl.href : '';
                    if (!title && linkEl) title = (linkEl.innerText || '').trim().split('\\n')[0];
                    var locEl = posting.querySelector('.posting-categories .sort-by-time, .location');
                    var location = locEl ? locEl.innerText.trim() : '';
                    var deptEl = posting.querySelector('.posting-categories .department');
                    var department = deptEl ? deptEl.innerText.trim() : '';
                    var text = (posting.innerText || '').trim();
                    var empType = '';
                    if (text.includes('FULL TIME')) empType = 'Full Time';
                    else if (text.includes('INTERN')) empType = 'Intern';
                    else if (text.includes('CONTRACT')) empType = 'Contract';
                    if (title.length >= 3) {
                        results.push({
                            title: title, url: url, location: location,
                            department: department, employment_type: empType
                        });
                    }
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"Selenium found {len(js_jobs)} Lever postings")
                seen_titles = set()
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    url = job_data.get('url', '')
                    location = job_data.get('location', '')

                    job_id = f"paytm_{idx}"
                    if url and 'lever.co' in url:
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
                        'employment_type': job_data.get('employment_type', ''),
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
    scraper = PaytmScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs[:10]:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

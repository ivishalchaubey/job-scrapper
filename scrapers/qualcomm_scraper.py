from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import json
import time
import os
import stat
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('qualcomm_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class QualcommScraper:
    def __init__(self):
        self.company_name = 'Qualcomm'
        self.url = 'https://qualcomm.wd5.myworkdayjobs.com/External?locationCountry=bc33aa3152ec42d4995f4791a106ed09'
        self.api_url = 'https://qualcomm.wd5.myworkdayjobs.com/wday/cxs/qualcomm/External/jobs'
        self.base_job_url = 'https://qualcomm.wd5.myworkdayjobs.com/External'

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

        driver_path = CHROMEDRIVER_PATH
        if not os.path.exists(driver_path):
            logger.warning(f"Fresh chromedriver not found at {driver_path}, trying system chromedriver")
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()
            if 'chromedriver-mac-arm64' in driver_path and not driver_path.endswith('chromedriver'):
                driver_dir = os.path.dirname(driver_path)
                actual_driver = os.path.join(driver_dir, 'chromedriver')
                if os.path.exists(actual_driver):
                    driver_path = actual_driver

        try:
            current_permissions = os.stat(driver_path).st_mode
            os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            logger.warning(f"Could not set permissions on chromedriver: {str(e)}")

        try:
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"Service driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Qualcomm Workday careers page.

        Uses a single Selenium session for both approaches:
        1. Primary: In-browser fetch() to call Workday API (bypasses Cloudflare)
        2. Fallback: DOM scraping from the already-loaded page
        """
        driver = None
        try:
            driver = self.setup_driver()
            logger.info(f"Loading {self.url} to establish browser session")

            try:
                driver.get(self.url)
            except Exception as e:
                error_msg = str(e).lower()
                if any(kw in error_msg for kw in ['dns', 'name or service not known',
                        'err_name_not_resolved', 'neterror', 'unreachable', 'connectionrefused']):
                    logger.error(f"DNS/Network error loading {self.url}: {str(e)}")
                    return []
                logger.warning(f"Page load issue (continuing): {str(e)}")

            # Check if the page loaded successfully or hit an error
            page_title = driver.title or ''
            if 'error' in page_title.lower() or 'unavailable' in page_title.lower() or 'maintenance' in page_title.lower():
                body_text = ''
                try:
                    body_text = driver.find_element(By.TAG_NAME, 'body').text[:200]
                except Exception:
                    pass
                logger.error(f"Workday site error: title='{page_title}', body='{body_text}'")
                logger.error("Qualcomm Workday site appears to be down. Cannot scrape.")
                return []

            # Wait for Workday to fully render (Cloudflare challenge + SPA load)
            page_loaded = False
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'li[data-automation-id="listItem"]'))
                )
                logger.info("Workday job listings loaded")
                page_loaded = True
            except Exception:
                logger.warning("Timeout waiting for job listings, trying API anyway")
                time.sleep(5)

            # Primary: Try in-browser API fetch
            api_jobs = self._try_browser_api(driver, max_pages)
            if api_jobs:
                logger.info(f"Browser API method returned {len(api_jobs)} jobs")
                return api_jobs
            else:
                logger.warning("Browser API returned 0 jobs, trying Selenium DOM scraping")

            # Fallback: DOM scraping using the same driver
            if page_loaded:
                dom_jobs = self._scrape_dom(driver, max_pages)
                if dom_jobs:
                    logger.info(f"Selenium DOM scraping returned {len(dom_jobs)} jobs")
                    return dom_jobs
            else:
                logger.warning("Skipping DOM scraping - page didn't load properly")

            logger.warning("All scraping methods returned 0 jobs")
            return []

        except Exception as e:
            logger.error(f"Scrape failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _try_browser_api(self, driver, max_pages=MAX_PAGES_TO_SCRAPE):
        """Try to scrape via in-browser fetch() API calls."""
        all_jobs = []
        limit = 20
        max_results = max_pages * limit

        # Try multiple payload formats via in-browser fetch
        payload_formats = [
            {"appliedFacets": {}, "limit": limit, "offset": 0, "searchText": ""},
            {"appliedFacets": {"locationCountry": ["bc33aa3152ec42d4995f4791a106ed09"]}, "limit": limit, "offset": 0, "searchText": ""},
            {"appliedFacets": {}, "limit": limit, "offset": 0, "searchText": "India"},
        ]

        working_payload = None
        for idx, payload in enumerate(payload_formats):
            logger.info(f"Trying in-browser API payload format {idx + 1}")
            try:
                result = self._browser_fetch(driver, payload)
                status = result.get('status', 0)
                body = result.get('body', '')

                if status == 200 and body:
                    data = json.loads(body)
                    total = data.get('total', 0)
                    postings = data.get('jobPostings', [])
                    logger.info(f"Format {idx + 1}: status=200, total={total}, postings={len(postings)}")

                    if postings:
                        working_payload = payload.copy()
                        all_jobs = self._process_api_postings(postings)
                        break
                    elif total == 0:
                        continue
                else:
                    logger.warning(f"Format {idx + 1}: status={status}")
                    continue
            except Exception as e:
                logger.warning(f"Format {idx + 1} in-browser fetch failed: {str(e)}")
                continue

        if not working_payload:
            logger.warning("No in-browser API payload format worked")
            return all_jobs

        # Paginate through remaining results
        if all_jobs and working_payload:
            offset = limit
            while offset < max_results:
                working_payload['offset'] = offset
                try:
                    logger.info(f"In-browser API: fetching offset={offset}")
                    result = self._browser_fetch(driver, working_payload)

                    if result.get('status') != 200:
                        logger.warning(f"API pagination returned status {result.get('status')}")
                        break

                    data = json.loads(result.get('body', '{}'))
                    total = data.get('total', 0)
                    postings = data.get('jobPostings', [])

                    if not postings:
                        break

                    new_jobs = self._process_api_postings(postings)
                    all_jobs.extend(new_jobs)
                    logger.info(f"Offset={offset}: got {len(new_jobs)} jobs (total so far: {len(all_jobs)})")

                    offset += limit
                    if offset >= total:
                        logger.info(f"Fetched all {total} available jobs")
                        break
                except Exception as e:
                    logger.error(f"API pagination failed at offset {offset}: {str(e)}")
                    break

        logger.info(f"Total jobs from browser API: {len(all_jobs)}")
        return all_jobs

    def _browser_fetch(self, driver, payload):
        """Execute a fetch() POST request from within the browser context.
        This inherits all browser cookies/session, bypassing Cloudflare and
        Workday's session validation that causes 422 errors with plain requests."""
        driver.set_script_timeout(30)
        result = driver.execute_async_script("""
            var payload = arguments[0];
            var apiUrl = arguments[1];
            var callback = arguments[arguments.length - 1];
            fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(payload)
            })
            .then(function(r) {
                return r.text().then(function(t) {
                    return {status: r.status, body: t};
                });
            })
            .then(function(result) { callback(result); })
            .catch(function(err) { callback({status: 0, error: err.toString()}); });
        """, payload, self.api_url)

        if result.get('error'):
            raise Exception(f"Browser fetch error: {result['error']}")
        return result

    def _process_api_postings(self, postings):
        """Process Workday API postings into job data format."""
        jobs = []
        for posting in postings:
            try:
                title = posting.get('title', '')
                if not title:
                    continue

                external_path = posting.get('externalPath', '')
                apply_url = f"{self.base_job_url}{external_path}" if external_path else self.url

                location = posting.get('locationsText', '')
                posted_date = posting.get('postedOn', '')

                # Extract job ID from externalPath (e.g., /job/R12345)
                job_id = ''
                if external_path:
                    parts = external_path.strip('/').split('/')
                    if parts:
                        job_id = parts[-1]
                if not job_id:
                    job_id = f"qualcomm_{hashlib.md5(title.encode()).hexdigest()[:12]}"

                # Extract additional info from bulletFields
                bullet_fields = posting.get('bulletFields', [])
                remote_type = ''
                employment_type = ''
                for field in bullet_fields:
                    if isinstance(field, str):
                        if 'On-site' in field or 'Remote' in field or 'Hybrid' in field:
                            remote_type = field
                        elif 'Full' in field or 'Part' in field or 'Contract' in field:
                            employment_type = field

                # Parse location
                city, state, country = self.parse_location(location)

                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': country,
                    'employment_type': employment_type,
                    'department': '',
                    'apply_url': apply_url,
                    'posted_date': posted_date,
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': remote_type,
                    'status': 'active'
                }
                jobs.append(job_data)
                logger.info(f"Added job: {title}")

            except Exception as e:
                logger.error(f"Error processing posting: {str(e)}")
                continue

        return jobs

    def _scrape_dom(self, driver, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: scrape Qualcomm jobs using Selenium DOM scraping.
        Reuses the already-loaded driver from the main scrape() method."""
        all_jobs = []

        try:
            current_page = 1

            while current_page <= max_pages:
                logger.info(f"DOM scraping page {current_page}")

                # Scrape current page
                page_jobs = self._scrape_page(driver)
                all_jobs.extend(page_jobs)
                logger.info(f"Page {current_page}: found {len(page_jobs)} jobs")

                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    # _go_to_next_page already handles waiting

                current_page += 1

            logger.info(f"Total jobs scraped via DOM: {len(all_jobs)}")

        except Exception as e:
            logger.error(f"Error during DOM scraping: {str(e)}")

        return all_jobs

    def _go_to_next_page(self, driver, current_page):
        """Navigate to next page in Workday"""
        try:
            next_page_num = current_page + 1

            # Scroll to pagination
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            # Capture current state for change detection
            old_first = driver.execute_script("""
                var card = document.querySelector('li[data-automation-id="listItem"]');
                return card ? card.innerText.substring(0, 50) : '';
            """)

            # Workday pagination selectors
            next_selectors = [
                (By.XPATH, f'//button[@aria-label="{next_page_num}"]'),
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'button[data-uxi-widget-type="page"][aria-label="{next_page_num}"]'),
                (By.XPATH, '//button[@aria-label="next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="next"]'),
            ]

            for selector_type, selector_value in next_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Navigated to page {next_page_num}")

                    # Poll for content change
                    for _ in range(25):
                        time.sleep(0.2)
                        new_first = driver.execute_script("""
                            var card = document.querySelector('li[data-automation-id="listItem"]');
                            return card ? card.innerText.substring(0, 50) : '';
                        """)
                        if new_first and new_first != old_first:
                            break
                    time.sleep(0.5)
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver):
        """Scrape jobs from current Workday page"""
        jobs = []
        wait = WebDriverWait(driver, 10)  # Short timeout since page is already loaded

        # Quick scroll for lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.3)

        # Workday job listing selectors
        workday_selectors = [
            (By.CSS_SELECTOR, 'li[data-automation-id="listItem"]'),
            (By.CSS_SELECTOR, 'li.css-1q2dra3'),
            (By.CSS_SELECTOR, 'ul li[class*="job"]'),
            (By.XPATH, '//ul[@aria-label="Search Results"]/li'),
        ]

        job_cards = []
        for selector_type, selector_value in workday_selectors:
            try:
                wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                job_cards = driver.find_elements(selector_type, selector_value)
                if job_cards and len(job_cards) > 0:
                    logger.info(f"Found {len(job_cards)} jobs using selector: {selector_value}")
                    break
            except:
                continue

        if not job_cards:
            logger.warning("No job cards found using standard selectors")
            return jobs

        for idx, card in enumerate(job_cards):
            try:
                card_text = card.text
                if not card_text or len(card_text) < 10:
                    continue

                # Extract job title (usually a link)
                job_title = ""
                job_link = ""

                try:
                    title_link = card.find_element(By.TAG_NAME, 'a')
                    job_title = title_link.get_attribute('aria-label') or title_link.text.strip()
                    job_link = title_link.get_attribute('href')
                except:
                    job_title = card_text.split('\n')[0].strip()

                if not job_title or len(job_title) < 3:
                    continue

                # Extract Job ID
                job_id = ""
                lines = card_text.split('\n')
                for line in lines:
                    line_stripped = line.strip()
                    if (line_stripped.startswith('REQ') or line_stripped.startswith('R')) and \
                       len(line_stripped) < 15 and line_stripped[1:].replace('-', '').isdigit():
                        job_id = line_stripped
                        break

                if not job_id:
                    if job_link and '/job/' in job_link:
                        job_id = job_link.split('/job/')[-1].split('/')[0]
                    else:
                        job_id = f"qualcomm_{hashlib.md5(job_title.encode()).hexdigest()[:12]}"

                # Extract location and work type
                location = ""
                city = ""
                state = ""
                remote_type = ""
                posted_date = ""

                for line in lines:
                    line_stripped = line.strip()

                    # Location (city, state format)
                    if ',' in line_stripped and len(line_stripped.split(',')) >= 2:
                        parts = line_stripped.split(',')
                        if len(parts[1].strip()) <= 3 or 'India' in line_stripped:
                            location = line_stripped
                            city = parts[0].strip()
                            state = parts[1].strip()

                    # Work type
                    if 'On-site' in line_stripped:
                        remote_type = 'On-site'
                    elif 'Remote' in line_stripped:
                        remote_type = 'Remote'
                    elif 'Hybrid' in line_stripped:
                        remote_type = 'Hybrid'

                    # Posted date
                    if 'Posted' in line_stripped:
                        posted_date = line_stripped.replace('Posted', '').strip()

                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': job_title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': 'India',
                    'employment_type': '',
                    'department': '',
                    'apply_url': job_link if job_link else self.url,
                    'posted_date': posted_date,
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': remote_type,
                    'status': 'active'
                }

                jobs.append(job_data)
                logger.info(f"Successfully added job: {job_title}")

            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                continue

        return jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

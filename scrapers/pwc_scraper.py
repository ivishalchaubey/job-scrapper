from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import json
import re
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('pwc_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class PwCScraper:
    def __init__(self):
        self.company_name = 'PwC'
        self.url = 'https://www.pwc.in/careers/experienced-jobs.html'

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
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
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
        """Scrape jobs from PwC India careers page.

        The page uses a Workday widget. The search form at
        /careers/experienced-jobs.html submits to /careers/experienced-jobs/results.html.
        The results page embeds all job data in a JavaScript variable called 'jsondata'.
        We extract jobs directly from that embedded JSON for reliability.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Strategy 1: Navigate to results page with country=India params
            # The form submits to results.html with wdcountry=IND|BGD and wdjobsite params
            results_url = (
                'https://www.pwc.in/careers/experienced-jobs/results.html'
                '?wdcountry=IND%7CBGD'
                '&wdjobsite=Global_Experienced_Careers'
                '&flds=jobreqid,title,location,jobsite,iso'
            )
            logger.info(f"Navigating to results page: {results_url}")
            driver.get(results_url)
            time.sleep(15)  # Wait for page and AJAX to load

            # Extract jsondata from page source
            page_source = driver.page_source
            jsondata_match = re.search(r'var\s+jsondata\s*=\s*(\[.*?\])\s*;', page_source, re.DOTALL)

            if jsondata_match:
                try:
                    raw_json = jsondata_match.group(1)
                    job_list = json.loads(raw_json)
                    logger.info(f"Found {len(job_list)} jobs in jsondata")

                    for job_entry in job_list:
                        title = job_entry.get('title', '').strip()
                        location = job_entry.get('location', '').strip()
                        job_req_id = job_entry.get('jobreqid', '').strip()
                        iso = job_entry.get('iso', '').strip()
                        jobsite = job_entry.get('jobsite', '').strip()

                        if not title or not job_req_id:
                            continue

                        # Build apply URL using PwC's description page pattern
                        apply_url = (
                            f'https://www.pwc.in/in/en/careers/experienced-jobs/description.html'
                            f'?wdjobreqid={job_req_id}&wdcountry=IND'
                        )

                        city, state, _ = self.parse_location(location)

                        job_data = {
                            'external_id': self.generate_external_id(job_req_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': 'India',
                            'employment_type': '',
                            'department': '',
                            'apply_url': apply_url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        jobs.append(job_data)

                    logger.info(f"Parsed {len(jobs)} jobs from embedded JSON data")

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse jsondata: {str(e)}")
                    # Fall through to table-based extraction
            else:
                logger.warning("jsondata not found in page source")

            # Strategy 2: If jsondata extraction failed, try table-based extraction
            if not jobs:
                logger.info("Falling back to table-based extraction")
                jobs = self._extract_from_table(driver)

            # Strategy 3: If table extraction also failed, try submitting form from search page
            if not jobs:
                logger.info("Table extraction failed, trying form submission approach")
                jobs = self._submit_form_and_extract(driver)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_from_table(self, driver):
        """Extract jobs from the results table (#wdresults)"""
        jobs = []
        try:
            table = driver.find_element(By.ID, 'wdresults')
            rows = table.find_elements(By.TAG_NAME, 'tr')
            logger.info(f"Found {len(rows)} rows in results table")

            for idx, row in enumerate(rows):
                try:
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) < 2:
                        continue

                    # First cell: title with link, Second cell: location
                    title_cell = cells[0]
                    location_cell = cells[1] if len(cells) > 1 else None

                    link = None
                    try:
                        link = title_cell.find_element(By.TAG_NAME, 'a')
                    except:
                        pass

                    title = title_cell.text.strip()
                    # Clean up bullet point prefix
                    if title.startswith('\u00b7'):
                        title = title[1:].strip()

                    href = link.get_attribute('href') if link else ''
                    location = location_cell.text.strip() if location_cell else ''

                    if not title or len(title) < 3:
                        continue

                    # Extract job requisition ID from URL
                    job_req_id = ''
                    if href:
                        req_match = re.search(r'wdjobreqid=(\w+)', href)
                        if req_match:
                            job_req_id = req_match.group(1)

                    if not job_req_id:
                        job_req_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    city, state, _ = self.parse_location(location)

                    job_data = {
                        'external_id': self.generate_external_id(job_req_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': href if href else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job_data)

                except Exception as e:
                    logger.error(f"Error extracting row {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Table extraction error: {str(e)}")

        return jobs

    def _submit_form_and_extract(self, driver):
        """Navigate to search page, submit form, then extract from results"""
        jobs = []
        try:
            logger.info("Loading search page to submit form")
            driver.get(self.url)
            time.sleep(10)

            # Click "View all jobs" button
            try:
                view_all = driver.find_element(By.CSS_SELECTOR, 'input[name="submit1"][value="View all jobs"]')
                driver.execute_script('arguments[0].click()', view_all)
                logger.info("Clicked 'View all jobs' button")
                time.sleep(15)
            except Exception as e:
                logger.warning(f"Could not click View all jobs: {str(e)}")
                return jobs

            # Now extract from the redirected results page
            page_source = driver.page_source
            jsondata_match = re.search(r'var\s+jsondata\s*=\s*(\[.*?\])\s*;', page_source, re.DOTALL)

            if jsondata_match:
                try:
                    job_list = json.loads(jsondata_match.group(1))
                    logger.info(f"Form submission: found {len(job_list)} jobs in jsondata")

                    for job_entry in job_list:
                        title = job_entry.get('title', '').strip()
                        location = job_entry.get('location', '').strip()
                        job_req_id = job_entry.get('jobreqid', '').strip()

                        if not title or not job_req_id:
                            continue

                        apply_url = (
                            f'https://www.pwc.in/in/en/careers/experienced-jobs/description.html'
                            f'?wdjobreqid={job_req_id}&wdcountry=IND'
                        )

                        city, state, _ = self.parse_location(location)

                        job_data = {
                            'external_id': self.generate_external_id(job_req_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': 'India',
                            'employment_type': '',
                            'department': '',
                            'apply_url': apply_url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        jobs.append(job_data)

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse jsondata after form submission: {str(e)}")
            else:
                logger.warning("jsondata not found after form submission either")
                # Try table extraction on the results page
                jobs = self._extract_from_table(driver)

        except Exception as e:
            logger.error(f"Form submission approach error: {str(e)}")

        return jobs

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(3)

            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, "//h2[contains(text(), 'Description')]/following-sibling::div"),
                    (By.CSS_SELECTOR, 'div.job-description'),
                ]

                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        if desc_elem and desc_elem.text.strip():
                            details['description'] = desc_elem.text.strip()[:2000]
                            break
                    except:
                        continue
            except:
                pass

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass

        return details

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

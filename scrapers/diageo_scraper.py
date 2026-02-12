from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('diageo_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class DiageoScraper:
    def __init__(self):
        self.company_name = 'Diageo'
        self.url = 'https://diageo.wd3.myworkdayjobs.com/Diageo_Careers'
        self.api_url = 'https://diageo.wd3.myworkdayjobs.com/wday/cxs/diageo/Diageo_Careers/jobs'
        self.base_job_url = 'https://diageo.wd3.myworkdayjobs.com/Diageo_Careers'

    def setup_driver(self):
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
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        # Primary method: Workday API via requests
        if requests is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("API method returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.warning(f"API method failed: {str(e)}, falling back to Selenium")
        else:
            logger.warning("requests library not available, using Selenium only")

        # Fallback: Selenium-based scraping
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Diageo jobs using Workday API directly."""
        all_jobs = []
        limit = 20
        max_results = max_pages * limit

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        }

        offset = 0
        while offset < max_results:
            payload = {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": "India"
            }

            try:
                logger.info(f"Fetching API page offset={offset}")
                response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()

                total = data.get('total', 0)
                postings = data.get('jobPostings', [])

                if not postings:
                    logger.info(f"No more postings at offset {offset}")
                    break

                logger.info(f"API returned {len(postings)} postings (total available: {total})")

                for posting in postings:
                    try:
                        title = posting.get('title', '')
                        if not title:
                            continue

                        external_path = posting.get('externalPath', '')
                        apply_url = f"{self.base_job_url}{external_path}" if external_path else self.url

                        location = posting.get('locationsText', '')
                        posted_date = posting.get('postedOn', '')

                        # Extract job ID from externalPath
                        job_id = ''
                        if external_path:
                            parts = external_path.strip('/').split('/')
                            if parts:
                                job_id = parts[-1]
                        if not job_id:
                            job_id = f"diageo_{hashlib.md5(title.encode()).hexdigest()[:12]}"

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
                            'department': '',
                            'apply_url': apply_url,
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        }

                        all_jobs.append(job_data)
                        logger.info(f"Added job: {title}")

                    except Exception as e:
                        logger.error(f"Error processing posting: {str(e)}")
                        continue

                offset += limit

                # Stop if we've fetched all available
                if offset >= total:
                    logger.info(f"Fetched all {total} available jobs")
                    break

            except Exception as e:
                logger.error(f"API request failed at offset {offset}: {str(e)}")
                break

        logger.info(f"Total jobs from API: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: scrape Diageo jobs using Selenium."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")

            driver.get(self.url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(12)

            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, 'li[data-automation-id="listItem"]'
                )))
                logger.info("Job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for job listings: {str(e)}")

            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                jobs = self._scrape_page(driver, wait)
                all_jobs.extend(jobs)
                logger.info(f"Page {current_page}: found {len(jobs)} jobs")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        break
                    time.sleep(5)
                current_page += 1

            logger.info(f"Total jobs scraped via Selenium: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during Selenium scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _go_to_next_page(self, driver, current_page):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            next_selectors = [
                (By.XPATH, f'//button[@aria-label="{current_page + 1}"]'),
                (By.XPATH, f'//button[text()="{current_page + 1}"]'),
                (By.CSS_SELECTOR, f'button[data-uxi-widget-type="page"][aria-label="{current_page + 1}"]'),
                (By.XPATH, '//button[@aria-label="next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="next"]'),
            ]

            for selector_type, selector_value in next_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Navigated to page {current_page + 1}")
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver, wait):
        """Scrape jobs from current Workday page."""
        jobs = []
        time.sleep(3)

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

                job_id = ""
                lines = card_text.split('\n')
                for line in lines:
                    line_stripped = line.strip()
                    if (line_stripped.startswith('R') and line_stripped[1:].isdigit()) or \
                       (line_stripped.startswith('REQ') and len(line_stripped) < 15):
                        job_id = line_stripped
                        break

                if not job_id:
                    if job_link and '/job/' in job_link:
                        job_id = job_link.split('/job/')[-1].split('/')[0]
                    else:
                        job_id = f"diageo_{hashlib.md5(job_title.encode()).hexdigest()[:12]}"

                location = ""
                city = ""
                state = ""
                remote_type = ""
                posted_date = ""

                for line in lines:
                    line_stripped = line.strip()

                    if ',' in line_stripped and len(line_stripped.split(',')) >= 2:
                        parts = line_stripped.split(',')
                        if len(parts[1].strip()) <= 3 or 'India' in line_stripped:
                            location = line_stripped
                            city = parts[0].strip()
                            state = parts[1].strip()

                    if 'On-site' in line_stripped:
                        remote_type = 'On-site'
                    elif 'Remote' in line_stripped:
                        remote_type = 'Remote'
                    elif 'Hybrid' in line_stripped:
                        remote_type = 'Hybrid'

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

                location_parts = self.parse_location(job_data.get('location', ''))
                job_data.update(location_parts)

                jobs.append(job_data)
                logger.info(f"Successfully added job: {job_title}")

            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                continue

        return jobs

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


if __name__ == "__main__":
    scraper = DiageoScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

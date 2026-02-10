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
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('lowes_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class LowesScraper:
    def __init__(self):
        self.company_name = "Lowe's"
        self.url = 'https://jobs.lowes.com/search-jobs/India'

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
        """Scrape jobs from Lowe's careers page"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            logger.info(f"Navigating to {self.url}")
            driver.get(self.url)
            time.sleep(15)

            current_url = driver.current_url
            logger.info(f"Current URL after navigation: {current_url}")

            # Wait for job listings to appear (Radancy or Phenom)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        '#search-results-list li, li.jobs-list-item, a[data-ph-at-id="job-link"]'))
                )
                logger.info("Job listings detected on page")
            except:
                logger.warning("Timeout waiting for job listings, proceeding anyway")

            # Scroll to trigger lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_page(driver)
                if not page_jobs and current_page == 1:
                    logger.warning("No jobs found on first page, trying JS extraction fallback")
                    page_jobs = self._js_extract_jobs(driver)

                jobs.extend(page_jobs)
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(4)

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page using Phenom pagination"""
        try:
            next_page_num = current_page + 1

            # Scroll to pagination area
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # Radancy + Phenom pagination selectors
            next_page_selectors = [
                (By.CSS_SELECTOR, f'a[data-ph-at-id="pagination-page-number-link"][aria-label="Page {next_page_num}"]'),
                (By.CSS_SELECTOR, 'a[data-ph-at-id="pagination-next-link"]'),
                (By.CSS_SELECTOR, '.pagination-paging a.next'),
                (By.CSS_SELECTOR, f'a.pagination-page[data-page="{next_page_num}"]'),
                (By.XPATH, f'//a[@aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="View next page"]'),
                (By.XPATH, '//a[contains(@class, "next")]'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Clicked next page button for page {next_page_num}")
                    time.sleep(3)
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver):
        """Scrape jobs from current page using Selenium selectors (Radancy + Phenom)"""
        jobs = []
        time.sleep(2)

        current_url = driver.current_url
        job_elements = []

        # Strategy 1: Radancy selectors (jobs.lowes.com)
        radancy_selectors = [
            '#search-results-list li',
            '.search-results-list li',
            'section[id*="search-results"] li',
        ]

        # Strategy 2: Phenom selectors (talent.lowes.com)
        phenom_selectors = [
            'li.jobs-list-item',
            'a[data-ph-at-id="job-link"]',
        ]

        all_selectors = radancy_selectors + phenom_selectors
        used_selector = ''

        for selector in all_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    job_elements = elements
                    used_selector = selector
                    logger.info(f"Found {len(elements)} elements with: {selector}")
                    break
            except:
                continue

        if job_elements:
            for idx, elem in enumerate(job_elements):
                try:
                    title = ''
                    href = ''
                    location = ''

                    if elem.tag_name == 'a':
                        title = elem.text.strip()
                        href = elem.get_attribute('href') or ''
                    else:
                        # Find link inside the element
                        for link_sel in ['h2 a', 'a[data-ph-at-id="job-link"]', 'a[href*="/job/"]', '.job-result-title a', 'a']:
                            try:
                                link = elem.find_element(By.CSS_SELECTOR, link_sel)
                                title = link.text.strip()
                                href = link.get_attribute('href') or ''
                                if title:
                                    break
                            except:
                                continue

                        # Extract location
                        for loc_sel in ['.job-location', '[data-ph-at-id="job-location"]', 'span[class*="location"]']:
                            try:
                                loc_elem = elem.find_element(By.CSS_SELECTOR, loc_sel)
                                location = loc_elem.text.strip()
                                if location.startswith('Location'):
                                    location = location.replace('Location', '', 1).strip()
                                if location:
                                    break
                            except:
                                continue

                    if not title or len(title) < 3:
                        continue

                    job_id = f"lowes_{idx}"
                    if href and '/job/' in href:
                        parts = href.split('/job/')
                        if len(parts) > 1:
                            job_id = parts[1].split('/')[0].split('?')[0]

                    city, state, country = self.parse_location(location)
                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country if country else 'USA',
                        'employment_type': '',
                        'department': '',
                        'apply_url': href or self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job)
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

            if jobs:
                return jobs

        # Strategy 3: Simple JS fallback with try-catch wrapper
        logger.info("Selenium selectors found nothing, trying JS fallback")
        try:
            js_jobs = driver.execute_script(
                "try {"
                "  var r = [];"
                "  var s = {};"
                "  var links = document.querySelectorAll('a[href]');"
                "  for (var i = 0; i < links.length; i++) {"
                "    var a = links[i];"
                "    var t = (a.innerText || '').trim();"
                "    var h = a.href || '';"
                "    var lh = h.toLowerCase();"
                "    if (t.length > 3 && t.length < 200 && !s[h] && "
                "        (lh.indexOf('/job/') > -1 || lh.indexOf('/job-') > -1)) {"
                "      s[h] = true;"
                "      r.push({title: t.split(String.fromCharCode(10))[0].trim(), href: h});"
                "    }"
                "  }"
                "  return r;"
                "} catch(e) { return []; }"
            )
            if js_jobs:
                logger.info(f"JS fallback found {len(js_jobs)} links")
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '')
                    href = jdata.get('href', '')
                    if not title or len(title) < 3:
                        continue
                    job_id = f"lowes_js_{idx}"
                    if href and '/job/' in href:
                        parts = href.split('/job/')
                        if len(parts) > 1:
                            job_id = parts[1].split('/')[0].split('?')[0]
                    city, state, country = self.parse_location('')
                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': '',
                        'city': city,
                        'state': state,
                        'country': country if country else 'USA',
                        'employment_type': '',
                        'department': '',
                        'apply_url': href or self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job)
        except Exception as e:
            logger.error(f"JS fallback failed: {str(e)}")

        return jobs

    def _js_extract_jobs(self, driver):
        """Final fallback: extract all job links via JavaScript"""
        jobs = []
        try:
            js_links = driver.execute_script("""
                var results = [];
                var links = document.querySelectorAll('a[href*="/job/"]');
                var seen = {};
                for (var i = 0; i < links.length; i++) {
                    var href = links[i].href;
                    var text = links[i].innerText.trim();
                    if (text.length > 3 && text.length < 200 && !seen[href]) {
                        seen[href] = true;
                        results.push({title: text.split('\\n')[0].trim(), url: href});
                    }
                }
                return results;
            """)

            if js_links:
                logger.info(f"JS link fallback found {len(js_links)} job links")
                for idx, link_data in enumerate(js_links):
                    title = link_data.get('title', '')
                    url = link_data.get('url', '')
                    if not title or not url or len(title) < 3:
                        continue

                    job_id = f"lowes_js_{idx}"
                    if '/job/' in url:
                        parts = url.split('/job/')
                        if len(parts) > 1:
                            job_id = parts[1].split('/')[0].split('?')[0]

                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'USA',
                        'employment_type': '',
                        'department': '',
                        'apply_url': url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job)
        except Exception as e:
            logger.error(f"JS link fallback error: {str(e)}")

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
                    (By.CSS_SELECTOR, 'div.job-description'),
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, '//div[contains(@class, "description")]'),
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

            try:
                dept_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'Department')]//following-sibling::*")
                details['department'] = dept_elem.text.strip()
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
            return '', '', ''

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        country = ''
        if 'India' in location_str:
            country = 'India'
        elif len(parts) > 2:
            country = parts[2]

        return city, state, country

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

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

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

            # Detect redirect to Phenom platform
            is_phenom = 'talent.lowes.com' in current_url and 'search-jobs' not in current_url
            if is_phenom:
                logger.info("Detected Phenom platform redirect, navigating to India search")
                # Lowes India jobs are under /in/en/ path prefix
                phenom_search = 'https://talent.lowes.com/in/en/search-results'
                driver.get(phenom_search)
                time.sleep(12)
                logger.info(f"Phenom search URL: {driver.current_url}")

            # Wait for job listings to appear
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        '#search-results-list li, li.jobs-list-item, a[data-ph-at-id="job-link"], a[href*="/job/"]'))
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
                # NAS/Radancy
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
                # Phenom pagination (a.next-btn with aria-label="View next page")
                (By.CSS_SELECTOR, 'a.next-btn[aria-label="View next page"]'),
                (By.CSS_SELECTOR, 'a[aria-label="View next page"]'),
                (By.CSS_SELECTOR, 'a[data-ph-at-id="pagination-next-link"]'),
                (By.CSS_SELECTOR, f'a[data-ph-at-id="pagination-page-number-link"][aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
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
        """Scrape jobs - tries NAS/Radancy first, then Phenom fallback"""
        jobs = []
        time.sleep(2)

        # Strategy 1: NAS/Radancy JS extraction
        js_jobs = driver.execute_script("""
            var results = [];
            var seen = {};
            var container = document.querySelector('#search-results-list');
            if (container) {
                var items = container.querySelectorAll('li');
                for (var i = 0; i < items.length; i++) {
                    var item = items[i];
                    var link = item.querySelector('a[href]');
                    if (!link) continue;
                    var title = link.innerText.trim().split('\\n')[0];
                    var url = link.href;
                    if (!title || title.length < 3 || seen[url]) continue;
                    seen[url] = true;
                    var locEl = item.querySelector('.job-location, [class*="location"]');
                    var location = locEl ? locEl.innerText.trim() : '';
                    var dateEl = item.querySelector('.job-date-posted, [class*="date"]');
                    var date = dateEl ? dateEl.innerText.trim() : '';
                    results.push({title: title, url: url, location: location, date: date});
                }
            }
            return results;
        """)

        if js_jobs:
            logger.info(f"NAS/Radancy extraction found {len(js_jobs)} jobs")
        else:
            # Strategy 2: Phenom platform extraction (talent.lowes.com)
            # Uses li.jobs-list-item cards with a.au-target job links
            logger.info("Trying Phenom platform extraction")
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};
                // Phenom job cards
                var cards = document.querySelectorAll('li.jobs-list-item');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var link = card.querySelector('a.au-target[href*="/job/"], a[data-ph-at-id="job-link"], a[href*="/job/"]');
                    if (!link) continue;
                    var h = link.href;
                    if (!h || seen[h] || h.indexOf('jobcart') > -1) continue;
                    var t = link.innerText.trim().split('\\n')[0];
                    if (t.length < 3 || t.length > 200) continue;
                    seen[h] = true;
                    // Location from spans containing "Location\\n..."
                    var location = '';
                    var spans = card.querySelectorAll('span');
                    for (var j = 0; j < spans.length; j++) {
                        var st = spans[j].innerText.trim();
                        if (st.indexOf('Location') === 0 && st.indexOf('\\n') > -1) {
                            location = st.split('\\n')[1].trim();
                            break;
                        }
                    }
                    // Department/category
                    var dept = '';
                    for (var j = 0; j < spans.length; j++) {
                        var st = spans[j].innerText.trim();
                        if (st.indexOf('Category') === 0 && st.indexOf('\\n') > -1) {
                            dept = st.split('\\n')[1].trim();
                            break;
                        }
                    }
                    results.push({title: t, url: h, location: location, dept: dept});
                }
                // Fallback: direct job links
                if (results.length === 0) {
                    var links = document.querySelectorAll('a.au-target[href*="/job/"], a[href*="/en/job/"]');
                    for (var i = 0; i < links.length; i++) {
                        var a = links[i];
                        var h = a.href;
                        if (!h || seen[h] || h.indexOf('jobcart') > -1) continue;
                        var t = (a.innerText || '').trim().split('\\n')[0];
                        if (t.length > 3 && t.length < 200) {
                            seen[h] = true;
                            results.push({title: t, url: h, location: '', dept: ''});
                        }
                    }
                }
                return results;
            """)
            if js_jobs:
                logger.info(f"Phenom extraction found {len(js_jobs)} jobs")

        if not js_jobs:
            logger.warning("No jobs found on page")
            return jobs

        for jdata in js_jobs:
            try:
                title = jdata.get('title', '').strip()
                url = jdata.get('url', '').strip()
                location = jdata.get('location', '').strip()

                if not title or len(title) < 3 or not url:
                    continue

                job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                if '/job/' in url:
                    parts = url.split('/job/')
                    if len(parts) > 1:
                        job_id = parts[1].split('/')[0].split('?')[0] or job_id

                city, state, country = self.parse_location(location)

                job = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': country if country else 'India',
                    'employment_type': '',
                    'department': jdata.get('dept', ''),
                    'apply_url': url,
                    'posted_date': jdata.get('date', ''),
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                jobs.append(job)

            except Exception as e:
                logger.error(f"Error extracting job: {str(e)}")
                continue

        return jobs

    def _js_extract_jobs(self, driver):
        """Fallback: same NAS/Radancy extraction (called if first page returns empty)"""
        return self._scrape_page(driver)

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

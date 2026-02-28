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


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('synchrony_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class SynchronyScraper:
    def __init__(self):
        self.company_name = 'Synchrony'
        self.url = 'https://www.synchronycareers.com/job-search-results/?location=India&country=IN&radius=25'
        self.base_url = 'https://www.synchronycareers.com'

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
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Primary driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Wait for Synchrony custom WordPress job table to load
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.search-results-table, a[href*="/job-detail/"]'))
                )
            except:
                time.sleep(5)

            # Quick scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

            for page in range(max_pages):
                page_jobs = self._extract_jobs(driver)
                if not page_jobs:
                    break
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if page < max_pages - 1:
                    if not self._go_to_next_page(driver):
                        break

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver):
        jobs = []

        try:
            # Single scroll to ensure all items are loaded
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Synchrony uses a custom WordPress job table with div[role="table"]
                // Each job row is a div[role="row"] containing a link to /job-detail/
                // Strategy 1: Find job detail links directly
                var jobLinks = document.querySelectorAll('a[href*="/job-detail/"]');

                for (var i = 0; i < jobLinks.length; i++) {
                    var link = jobLinks[i];
                    var href = link.href || '';
                    if (!href || seen[href]) continue;

                    var title = link.innerText.trim();
                    // Skip non-title text (headers, navigation labels)
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (title === 'Title' || title === 'Search Results' || title === 'Location') continue;

                    seen[href] = true;

                    // Try to find location from sibling/parent row structure
                    var location = '';
                    var row = link.closest('div[role="row"], tr, li, [class*="row"]');
                    if (row) {
                        // Look for location cell - typically the second cell in the row
                        var cells = row.querySelectorAll('div[role="cell"], td, [class*="cell"]');
                        if (cells.length >= 2) {
                            location = cells[1].innerText.trim();
                        }
                        // Fallback: look for location-specific class
                        if (!location) {
                            var locEl = row.querySelector('[class*="location"]');
                            if (locEl) location = locEl.innerText.trim();
                        }
                    }

                    results.push({title: title, url: href, location: location});
                }

                // Strategy 2: Fallback - look for rows in search results table
                if (results.length === 0) {
                    var rows = document.querySelectorAll('.search-results-table div[role="row"]');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        var link = row.querySelector('a[href]');
                        if (!link) continue;
                        var href = link.href || '';
                        if (!href || seen[href]) continue;
                        if (!href.includes('/job-detail/') && !href.includes('/job/')) continue;

                        var title = link.innerText.trim();
                        if (!title || title.length < 3 || title === 'Title') continue;

                        seen[href] = true;
                        var location = '';
                        var cells = row.querySelectorAll('div[role="cell"], td');
                        if (cells.length >= 2) {
                            location = cells[1].innerText.trim();
                        }
                        results.push({title: title, url: href, location: location});
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/job-detail/' in url:
                        parts = url.split('/job-detail/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    loc_data = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url or self.url,
                        'location': location,
                        'department': '',
                        'employment_type': '',
                        'description': '',
                        'posted_date': '',
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            # Get current first job link to detect page change
            old_first = driver.execute_script("""
                var link = document.querySelector('a[href*="/job-detail/"]');
                return link ? link.href : '';
            """)

            # Synchrony uses a pagination bar with page numbers and go-to-next button
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a.go-to-next'),
                (By.CSS_SELECTOR, 'button.go-to-next'),
                (By.CSS_SELECTOR, '[class*="go-to-next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.XPATH, '//a[contains(@class, "next")]'),
                (By.XPATH, '//button[contains(@class, "next")]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        # Poll for page change instead of blind sleep
                        for _ in range(20):  # max 4s wait
                            time.sleep(0.2)
                            new_first = driver.execute_script("""
                                var link = document.querySelector('a[href*="/job-detail/"]');
                                return link ? link.href : '';
                            """)
                            if new_first and new_first != old_first:
                                break
                        time.sleep(0.5)  # Brief settle
                        return True
                except:
                    continue
            return False
        except:
            return False

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


if __name__ == "__main__":
    scraper = SynchronyScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

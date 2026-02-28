from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import stat
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('nike_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class NikeScraper:
    def __init__(self):
        self.company_name = 'Nike'
        self.url = 'https://jobs.nike.com/search-jobs/India'

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
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Nike careers page with pagination support"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            time.sleep(10)

            current_url = driver.current_url
            logger.info(f"Landed on: {current_url}")

            # Detect redirect away from NAS
            if 'search-jobs' not in current_url:
                logger.info("Detected redirect away from NAS, navigating to Nike jobs search")
                # Nike's new careers site job search with location filter
                driver.get('https://careers.nike.com/jobs?location=India')
                time.sleep(15)
                logger.info(f"Redirected to: {driver.current_url}")

            # Wait for job listings
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "#search-results-list li, a[href*='/job/'], [class*='job-card']"
                )))
                logger.info("Job listings loaded")
            except:
                logger.warning("Timeout waiting for job listings")

            # Scroll to trigger lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1
            seen_ids = set()

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_page(driver, seen_ids)
                jobs.extend(page_jobs)

                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(3)

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page"""
        try:
            next_page_num = current_page + 1

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            next_page_selectors = [
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
                (By.CSS_SELECTOR, 'a.pagination-show-more'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Clicked next page button")
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver, seen_ids):
        """Scrape jobs - tries NAS/Radancy first, then generic job link extraction with India filter."""
        jobs = []
        time.sleep(2)

        try:
            # Scroll to load all content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

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
                        results.push({title: title, url: url, location: location});
                    }
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"NAS/Radancy extraction found {len(js_jobs)} jobs")
            else:
                # Strategy 2: Generic job link extraction (careers.nike.com)
                logger.info("Trying generic job link extraction")
                js_jobs = driver.execute_script("""
                    var results = [];
                    var seen = {};
                    var links = document.querySelectorAll('a[href*="/job/"]');
                    for (var i = 0; i < links.length; i++) {
                        var a = links[i];
                        var t = (a.innerText || '').trim().split('\\n')[0];
                        var h = a.href;
                        if (t.length > 3 && t.length < 200 && !seen[h]) {
                            if (h.indexOf('login') > -1 || h.indexOf('sign-in') > -1) continue;
                            seen[h] = true;
                            var parent = a.closest('li, div[class*="job"], article, div[class*="card"]');
                            var location = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], .job-location');
                                if (locEl) location = locEl.innerText.trim();
                            }
                            results.push({title: t, url: h, location: location});
                        }
                    }
                    return results;
                """)
                if js_jobs:
                    logger.info(f"Generic extraction found {len(js_jobs)} jobs")

            if not js_jobs:
                logger.warning("No jobs found on page")
                return jobs

            india_keywords = ['india', 'mumbai', 'delhi', 'bangalore', 'bengaluru', 'hyderabad',
                              'chennai', 'pune', 'kolkata', 'gurgaon', 'gurugram', 'noida']

            for jl in js_jobs:
                title = jl.get('title', '').strip()
                url = jl.get('url', '').strip()
                if not title or not url:
                    continue

                location = jl.get('location', '').strip()

                # India post-filter: reject non-India jobs
                loc_lower = location.lower()
                if location and not any(kw in loc_lower for kw in india_keywords):
                    continue

                job_id = self._extract_job_id(url)
                external_id = self.generate_external_id(job_id, self.company_name)

                if external_id in seen_ids:
                    continue

                city, state, country = self.parse_location(location)

                job_data = {
                    'external_id': external_id,
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': 'India',
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

                if FETCH_FULL_JOB_DETAILS and url:
                    full_details = self._fetch_job_details(driver, url)
                    job_data.update(full_details)

                jobs.append(job_data)
                seen_ids.add(external_id)
                logger.info(f"Extracted: {title} | {location}")

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        return jobs

    def _extract_job_id(self, job_url):
        """Extract job ID from Nike URL."""
        job_id = ""
        if '/job/' in job_url:
            job_id = job_url.split('/job/')[-1].split('?')[0].split('/')[0]
        elif 'id=' in job_url:
            job_id = job_url.split('id=')[-1].split('&')[0]
        if not job_id:
            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]
        return job_id

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(3)

            # Extract description
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

            # Extract department
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
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'


if __name__ == "__main__":
    scraper = NikeScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

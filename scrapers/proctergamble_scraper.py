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

logger = setup_logger('proctergamble_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class ProcterGambleScraper:
    def __init__(self):
        self.company_name = 'Procter & Gamble'
        self.url = 'https://www.pgcareers.com/search-jobs/India/403/1/2/6252001/19x9434/-2x2371/50/2'
    
    def setup_driver(self):
        """Set up Chrome driver with anti-detection options"""
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
            import os
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
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
        """Scrape jobs from Procter & Gamble careers page with pagination support"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            time.sleep(10)

            current_url = driver.current_url
            logger.info(f"Landed on: {current_url}")

            # Detect platform: NAS/Radancy vs Phenom redirect
            has_nas = 'search-results-list' in driver.page_source
            is_phenom = 'pgcareers.com' in current_url and 'search-jobs' not in current_url

            if is_phenom:
                logger.info("Detected Phenom platform redirect, navigating to search-results")
                # P&G Phenom search results page (shows all jobs)
                driver.get('https://www.pgcareers.com/global/en/search-results')
                time.sleep(12)
                logger.info(f"Phenom search URL: {driver.current_url}")

                # Try to use location filter to narrow to India
                try:
                    loc_input = driver.find_element(By.CSS_SELECTOR, '#gllocationInput')
                    loc_input.clear()
                    loc_input.send_keys('India')
                    time.sleep(2)
                    # Select India from dropdown if it appears
                    try:
                        india_option = driver.find_element(By.XPATH, '//span[contains(text(), "India")]')
                        india_option.click()
                        time.sleep(5)
                        logger.info("Selected India location filter")
                    except Exception:
                        # Press enter or click search button
                        from selenium.webdriver.common.keys import Keys
                        loc_input.send_keys(Keys.RETURN)
                        time.sleep(5)
                        logger.info("Submitted India location search")
                except Exception as e:
                    logger.warning(f"Could not set location filter: {str(e)}")

                # Scroll to trigger lazy loading of job cards
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
        """Navigate to the next page (NAS or Phenom pagination)"""
        try:
            next_page_num = current_page + 1

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            next_page_selectors = [
                # NAS/Radancy pagination
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
                # P&G Phenom pagination (a.next-btn with aria-label="View next page")
                (By.CSS_SELECTOR, 'a.next-btn[aria-label="View next page"]'),
                (By.CSS_SELECTOR, 'a[aria-label="View next page"]'),
                (By.CSS_SELECTOR, 'a[data-ph-at-id="pagination-next-link"]'),
                (By.CSS_SELECTOR, 'button[data-ph-at-id="load-more-jobs-button"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
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
                    results.push({title: title, url: url, location: location});
                }
            }
            return results;
        """)

        if js_jobs:
            logger.info(f"NAS/Radancy extraction found {len(js_jobs)} jobs")
        else:
            # Strategy 2: P&G Phenom platform extraction
            # Uses li.jobs-list-item cards with a.au-target[href*="/job/"] links
            logger.info("Trying Phenom platform extraction")
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};
                // P&G Phenom job cards
                var cards = document.querySelectorAll('li.jobs-list-item');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var link = card.querySelector('a.au-target[href*="/job/"], a[href*="/job/"]');
                    if (!link) continue;
                    var h = link.href;
                    if (!h || seen[h]) continue;
                    if (h.indexOf('jobcart') > -1) continue;
                    var t = link.innerText.trim().split('\\n')[0];
                    if (t.length < 3 || t.length > 200) continue;
                    seen[h] = true;
                    // Location is in spans containing "Location\\n..."
                    var location = '';
                    var spans = card.querySelectorAll('span');
                    for (var j = 0; j < spans.length; j++) {
                        var st = spans[j].innerText.trim();
                        if (st.indexOf('Location') === 0 && st.indexOf('\\n') > -1) {
                            location = st.split('\\n')[1].trim();
                            break;
                        }
                    }
                    // Get department/category
                    var dept = '';
                    for (var j = 0; j < spans.length; j++) {
                        var st = spans[j].innerText.trim();
                        if (st.indexOf('Category') === 0 && st.indexOf('\\n') > -1) {
                            dept = st.split('\\n')[1].trim();
                            break;
                        }
                    }
                    // Get job type
                    var jobType = '';
                    for (var j = 0; j < spans.length; j++) {
                        var st = spans[j].innerText.trim();
                        if (st.indexOf('Job Type') === 0 && st.indexOf('\\n') > -1) {
                            jobType = st.split('\\n')[1].trim();
                            break;
                        }
                    }
                    results.push({title: t, url: h, location: location, dept: dept, jobType: jobType});
                }
                // Fallback: direct a.au-target links with /job/ in href
                if (results.length === 0) {
                    var links = document.querySelectorAll('a.au-target[href*="/job/"], a[href*="/en/job/"]');
                    for (var i = 0; i < links.length; i++) {
                        var a = links[i];
                        var h = a.href;
                        if (!h || seen[h] || h.indexOf('jobcart') > -1) continue;
                        var t = (a.innerText || '').trim().split('\\n')[0];
                        if (t.length > 3 && t.length < 200) {
                            seen[h] = true;
                            results.push({title: t, url: h, location: '', dept: '', jobType: ''});
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
                city, state, _ = self.parse_location(location)

                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': 'India',
                    'employment_type': jdata.get('jobType', ''),
                    'department': jdata.get('dept', ''),
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

            except Exception as e:
                logger.error(f"Error extracting job: {str(e)}")
                continue

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
                    (By.XPATH, "//div[contains(@class, 'job-description')]"),
                    (By.CSS_SELECTOR, 'div.description'),
                ]
                
                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
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

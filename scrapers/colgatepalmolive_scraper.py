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

logger = setup_logger('colgatepalmolive_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class ColgatePalmoliveScraper:
    def __init__(self):
        self.company_name = 'Colgate-Palmolive'
        self.url = 'https://jobs.colgate.com/search-jobs'
    
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
        """Scrape jobs from Colgate-Palmolive careers page with pagination support"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            time.sleep(10)

            current_url = driver.current_url
            logger.info(f"Landed on: {current_url}")

            # If NAS container not found, try the View All Jobs page
            has_nas = 'search-results-list' in driver.page_source
            if not has_nas:
                logger.info("NAS container not found, navigating to View All Jobs page")
                driver.get('https://jobs.colgate.com/go/View-All-Jobs/8506400/')
                time.sleep(10)
                logger.info(f"Redirected to: {driver.current_url}")

            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(3)

            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                page_jobs = self._scrape_page(driver, wait)
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
            next_page_selectors = [
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    next_button.click()
                    logger.info(f"Clicked next page button")
                    return True
                except:
                    continue
            
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs - tries NAS/Radancy first, then generic job link extraction"""
        jobs = []
        time.sleep(3)

        # Scroll to load dynamic content
        for scroll_i in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        # Strategy 1: NAS/Radancy JS extraction
        js_jobs = driver.execute_script("""
            var results = [];
            var seen = {};
            var container = document.querySelector('#search-results-list');
            if (container) {
                var items = container.querySelectorAll('li, div.list-item');
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
            # Strategy 2: Generic job link extraction (SuccessFactors / /go/ pages)
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
                        var parent = a.closest('tr, li, div[class*="job"], article');
                        var location = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], .job-location, td:nth-child(2)');
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

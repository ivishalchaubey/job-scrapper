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

logger = setup_logger('intel_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class IntelScraper:
    def __init__(self):
        self.company_name = 'Intel'
        self.url = 'https://jobs.intel.com/en/search-jobs/India'
    
    def setup_driver(self):
        """Set up Chrome driver with options"""
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        try:
            driver_path = CHROMEDRIVER_PATH
            logger.info(f"ChromeDriver installed at: {driver_path}")
            
            if 'chromedriver-mac-arm64' in driver_path and not driver_path.endswith('chromedriver'):
                import os
                driver_dir = os.path.dirname(driver_path)
                actual_driver = os.path.join(driver_dir, 'chromedriver')
                if os.path.exists(actual_driver):
                    driver_path = actual_driver
                    logger.info(f"Using corrected path: {driver_path}")
            
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
            return driver
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Intel careers page"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(12)  # Phenom platform needs extra time to render

            # Scroll to trigger lazy-loaded content
            logger.info("Scrolling to load dynamic content...")
            last_height = driver.execute_script("return document.body.scrollHeight")
            for scroll_i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

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
            next_page_selectors = [
                (By.XPATH, '//a[@aria-label="View next page"]'),
                (By.CSS_SELECTOR, 'a[aria-label="View next page"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '.pagination-next-link'),
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
            
            logger.warning("Could not find next page button")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(2)
        
        job_cards = []
        selectors = [
            (By.CSS_SELECTOR, 'a[data-ph-at-id="job-link"]'),
            (By.CSS_SELECTOR, '[class*="job-card"]'),
            (By.CSS_SELECTOR, 'a[href*="/job/"]'),
            (By.CSS_SELECTOR, 'li[class*="jobs-list-item"]'),
            (By.CSS_SELECTOR, '.job-item'),
            (By.CSS_SELECTOR, '[data-job-id]'),
            (By.CSS_SELECTOR, 'div[class*="search-result"]'),
            (By.CSS_SELECTOR, 'tr[class*="data-row"]'),
        ]

        for selector_type, selector_value in selectors:
            try:
                wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                job_cards = driver.find_elements(selector_type, selector_value)
                if job_cards and len(job_cards) > 0:
                    logger.info(f"Found {len(job_cards)} job cards using selector: {selector_value}")
                    break
            except:
                continue

        # Link-based fallback
        if not job_cards:
            logger.warning("No job cards found with standard selectors, trying link-based fallback")
            try:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                job_links_found = []
                seen_hrefs = set()
                for link in all_links:
                    try:
                        href = link.get_attribute('href') or ''
                        text = link.text.strip()
                        if not text or len(text) < 3 or href in seen_hrefs:
                            continue
                        href_lower = href.lower()
                        if any(kw in href_lower for kw in ['/job/', 'intel.com/job', '/en/job/']):
                            job_links_found.append(link)
                            seen_hrefs.add(href)
                    except:
                        continue
                if job_links_found:
                    logger.info(f"Fallback found {len(job_links_found)} job links")
                    job_cards = job_links_found
            except:
                pass

        if not job_cards:
            logger.warning("No job cards found")
            return jobs
        
        for idx, card in enumerate(job_cards):
            try:
                card_text = card.text
                if not card_text or len(card_text) < 10:
                    continue
                
                job_title = ""
                job_link = ""
                try:
                    if card.tag_name == 'a':
                        job_title = card.text.strip()
                        job_link = card.get_attribute('href')
                    else:
                        # Try Phenom-specific selectors first
                        phenom_selectors = [
                            (By.CSS_SELECTOR, 'a[data-ph-at-id="job-link"]'),
                            (By.CSS_SELECTOR, 'a[href*="/job/"]'),
                            (By.CSS_SELECTOR, 'a'),
                        ]
                        for sel_type, sel_val in phenom_selectors:
                            try:
                                link_elem = card.find_element(sel_type, sel_val)
                                job_title = link_elem.text.strip()
                                job_link = link_elem.get_attribute('href')
                                if job_title:
                                    break
                            except:
                                continue
                except:
                    try:
                        lines = card_text.split('\n')
                        job_title = lines[0].strip() if lines else ""
                    except:
                        pass

                if not job_title or len(job_title) < 3:
                    continue

                job_id = f"intel_{idx}"
                if job_link:
                    try:
                        if '/job/' in job_link:
                            job_id = job_link.split('/job/')[-1].split('?')[0].split('/')[0]
                        elif '/' in job_link:
                            job_id = job_link.split('/')[-1].split('?')[0]
                    except:
                        pass
                
                location = ""
                city = ""
                state = ""
                try:
                    loc_elem = card.find_element(By.CSS_SELECTOR, '[class*="location"]')
                    location = loc_elem.text.strip()
                    city, state, _ = self.parse_location(location)
                except:
                    pass
                
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
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                
                if FETCH_FULL_JOB_DETAILS and job_link:
                    full_details = self._fetch_job_details(driver, job_link)
                    job_data.update(full_details)
                
                jobs.append(job_data)
                
            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
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
                    (By.CSS_SELECTOR, '.job-description'),
                    (By.CSS_SELECTOR, '[class*="description"]'),
                    (By.CSS_SELECTOR, '[itemprop="description"]'),
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

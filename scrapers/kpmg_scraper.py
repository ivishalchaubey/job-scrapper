from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import re
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('kpmg_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class KPMGScraper:
    def __init__(self):
        self.company_name = 'KPMG'
        self.url = 'https://home.kpmg/in/en/home/careers/job-search.html'
    
    def setup_driver(self):
        """Set up Chrome driver with options"""
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
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
        """Scrape jobs from KPMG India careers page"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            logger.info("Waiting for KPMG careers page to load...")
            time.sleep(12)
            
            # Scroll to load lazy-loaded content
            logger.info("Scrolling page to load all content...")
            last_height = driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scrolls = 5
            
            while scroll_attempts < max_scrolls:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_attempts += 1
                logger.info(f"Scrolled {scroll_attempts} times")
            
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            
            # Check for iframes
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                logger.info(f"Found {len(iframes)} iframes, checking for job listings...")
                for idx, iframe in enumerate(iframes):
                    try:
                        src = iframe.get_attribute('src')
                        logger.info(f"Iframe {idx}: {src}")
                        driver.switch_to.frame(iframe)
                        time.sleep(3)
                        test_elements = driver.find_elements(By.CSS_SELECTOR, 'div[class*="job"], article, li[class*="job"]')
                        if test_elements and len(test_elements) > 5:
                            logger.info(f"Found {len(test_elements)} potential job elements in iframe {idx}")
                            break
                        driver.switch_to.default_content()
                    except Exception as e:
                        logger.debug(f"Error checking iframe {idx}: {e}")
                        driver.switch_to.default_content()
                        continue
            
            page_jobs = self._scrape_page(driver, wait)
            jobs.extend(page_jobs)
            
            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
            
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
        
        finally:
            if driver:
                driver.quit()
        
        return jobs
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from KPMG careers page"""
        jobs = []
        time.sleep(3)
        
        job_elements = []
        selectors = [
            (By.CSS_SELECTOR, 'div.job-tile, div.jobTile, div[class*="JobTile"]'),
            (By.CSS_SELECTOR, 'div[class*="job-card"], div[class*="jobCard"], div[class*="JobCard"]'),
            (By.CSS_SELECTOR, 'article[class*="job"], article.job'),
            (By.CSS_SELECTOR, 'li[class*="job"], li.job-item'),
            (By.CSS_SELECTOR, 'div[data-job], div[data-jobid]'),
            (By.CSS_SELECTOR, 'div.career-opportunity, div[class*="career"]'),
            (By.CSS_SELECTOR, 'div[class*="position"], div[class*="vacancy"]'),
            (By.XPATH, '//div[contains(@class, "search-result")]//a'),
            (By.CSS_SELECTOR, 'a[href*="/careers/"], a[href*="/job"]'),
            (By.CSS_SELECTOR, 'a[href*="kpmg"][href*="career"]'),
            (By.CSS_SELECTOR, 'tr[class*="data-row"]'),
            (By.CSS_SELECTOR, 'a[href*="/job/"]'),
            (By.TAG_NAME, 'article'),
        ]
        
        for selector_type, selector_value in selectors:
            try:
                elements = driver.find_elements(selector_type, selector_value)
                if elements and len(elements) >= 10:
                    logger.info(f"Found {len(elements)} job elements using: {selector_value}")
                    job_elements = elements
                    break
                elif elements and len(elements) >= 5:
                    logger.info(f"Found {len(elements)} potential job elements using: {selector_value}")
                    if not job_elements:
                        job_elements = elements
            except Exception as e:
                logger.debug(f"Selector {selector_value} failed: {str(e)}")
                continue
        
        if not job_elements:
            logger.warning("No job elements found, trying alternative approach...")
            try:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                job_links = []
                seen_hrefs = set()
                for link in all_links:
                    try:
                        href = link.get_attribute('href') or ''
                        text = link.text.strip()
                        if not text or len(text) < 3 or href in seen_hrefs:
                            continue
                        href_lower = href.lower()
                        if any(keyword in href_lower for keyword in ['job', 'career', 'position', 'vacancy', '/job/', 'jobid']):
                            # Skip navigation/footer links
                            skip_texts = ['apply now', 'view all', 'next', 'previous', 'page', 'home', 'back', 'filter', 'sort', 'search', 'sign in', 'log in']
                            if any(sk in text.lower() for sk in skip_texts) and len(text) < 25:
                                continue
                            job_links.append(link)
                            seen_hrefs.add(href)
                    except:
                        continue
                if job_links:
                    logger.info(f"Found {len(job_links)} job links via fallback")
                    job_elements = job_links
            except:
                pass
        
        if not job_elements:
            logger.warning("No job elements found")
            try:
                page_text = driver.page_source[:3000]
                logger.debug(f"Page source preview: {page_text}")
            except:
                pass
            return jobs
        
        for idx, element in enumerate(job_elements):
            try:
                job_title = ""
                job_link = ""
                location = ""
                
                if element.tag_name == 'a':
                    job_title = element.text.strip()
                    job_link = element.get_attribute('href')
                    if not job_title:
                        try:
                            parent = element.find_element(By.XPATH, '..')
                            job_title = parent.text.strip().split('\n')[0]
                        except:
                            pass
                else:
                    try:
                        link = element.find_element(By.TAG_NAME, 'a')
                        job_title = link.text.strip()
                        job_link = link.get_attribute('href')
                    except:
                        try:
                            title_elem = element.find_element(By.CSS_SELECTOR, 'h2, h3, h4, span[class*="title"], div[class*="title"]')
                            job_title = title_elem.text.strip()
                        except:
                            job_title = element.text.strip().split('\n')[0] if element.text else ""
                        
                        try:
                            link_elem = element.find_element(By.TAG_NAME, 'a')
                            job_link = link_elem.get_attribute('href')
                        except:
                            pass
                
                if not job_title or len(job_title) < 3:
                    continue
                
                skip_keywords = ['apply now', 'view all', 'next', 'previous', 'page', 'home', 'back', 'filter', 'sort', 'search']
                if any(keyword in job_title.lower() for keyword in skip_keywords) and len(job_title) < 25:
                    continue
                
                job_id = f"kpmg_{idx}"
                if job_link:
                    try:
                        match = re.search(r'/job/([^/]+)', job_link, re.IGNORECASE)
                        if match:
                            job_id = f"kpmg_{match.group(1)}"
                        else:
                            job_id = hashlib.md5(job_link.encode()).hexdigest()[:12]
                    except:
                        job_id = hashlib.md5(job_link.encode()).hexdigest()[:12]
                
                try:
                    element_text = element.text if hasattr(element, 'text') else ""
                    lines = element_text.split('\n')
                    for line in lines:
                        if any(city in line for city in ['Mumbai', 'Delhi', 'Bangalore', 'Bengaluru', 'Hyderabad', 'Chennai', 'Pune', 'Kolkata', 'Gurgaon', 'Gurugram', 'Noida', 'India']):
                            location = line.strip()
                            break
                except:
                    pass
                
                city, state, _ = self.parse_location(location)
                
                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': job_title,
                    'description': '',
                    'location': location if location else 'India',
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
                
                if FETCH_FULL_JOB_DETAILS and job_link and job_link != self.url:
                    full_details = self._fetch_job_details(driver, job_link)
                    job_data.update(full_details)
                
                jobs.append(job_data)
                logger.info(f"Extracted job: {job_title}")
                
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
            time.sleep(4)
            
            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div[class*="jobDescription"], div[class*="job-description"]'),
                    (By.CSS_SELECTOR, 'div[id*="description"]'),
                    (By.XPATH, '//div[contains(@class, "description")]'),
                    (By.CSS_SELECTOR, 'span[class*="jobDescriptionText"]'),
                    (By.XPATH, "//h2[contains(text(), 'Description')]/following-sibling::div"),
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
                location_selectors = [
                    (By.CSS_SELECTOR, 'span[class*="location"]'),
                    (By.XPATH, "//label[contains(text(), 'Location')]/following-sibling::span"),
                    (By.CSS_SELECTOR, 'div[class*="location"]'),
                ]
                
                for selector_type, selector_value in location_selectors:
                    try:
                        loc_elem = driver.find_element(selector_type, selector_value)
                        if loc_elem and loc_elem.text.strip():
                            location_text = loc_elem.text.strip()
                            if location_text:
                                details['location'] = location_text
                                city, state, _ = self.parse_location(location_text)
                                details['city'] = city
                                details['state'] = state
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

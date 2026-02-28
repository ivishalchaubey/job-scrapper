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
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, MAX_PAGES_TO_SCRAPE, FETCH_FULL_JOB_DETAILS

logger = setup_logger('jll_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class JLLScraper:
    def __init__(self):
        self.company_name = 'JLL'
        # Using JLL Workday careers page
        self.url = 'https://jll.wd1.myworkdayjobs.com/en-GB/jllcareers'
    
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
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            # Install and get the correct chromedriver path
            driver_path = CHROMEDRIVER_PATH
            logger.info(f"ChromeDriver installed at: {driver_path}")
            
            # Fix for macOS ARM - ensure we use the actual chromedriver binary
            if 'chromedriver-mac-arm64' in driver_path and not driver_path.endswith('chromedriver'):
                import os
                driver_dir = os.path.dirname(driver_path)
                actual_driver = os.path.join(driver_dir, 'chromedriver')
                if os.path.exists(actual_driver):
                    driver_path = actual_driver
                    logger.info(f"Using corrected path: {driver_path}")
            
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            # Fallback: try without service specification
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
            return driver
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from JLL Workday careers page with pagination"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Smart wait for Workday job listings
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'li[data-automation-id="listItem"]'))
                )
                logger.info("Workday job listings loaded")
            except:
                logger.warning("Timeout waiting for Workday listings, using fallback wait")
                time.sleep(5)
            
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                # Scrape current page
                page_jobs = self._scrape_page(driver)
                jobs.extend(page_jobs)
                
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")
                
                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    # No extra sleep — _go_to_next_page already handles waiting
                
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
        """Navigate to next page in Workday"""
        try:
            next_page_num = current_page + 1
            
            # Scroll to pagination
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            # Capture current state for change detection
            old_first = driver.execute_script("""
                var card = document.querySelector('li[data-automation-id="listItem"]');
                return card ? card.innerText.substring(0, 50) : '';
            """)

            # Workday pagination selectors
            next_selectors = [
                (By.XPATH, f'//button[@aria-label="{next_page_num}"]'),
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'button[data-uxi-widget-type="page"][aria-label="{next_page_num}"]'),
                (By.XPATH, '//button[@aria-label="next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="next"]'),
            ]

            for selector_type, selector_value in next_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Navigated to page {next_page_num}")

                    # Poll for content change
                    for _ in range(25):
                        time.sleep(0.2)
                        new_first = driver.execute_script("""
                            var card = document.querySelector('li[data-automation-id="listItem"]');
                            return card ? card.innerText.substring(0, 50) : '';
                        """)
                        if new_first and new_first != old_first:
                            break
                    time.sleep(0.5)
                    return True
                except:
                    continue
            
            logger.warning("Could not find next page button")
            return False
            
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver):
        """Scrape jobs from current Workday page"""
        jobs = []
        wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
        # Quick scroll for lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.3)
        
        # Workday job listing selectors
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
                
                # Extract job title (usually a link)
                job_title = ""
                job_link = ""
                
                try:
                    title_link = card.find_element(By.TAG_NAME, 'a')
                    job_title = title_link.get_attribute('aria-label') or title_link.text.strip()
                    job_link = title_link.get_attribute('href')
                except:
                    # Fallback to first line
                    job_title = card_text.split('\n')[0].strip()
                
                if not job_title or len(job_title) < 3:
                    continue
                
                # Extract Job ID (like REQ480281)
                job_id = ""
                lines = card_text.split('\n')
                for line in lines:
                    if line.startswith('REQ') and len(line) < 15:
                        job_id = line.strip()
                        break
                
                if not job_id:
                    # Try to extract from URL
                    if job_link and '/job/' in job_link:
                        job_id = job_link.split('/job/')[-1].split('/')[0]
                    else:
                        job_id = f"jll_{hashlib.md5(job_title.encode()).hexdigest()[:12]}"
                
                # Extract location and work type
                location = ""
                city = ""
                state = ""
                remote_type = ""
                posted_date = ""
                
                for line in lines:
                    line_stripped = line.strip()
                    
                    # Location (city, state format)
                    if ',' in line_stripped and len(line_stripped.split(',')) == 2:
                        parts = line_stripped.split(',')
                        if len(parts[1].strip()) == 2:  # State abbreviation like MO, KY, TX
                            location = line_stripped
                            city = parts[0].strip()
                            state = parts[1].strip()
                    
                    # Work type
                    if 'On-site' in line_stripped:
                        remote_type = 'On-site'
                    elif 'Remote' in line_stripped:
                        remote_type = 'Remote'
                    elif 'Hybrid' in line_stripped:
                        remote_type = 'Hybrid'
                    
                    # Posted date
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
                    'country': '',  # Not India specific anymore
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
                
                # Fetch full details if enabled
                if FETCH_FULL_JOB_DETAILS and job_link and job_link != self.url:
                    full_details = self._fetch_job_details(driver, job_link)
                    job_data.update(full_details)
                
                jobs.append(job_data)
                logger.info(f"Successfully added job: {job_title}")
                
            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                continue
        
        return jobs
    
    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}
        
        try:
            # Open job in new tab
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
            driver.get(job_url)
            time.sleep(5)  # Workday pages need time to load
            
            # Extract job description
            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div[data-automation-id="jobPostingDescription"]'),
                    (By.XPATH, '//div[@data-automation-id="jobPostingDescription"]'),
                    (By.CSS_SELECTOR, 'div.css-12xvhzt'),
                    (By.XPATH, '//h2[contains(text(), "What this job involves")]//ancestor::div[1]'),
                ]
                
                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        if desc_elem and desc_elem.text.strip():
                            full_text = desc_elem.text.strip()
                            
                            # Remove common JLL boilerplate text
                            cleaned_text = self._clean_jll_description(full_text)
                            
                            details['description'] = cleaned_text[:2000]
                            logger.debug(f"Extracted description using: {selector_value}")
                            break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"Error extracting description: {str(e)}")
            
            # Extract employment type
            try:
                employment_selectors = [
                    (By.XPATH, '//dd[contains(text(), "Full time") or contains(text(), "Part time") or contains(text(), "Contract")]'),
                    (By.CSS_SELECTOR, 'dd[data-automation-id="jobPostingType"]'),
                ]
                
                for selector_type, selector_value in employment_selectors:
                    try:
                        emp_elem = driver.find_element(selector_type, selector_value)
                        if emp_elem and emp_elem.text.strip():
                            details['employment_type'] = emp_elem.text.strip()
                            logger.debug(f"Extracted employment type: {details['employment_type']}")
                            break
                    except:
                        continue
            except:
                pass
            
            # Extract location details
            try:
                loc_selectors = [
                    (By.CSS_SELECTOR, 'dd[data-automation-id="locations"]'),
                    (By.XPATH, '//dd[contains(@class, "location")]'),
                ]
                
                for selector_type, selector_value in loc_selectors:
                    try:
                        loc_elem = driver.find_element(selector_type, selector_value)
                        if loc_elem and loc_elem.text.strip():
                            location_text = loc_elem.text.strip()
                            details['location'] = location_text
                            city, state, country = self.parse_location(location_text)
                            if city:
                                details['city'] = city
                            if state:
                                details['state'] = state
                            if country:
                                details['country'] = country
                            logger.debug(f"Extracted location: {location_text}")
                            break
                    except:
                        continue
            except:
                pass
            
            # Extract posted date
            try:
                date_selectors = [
                    (By.CSS_SELECTOR, 'dd[data-automation-id="postedOn"]'),
                    (By.XPATH, '//dd[contains(text(), "Posted")]'),
                ]
                
                for selector_type, selector_value in date_selectors:
                    try:
                        date_elem = driver.find_element(selector_type, selector_value)
                        if date_elem and date_elem.text.strip():
                            details['posted_date'] = date_elem.text.strip()
                            logger.debug(f"Extracted posted date: {details['posted_date']}")
                            break
                    except:
                        continue
            except:
                pass
            
            # Close tab and return to search results
            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            # Make sure we return to original window
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass
        
        return details
    
    def _clean_jll_description(self, description):
        """Remove common JLL boilerplate text and extract only relevant job details"""
        # Common boilerplate text to remove
        boilerplate_phrases = [
            "JLL empowers you to shape a brighter way.",
            "Our people at JLL and JLL Technologies are shaping the future of real estate",
            "We are committed to hiring the best, most talented people",
            "Whether you've got deep experience in commercial real estate",
            "join our team as we help shape a brighter way forward"
        ]
        
        # Remove boilerplate sections
        cleaned = description
        for phrase in boilerplate_phrases:
            if phrase in cleaned:
                # Find the end of this boilerplate section
                idx = cleaned.find(phrase)
                # Look for the next major section (usually starts with a heading)
                end_markers = [
                    "\n\nWhat this job involves:",
                    "\nWhat this job involves:",
                    "What this job involves:",
                    "\n\nJob Title",
                    "\nJob Title"
                ]
                
                for marker in end_markers:
                    marker_idx = cleaned.find(marker)
                    if marker_idx > idx:
                        # Remove everything before the marker
                        cleaned = cleaned[marker_idx:].strip()
                        break
        
        # Extract from "What this job involves:" onwards
        if "What this job involves:" in cleaned:
            start_idx = cleaned.find("What this job involves:")
            cleaned = cleaned[start_idx:]
        
        return cleaned.strip()
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', ''
        
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        country = parts[2] if len(parts) > 2 else ''
        
        return city, state, country

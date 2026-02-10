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
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, MAX_PAGES_TO_SCRAPE, FETCH_FULL_JOB_DETAILS

logger = setup_logger('accenture_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class AccentureScraper:
    def __init__(self):
        self.company_name = 'Accenture'
        self.url = 'https://www.accenture.com/in-en/careers/jobsearch?ct=Ahmedabad%7CBengaluru%7CBhubaneswar%7CChennai%7CCoimbatore%7CGandhinagar%7CGurugram%7CHyderabad%7CIndore%7CJaipur%7CKochi%7CKolkata%7CMumbai%7CNagpur%7CNavi%20Mumbai%7CNew%20Delhi%7CNoida%7CPune%7CThiruvananthapuram'
    
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
        """Scrape jobs from Accenture careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load
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
                    time.sleep(4)  # Wait for next page to load
                
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
            
            # Scroll to pagination area
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            # Try to find and click next page button
            next_page_selectors = [
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'button[aria-label="Go to page {next_page_num}"]'),
                (By.XPATH, '//button[@aria-label="Go to next page"]'),
                (By.XPATH, '//button[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'button.pagination-next'),
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
    
    def _scrape_page(self, driver):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(3)  # Wait for page content to load
        
        # Look for job cards by the correct class
        job_cards = []
        
        try:
            # Find job cards using the actual class from Accenture's page
            job_cards = driver.find_elements(By.CSS_SELECTOR, "div.rad-filters-vertical__job-card")
            if job_cards:
                logger.info(f"Found {len(job_cards)} job cards")
        except Exception as e:
            logger.error(f"Error finding job cards: {str(e)}")
        
        if not job_cards:
            logger.warning("No job cards found")
            return jobs
        
        # Process each job card
        for idx, card in enumerate(job_cards):
            try:
                # Extract job title from h3
                job_title = ""
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, "h3.rad-filters-vertical__job-card-title")
                    job_title = title_elem.text.strip()
                except:
                    logger.debug(f"Could not extract title for card {idx}")
                    continue
                
                if not job_title or len(job_title) < 3:
                    logger.debug(f"Skipping card {idx}: Title too short")
                    continue
                
                # Extract job link
                job_link = ""
                job_number = ""
                try:
                    link_elem = card.find_element(By.CSS_SELECTOR, 'a[href*="jobdetails"]')
                    job_link = link_elem.get_attribute('href')
                    
                    # Extract job ID from URL
                    if 'id=' in job_link:
                        job_number = job_link.split('id=')[-1].split('&')[0]
                except:
                    logger.debug(f"Could not extract link for card {idx}")
                    # Try to get job number from the card content
                    try:
                        job_num_elem = card.find_element(By.CSS_SELECTOR, "span.rad-filters-vertical__job-card-content-job-number-dynamic-text")
                        job_number = job_num_elem.text.strip()
                    except:
                        pass
                
                # Extract location
                location = ""
                city = ""
                state = ""
                try:
                    loc_elem = card.find_element(By.CSS_SELECTOR, "span.rad-filters-vertical__job-card-details-location")
                    location = loc_elem.text.strip()
                    city, state, _ = self.parse_location(location)
                except:
                    pass
                
                # Extract employment type
                employment_type = ""
                try:
                    schedule_elem = card.find_element(By.CSS_SELECTOR, "span.rad-filters-vertical__job-card-details-schedule")
                    employment_type = schedule_elem.text.strip()
                except:
                    pass
                
                # Extract experience level
                experience_level = ""
                try:
                    exp_elem = card.find_element(By.CSS_SELECTOR, "span.rad-filters-vertical__job-card-details-type")
                    experience_level = exp_elem.text.strip()
                except:
                    pass
                
                # Generate external ID
                if job_number:
                    external_id = self.generate_external_id(job_number, self.company_name)
                else:
                    external_id = self.generate_external_id(f"accenture_{hashlib.md5(job_title.encode()).hexdigest()[:12]}", self.company_name)
                
                # If no job link, construct one
                if not job_link and job_number:
                    job_link = f"https://www.accenture.com/in-en/careers/jobdetails?id={job_number}&title={job_title.replace(' ', '+')}"
                elif not job_link:
                    job_link = self.url
                
                logger.info(f"Found job: '{job_title}' (ID: {job_number})")
                
                job_data = {
                    'external_id': external_id,
                    'company_name': self.company_name,
                    'title': job_title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': 'India',
                    'employment_type': employment_type,
                    'department': '',
                    'apply_url': job_link,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': experience_level,
                    'salary_range': '',
                    'remote_type': '',
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
                import traceback
                logger.error(traceback.format_exc())
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
            time.sleep(4)
            
            # Try to click the accordion/read more button for job description
            try:
                # Look for accordion button or "Read more" link
                accordion_selectors = [
                    (By.XPATH, "//button[contains(@class, 'rad-accordion-atom__title')]"),
                    (By.XPATH, "//button[contains(text(), 'Read more')]"),
                    (By.XPATH, "//button[contains(text(), 'Read full job description')]"),
                    (By.XPATH, "//a[contains(text(), 'Read more')]"),
                ]
                
                for selector_type, selector_value in accordion_selectors:
                    try:
                        accordion_button = driver.find_element(selector_type, selector_value)
                        driver.execute_script("arguments[0].scrollIntoView();", accordion_button)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", accordion_button)
                        time.sleep(2)
                        logger.info("Clicked accordion/read more button")
                        break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"No accordion button found: {str(e)}")
            
            # Extract job description from accordion content
            try:
                desc_elem = None
                selectors = [
                    # Target the specific accordion content wrapper
                    (By.CSS_SELECTOR, "div.rad-accordion-atom__content-wrapper.rad-accordion-atom__content-wrapper--open div.rad-accordion-atom__content"),
                    (By.CSS_SELECTOR, "div.rad-accordion-atom__content"),
                    (By.CSS_SELECTOR, "div[id*='job-description-content'] div.rad-accordion-atom__content"),
                    # Fallback selectors
                    (By.XPATH, "//div[contains(@class, 'job-description')]"),
                    (By.XPATH, "//*[contains(text(), 'Job description')]/following-sibling::div"),
                    (By.XPATH, "//h2[contains(text(), 'Job Description')]//following::div[1]"),
                ]
                
                for selector_type, selector_value in selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        if desc_elem and desc_elem.text.strip():
                            details['description'] = desc_elem.text.strip()[:2000]
                            logger.debug(f"Extracted description using selector: {selector_value}")
                            break
                    except:
                        continue
                
                if not details.get('description'):
                    logger.debug("Could not extract description from any selector")
            except Exception as e:
                logger.debug(f"Error extracting description: {str(e)}")
            
            # Extract locations
            try:
                loc_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'Location')]//following::div[1] | //h2[contains(text(), 'Locations')]//following::div[1]")
                location_text = loc_elem.text.strip()
                if location_text:
                    # Take first location if multiple
                    first_location = location_text.split('\n')[0]
                    details['location'] = first_location
                    city, state, _ = self.parse_location(first_location)
                    if city:
                        details['city'] = city
                    if state:
                        details['state'] = state
                    logger.debug(f"Extracted location: {first_location}")
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
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'
        
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        
        return city, state, 'India'

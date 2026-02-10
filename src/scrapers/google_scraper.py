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

logger = setup_logger('google_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class GoogleScraper:
    def __init__(self):
        self.company_name = 'Google'
        self.url = 'https://careers.google.com/jobs/results/?location=India'
    
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
        """Scrape jobs from Google careers page"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(6)  # Give extra time for JavaScript to load
            
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
            # Scroll to bottom of page to ensure pagination button is loaded
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Google careers uses "Go to next page" link at the bottom
            next_page_selectors = [
                (By.LINK_TEXT, 'Go to next page'),
                (By.PARTIAL_LINK_TEXT, 'Go to next'),
                (By.XPATH, '//a[contains(text(), "next")]'),
                (By.XPATH, '//a[contains(@aria-label, "next") or contains(@aria-label, "Next")]'),
                (By.CSS_SELECTOR, 'a[aria-label*="next"], a[aria-label*="Next"]'),
                # Try pagination links by checking for page numbers
                (By.XPATH, f'//a[contains(text(), "{current_page + 1}")]'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    # Make sure it's visible
                    if next_button.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                        time.sleep(1)
                        # Click using JavaScript to avoid click interception
                        driver.execute_script("arguments[0].click();", next_button)
                        logger.info(f"Clicked next page button successfully")
                        time.sleep(4)  # Wait for new page to load
                        
                        # Scroll back to top to see all jobs
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(1)
                        return True
                except Exception as e:
                    continue
            
            logger.warning("Could not find next page button - may be on last page")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(5)
        
        # Scroll down multiple times to load more jobs (lazy loading)
        logger.info("Scrolling to load more jobs...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scrolls = 5  # Scroll up to 5 times to load more jobs
        
        while scroll_attempts < max_scrolls:
            # Scroll down
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Wait for content to load
            
            # Check if new content loaded
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                # No new content, stop scrolling
                break
            
            last_height = new_height
            scroll_attempts += 1
            logger.info(f"Scrolled {scroll_attempts} times, loading more jobs...")
        
        # Scroll back to top to ensure all elements are in the DOM
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # Find all h3 elements - these contain job titles
        try:
            h3_elements = driver.find_elements(By.TAG_NAME, 'h3')
            logger.info(f"Total h3 elements found: {len(h3_elements)}")
            
            # Filter to only job titles (those that are long enough and not filter names)
            job_title_elements = []
            filter_keywords = ['Locations', 'Experience', 'Skills', 'Degree', 'Job types', 
                             'Organizations', 'Sort by', 'Search', 'Follow']
            
            for h3 in h3_elements:
                h3_text = h3.text.strip()
                # Job titles are usually longer and don't match filter keywords
                if h3_text and len(h3_text) > 10 and not any(keyword in h3_text for keyword in filter_keywords):
                    job_title_elements.append(h3)
            
            logger.info(f"Filtered to {len(job_title_elements)} potential job title elements")
            
            if not job_title_elements:
                logger.error("No job title elements found")
                return jobs
            
        except Exception as e:
            logger.error(f"Error finding h3 elements: {str(e)}")
            return jobs
        
        for idx, h3_elem in enumerate(job_title_elements):
            try:
                # Get job title from h3
                job_title = h3_elem.text.strip()
                
                if not job_title or len(job_title) < 3:
                    continue
                
                # Find the parent container for this job (go up to find the list item or card)
                parent = h3_elem
                job_link = ""
                location = ""
                city = ""
                state = ""
                
                try:
                    # Go up to find the job card container
                    for _ in range(6):  # Go up max 6 levels
                        parent = parent.find_element(By.XPATH, '..')
                        parent_tag = parent.tag_name.lower()
                        
                        # Stop if we found a list item or article
                        if parent_tag in ['li', 'article', 'div']:
                            parent_text = parent.text
                            # Check if this looks like a complete job card
                            if parent_text and 'India' in parent_text and len(parent_text) > 50:
                                break
                    
                    # Try to find a link within this container
                    try:
                        link_elem = parent.find_element(By.XPATH, './/a[contains(@href, "/jobs/results/")]')
                        job_link = link_elem.get_attribute('href')
                    except:
                        # Try to find any link in the parent
                        try:
                            link_elem = parent.find_element(By.TAG_NAME, 'a')
                            job_link = link_elem.get_attribute('href')
                        except:
                            pass
                    
                    # Extract location from parent text
                    parent_text = parent.text
                    lines = [line.strip() for line in parent_text.split('\n') if line.strip()]
                    
                    for line in lines:
                        if 'Google |' in line or 'YouTube |' in line:
                            location_parts = line.split('|')
                            if len(location_parts) > 1:
                                location = location_parts[1].strip()
                                city, state, _ = self.parse_location(location)
                                break
                        elif 'India' in line and '|' not in line and 'Minimum' not in line and 'qualifications' not in line:
                            # This might be a direct location line
                            if any(city_name in line for city_name in ['Bengaluru', 'Mumbai', 'Delhi', 'Hyderabad', 'Pune', 'Chennai', 'Gurugram', 'Gurgaon', 'Noida']):
                                location = line.strip()
                                city, state, _ = self.parse_location(location)
                                break
                    
                except Exception as e:
                    logger.warning(f"Could not find parent container for job {idx}: {str(e)}")
                
                # Extract job ID from URL or use index
                job_id = f"google_{idx}"
                if job_link and '/jobs/results/' in job_link:
                    try:
                        url_parts = job_link.split('/jobs/results/')[-1]
                        job_id = url_parts.split('-')[0].split('?')[0]
                    except:
                        pass
                
                if not job_link:
                    job_link = self.url
                
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
                    'apply_url': job_link,
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
                logger.debug(f"Extracted job {idx + 1}: {job_title}")
                
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
                    (By.CSS_SELECTOR, '[itemprop="description"]'),
                    (By.CSS_SELECTOR, '.description'),
                    (By.CSS_SELECTOR, '[class*="description"]'),
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
        
        # Remove "Google |" or "YouTube |" if present
        location_str = location_str.replace('Google |', '').replace('YouTube |', '').strip()
        
        # Split by comma
        parts = [p.strip() for p in location_str.split(',')]
        
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        
        # Clean up common variations
        if city:
            city = city.strip()
        if state:
            state = state.strip()
        
        return city, state, 'India'

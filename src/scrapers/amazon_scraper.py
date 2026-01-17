from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import hashlib
import time
from datetime import datetime
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('amazon_scraper')

class AmazonScraper:
    def __init__(self):
        self.company_name = 'Amazon'
        self.url = 'https://www.amazon.jobs/en/search?base_query=&loc_query=India&type=area&longitude=77.21676&latitude=28.63141&country=IND'
    
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
            driver_path = ChromeDriverManager().install()
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
        # Use job ID + company name for stable external ID
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Amazon careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(5)  # Wait for dynamic content
            
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                # Scrape current page
                page_jobs = self._scrape_page(driver, wait)
                jobs.extend(page_jobs)
                
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")
                
                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(3)  # Wait for next page to load
                
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
            # Method 1: Click on next page number
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
                    logger.info(f"Clicked next page button using selector: {selector_value}")
                    return True
                except:
                    continue
            
            # Method 2: Modify URL with offset parameter
            current_url = driver.current_url
            if 'offset=' in current_url:
                # Update offset
                import re
                new_offset = current_page * 10  # Assuming 10 jobs per page
                new_url = re.sub(r'offset=\d+', f'offset={new_offset}', current_url)
                driver.get(new_url)
                logger.info(f"Navigated to next page via URL modification")
                return True
            else:
                # Add offset parameter
                separator = '&' if '?' in current_url else '?'
                new_url = f"{current_url}{separator}offset={current_page * 10}"
                driver.get(new_url)
                logger.info(f"Navigated to next page via URL modification")
                return True
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(2)  # Wait for page content
        
        # Try multiple selectors for job listings
        job_cards = []
        selectors = [
            (By.CSS_SELECTOR, 'div.job-tile'),
            (By.CSS_SELECTOR, 'div[class*="job"]'),
            (By.XPATH, '//div[contains(@class, "result")]'),
            (By.TAG_NAME, 'article'),
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
        
        if not job_cards:
            # Fallback: get all job links
            logger.warning("Standard selectors failed, using fallback method")
            all_links = driver.find_elements(By.TAG_NAME, 'a')
            job_links = [link for link in all_links if '/jobs/' in link.get_attribute('href') or 'Job ID' in link.text]
            
            for idx, link in enumerate(job_links):
                try:
                    job_title = link.text.strip().split('\n')[0]
                    if not job_title or len(job_title) < 3:
                        continue
                        
                    job_url = link.get_attribute('href')
                    
                    # Extract Job ID from nearby text or URL
                    job_id = f"amazon_{idx}"
                    try:
                        parent = link.find_element(By.XPATH, '..')
                        parent_text = parent.text
                        if 'Job ID:' in parent_text:
                            job_id = parent_text.split('Job ID:')[-1].strip().split()[0]
                    except:
                        pass
                    
                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': job_title,
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': job_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    
                    jobs.append(job_data)
                    
                except Exception as e:
                    logger.error(f"Error in fallback extraction {idx}: {str(e)}")
                    continue
        else:
            # Extract from job cards
            for idx, card in enumerate(job_cards):
                try:
                    card_text = card.text
                    if not card_text or len(card_text) < 10:
                        continue
                    
                    # Get job title (first link or first line)
                    job_title = ""
                    job_link = ""
                    try:
                        title_link = card.find_element(By.TAG_NAME, 'a')
                        job_title = title_link.text.strip()
                        job_link = title_link.get_attribute('href')
                    except:
                        job_title = card_text.split('\n')[0].strip()
                    
                    if not job_title or len(job_title) < 3:
                        continue
                    
                    # Extract Job ID
                    job_id = f"amazon_{idx}"
                    if 'Job ID:' in card_text:
                        try:
                            job_id = card_text.split('Job ID:')[-1].strip().split()[0]
                        except:
                            pass
                    elif job_link and '/jobs/' in job_link:
                        job_id = job_link.split('/jobs/')[-1].split('?')[0].split('/')[0]
                    
                    # Extract location
                    location = ""
                    city = ""
                    state = ""
                    lines = card_text.split('\n')
                    for line in lines:
                        if ', IND' in line or 'India' in line:
                            location = line.split('|')[0].strip()
                            city, state, _ = self.parse_location(location)
                            break
                    
                    # Extract posted date
                    posted_date = ""
                    for line in lines:
                        if 'Posted' in line:
                            posted_date = line.replace('Posted', '').strip()
                            break
                    
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
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    
                    # Fetch full details if enabled
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
            # Open job in new tab to avoid losing search results page
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
            driver.get(job_url)
            time.sleep(3)
            
            # Extract description - try multiple selectors
            try:
                # Try to find the Description heading and get all following text
                desc_section = driver.find_element(By.XPATH, "//h2[contains(text(), 'Description')]/parent::div")
                details['description'] = desc_section.text.strip()[:2000]  # Limit to 2000 chars
            except:
                try:
                    # Fallback: look for description div
                    desc_elem = driver.find_element(By.CSS_SELECTOR, 'div[class*="description"]')
                    details['description'] = desc_elem.text.strip()[:2000]
                except:
                    try:
                        # Last resort: get the main content area
                        main_content = driver.find_element(By.CSS_SELECTOR, 'main, div[role="main"]')
                        # Get text after Description heading
                        full_text = main_content.text
                        if 'Description' in full_text:
                            desc_start = full_text.index('Description') + len('Description')
                            # Get text until next major heading or end
                            desc_text = full_text[desc_start:].split('\n\n')[0]
                            details['description'] = desc_text.strip()[:2000]
                    except:
                        pass
            
            # Extract department from Job details section
            try:
                # Look for department link (e.g., "Fulfillment & Operations Management")
                dept_elem = driver.find_element(By.CSS_SELECTOR, 'a[href*="/jobs/category/"]')
                details['department'] = dept_elem.text.strip()
            except:
                try:
                    # Fallback: look for link containing "category" anywhere
                    dept_elem = driver.find_element(By.XPATH, "//a[contains(@href, 'category')]")
                    details['department'] = dept_elem.text.strip()
                except:
                    try:
                        # Last resort: look in Job details section specifically
                        dept_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'Job details')]/following-sibling::*//a")
                        details['department'] = dept_elem.text.strip()
                    except:
                        pass
            
            # Extract precise location from Job details section  
            try:
                # Look for location text (e.g., "IND, TS, Hyderabad")
                location_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'IND,')]")
                details['location'] = location_elem.text.strip()
            except:
                pass
            
            # Close tab and return to search results
            driver.close()
            driver.switch_to.window(original_window)
            
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

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

logger = setup_logger('deloitte_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class DeloitteScraper:
    def __init__(self):
        self.company_name = 'Deloitte'
        self.url = 'https://apply.deloitte.com/careers/SearchJobs/india'
    
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

            # Hide automation indicators
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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
        """Scrape jobs from Deloitte careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load - Deloitte page has dynamic loading
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            
            # Handle potential cookie consent or privacy popups
            try:
                time.sleep(3)  # Wait for any popups to appear
                # Try to close cookie/privacy popups
                popup_close_selectors = [
                    'button[id*="accept"]',
                    'button[id*="cookie"]',
                    'button[class*="accept"]',
                    'button[aria-label*="Accept"]',
                    'button[aria-label*="Close"]',
                    'a[class*="close"]',
                ]
                for selector in popup_close_selectors:
                    try:
                        popup_btn = driver.find_element(By.CSS_SELECTOR, selector)
                        popup_btn.click()
                        logger.info(f"Closed popup using selector: {selector}")
                        time.sleep(1)
                        break
                    except:
                        continue
            except:
                pass
            
            # Wait for the search results section to load first
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'section.section--search-jobs')))
                logger.info("Search jobs section loaded")
            except:
                logger.warning("Could not find search section")
            
            # Wait for the job count indicator to appear (confirms page loaded)
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'span.jobListTotalRecords')))
                job_count_elem = driver.find_element(By.CSS_SELECTOR, 'span.jobListTotalRecords')
                total_jobs = job_count_elem.text
                logger.info(f"Job list page loaded successfully - Total jobs available: {total_jobs}")
            except:
                logger.warning("Could not find job count indicator, but continuing...")
            
            time.sleep(5)  # Additional wait for dynamic content to render
            
            # Scroll page to trigger any lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            
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
            next_page_num = current_page + 1
            
            # Deloitte uses specific aria-labels for pagination
            next_page_selectors = [
                (By.XPATH, f'//a[contains(@aria-label, "Go to Next Page")]'),
                (By.XPATH, f'//a[contains(@aria-label, "Go to Page Number {next_page_num}")]'),
                (By.XPATH, f'//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    # Scroll to element
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", next_button)
                    time.sleep(1)
                    # Try clicking with JavaScript if regular click fails
                    try:
                        next_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Clicked next page button using selector: {selector_value}")
                    time.sleep(2)  # Wait for page to load
                    return True
                except Exception as e:
                    logger.debug(f"Could not click with selector {selector_value}: {e}")
                    continue
            
            logger.warning("Could not find next page button")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(3)  # Wait for page content to load
        
        try:
            # Wait for job results to appear - Deloitte uses article--result class
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article.article--result')))
        except Exception as e:
            logger.warning(f"Timeout waiting for job listings: {e}")
        
        # Find all job listings using the correct Deloitte selector
        job_listings = []
        
        try:
            # Deloitte uses article.article--result for each job listing
            job_listings = driver.find_elements(By.CSS_SELECTOR, 'article.article--result')
            logger.info(f"Found {len(job_listings)} job listings")
        except Exception as e:
            logger.error(f"Error finding job listings: {e}")
            return jobs
        
        if not job_listings:
            logger.warning("No job listings found on page")
            logger.info(f"Page title: {driver.title}")
            logger.info(f"Current URL: {driver.current_url}")
            # Save page source for debugging
            try:
                with open('deloitte_no_jobs_debug.html', 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                logger.info("Saved debug page source to deloitte_no_jobs_debug.html")
            except Exception as debug_err:
                logger.error(f"Could not save debug page: {debug_err}")
            return jobs
        
        # Extract data from each job listing
        for idx, listing in enumerate(job_listings):
            try:
                # Find the job title and link
                job_title = ""
                job_url = ""
                
                try:
                    # Deloitte structure: h3.article__header__text__title > a
                    title_link = listing.find_element(By.CSS_SELECTOR, 'h3.article__header__text__title a')
                    job_title = title_link.text.strip()
                    job_url = title_link.get_attribute('href')
                except Exception as e:
                    logger.debug(f"Error finding title link for job {idx}: {e}")
                    continue
                
                if not job_title or not job_url:
                    logger.debug(f"Skipping listing {idx} - no title or URL found")
                    continue
                
                # Extract job ID from URL
                job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]
                
                # Extract location information from subtitle
                location = ""
                city = ""
                state = ""
                country = "United States"  # Default for this URL
                department = ""
                
                try:
                    # Deloitte structure: div.article__header__text__subtitle contains spans
                    # Format: "Deloitte US | Department | City, State, Country"
                    subtitle_elem = listing.find_element(By.CSS_SELECTOR, 'div.article__header__text__subtitle')
                    subtitle_spans = subtitle_elem.find_elements(By.TAG_NAME, 'span')
                    
                    # Last span typically contains location
                    if subtitle_spans:
                        # Try to find location span (contains comma)
                        for span in subtitle_spans:
                            span_text = span.text.strip()
                            if ',' in span_text or any(state_name in span_text for state_name in ['United States', 'India', 'Canada']):
                                location = span_text
                                break
                        
                        # Extract department from middle spans
                        if len(subtitle_spans) >= 2:
                            dept_text = subtitle_spans[1].text.strip()
                            if dept_text and dept_text not in ['Deloitte US', '|']:
                                department = dept_text
                    
                    # Parse location if found
                    if location:
                        city, state, country = self.parse_location(location)
                    
                except Exception as e:
                    logger.debug(f"Error extracting location for job {idx}: {e}")
                
                # Extract additional metadata if available
                employment_type = ""
                
                try:
                    # Look for job metadata in the listing text
                    metadata_text = listing.text
                    if 'Full-time' in metadata_text or 'Full Time' in metadata_text:
                        employment_type = 'Full-time'
                    elif 'Part-time' in metadata_text or 'Part Time' in metadata_text:
                        employment_type = 'Part-time'
                    elif 'Contract' in metadata_text:
                        employment_type = 'Contract'
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
                    'country': country,
                    'employment_type': employment_type,
                    'department': department,
                    'apply_url': job_url,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                
                # Fetch full details if enabled
                if FETCH_FULL_JOB_DETAILS and job_url:
                    full_details = self._fetch_job_details(driver, job_url)
                    job_data.update(full_details)
                
                jobs.append(job_data)
                logger.debug(f"Extracted job: {job_title} - {location}")
                
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
            
            # Extract description
            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, "//h2[contains(text(), 'Description')]/following-sibling::div"),
                    (By.CSS_SELECTOR, 'div.job-description'),
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
            return '', '', 'United States'
        
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        
        # Determine country based on location string
        country = 'United States'
        location_lower = location_str.lower()
        if any(country_name in location_lower for country_name in ['india', 'bangalore', 'mumbai', 'delhi', 'hyderabad', 'chennai', 'pune']):
            country = 'India'
        elif any(country_name in location_lower for country_name in ['uk', 'united kingdom', 'london', 'manchester']):
            country = 'United Kingdom'
        elif any(country_name in location_lower for country_name in ['canada', 'toronto', 'vancouver']):
            country = 'Canada'
        
        return city, state, country

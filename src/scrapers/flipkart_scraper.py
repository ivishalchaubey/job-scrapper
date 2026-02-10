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

logger = setup_logger('flipkart_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class FlipkartScraper:
    def __init__(self):
        self.company_name = 'Flipkart'
        # Use job search page with hash routing
        self.url = 'https://www.flipkartcareers.com/#!/job-listing'
        self.base_url = 'https://www.flipkartcareers.com'
    
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
        """Scrape jobs from Flipkart careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            
            # Navigate to jobs page using direct URL (bypasses hash routing)
            logger.info(f"Navigating to {self.url}")
            driver.get(self.url)
            
            # Wait for page to load - Flipkart uses Angular SPA
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            logger.info("Waiting for Angular app to initialize...")
            time.sleep(20)  # Angular SPA needs extra time for API calls
            
            # Check current URL
            current_url = driver.current_url
            logger.info(f"Current URL: {current_url}")
            
            # If we're on homepage, use hash navigation to job listing view
            if 'job-listing' not in current_url.lower() and 'jobview' not in current_url.lower():
                logger.info("Navigating to job listing view...")
                try:
                    driver.execute_script("window.location.hash = '#!/job-listing'")
                    time.sleep(5)
                    current_url = driver.current_url
                    logger.info(f"URL after hash: {current_url}")
                except Exception as e:
                    logger.warning(f"Hash navigation failed: {e}")
            
            # Wait for Angular to finish loading and making API calls
            logger.info("Waiting for Angular to load jobs data (25 seconds)...")
            time.sleep(25)  # Angular apps often need more time for API calls
            
            # Scroll to trigger any lazy loading - more aggressive
            logger.info("Scrolling to trigger content loading...")
            for i in range(6):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                driver.execute_script(f"window.scrollTo(0, {i * 300});")
                time.sleep(1)
            
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)
            
            # Try clicking "View All" or "Show More" buttons
            try:
                buttons = driver.find_elements(By.XPATH, '//button[contains(text(), "View")] | //button[contains(text(), "Show")] | //a[contains(text(), "View All")]')
                for btn in buttons:
                    try:
                        if btn.is_displayed():
                            btn.click()
                            time.sleep(3)
                            break
                    except:
                        pass
            except:
                pass
            
            current_page = 1
            all_scraped_ids = set()
            
            while current_page <= max_pages:
                logger.info(f"Scraping page/scroll iteration {current_page} of {max_pages}")
                
                # Scrape current page
                page_jobs = self._scrape_page(driver, wait)
                
                # Filter out duplicates
                new_jobs = [j for j in page_jobs if j['external_id'] not in all_scraped_ids]
                for job in new_jobs:
                    all_scraped_ids.add(job['external_id'])
                    jobs.append(job)
                
                logger.info(f"Page {current_page}: Found {len(new_jobs)} new jobs (total: {len(jobs)})")
                
                # If no new jobs found, try scrolling more
                if current_page < max_pages and len(new_jobs) > 0:
                    # Scroll down to load more jobs
                    prev_height = driver.execute_script("return document.body.scrollHeight")
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(3)
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    
                    # If height didn't change, try pagination
                    if new_height == prev_height:
                        if not self._go_to_next_page(driver, current_page):
                            logger.info("No more pages/content available")
                            break
                        time.sleep(3)
                elif len(new_jobs) == 0:
                    logger.info("No new jobs found, ending scrape")
                    break
                
                current_page += 1
            
            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
            
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
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
                    logger.info(f"Clicked next page button using selector: {selector_value}")
                    return True
                except:
                    continue
            
            logger.warning("Could not find next page button")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page - IMPROVED VERSION"""
        jobs = []
        
        try:
            logger.info(f"Current URL: {driver.current_url}")
            logger.info(f"Page title: {driver.title}")
            
            time.sleep(3)
            
            # STRATEGY 1: Extract from Angular/React data
            logger.info("Trying to extract from page data...")
            try:
                jobs_data = driver.execute_script("""
                    var jobs = [];
                    // Check Angular scope
                    if (typeof angular !== 'undefined') {
                        try {
                            var elem = document.querySelector('[ng-controller], [ng-app]');
                            if (elem) {
                                var scope = angular.element(elem).scope();
                                if (scope && scope.jobs) jobs = scope.jobs;
                                if (scope && scope.jobsList) jobs = scope.jobsList;
                            }
                        } catch(e) {}
                    }
                    // Check window object
                    if (window.jobsData) jobs = window.jobsData;
                    if (window.jobs && Array.isArray(window.jobs)) jobs = window.jobs;
                    
                    return jobs;
                """)
                
                if jobs_data and len(jobs_data) > 0:
                    logger.info(f"Found {len(jobs_data)} jobs from page data")
                    for idx, job_obj in enumerate(jobs_data):
                        try:
                            if isinstance(job_obj, dict):
                                title = job_obj.get('title') or job_obj.get('jobTitle') or ''
                                if title and len(title) > 3:
                                    location = job_obj.get('location') or 'India'
                                    city, state, _ = self.parse_location(location)
                                    job_id = job_obj.get('id') or f"flipkart_{idx}"
                                    
                                    jobs.append({
                                        'external_id': self.generate_external_id(str(job_id), self.company_name),
                                        'company_name': self.company_name,
                                        'title': title,
                                        'description': job_obj.get('description', '')[:2000],
                                        'location': location,
                                        'city': city,
                                        'state': state,
                                        'country': 'India',
                                        'employment_type': job_obj.get('employmentType', ''),
                                        'department': job_obj.get('department', ''),
                                        'apply_url': job_obj.get('url') or self.base_url,
                                        'posted_date': job_obj.get('postedDate', ''),
                                        'job_function': '',
                                        'experience_level': '',
                                        'salary_range': '',
                                        'remote_type': '',
                                        'status': 'active'
                                    })
                        except Exception as e:
                            logger.debug(f"Error parsing job object: {e}")
                    
                    if jobs:
                        logger.info(f"Successfully extracted {len(jobs)} jobs from page data")
                        return jobs
            except Exception as e:
                logger.debug(f"Could not extract from page data: {e}")
            
            # STRATEGY 2: Find job links
            logger.info("Looking for job links...")
            all_links = driver.find_elements(By.TAG_NAME, 'a')
            job_links = []
            
            for link in all_links:
                try:
                    text = link.text.strip()
                    if text and 10 < len(text) < 200:
                        # Exclude navigation links
                        exclude_words = ['home', 'about', 'contact', 'login', 'register', 
                                       'facebook', 'twitter', 'linkedin', 'privacy', 'terms',
                                       'all jobs', 'view jobs', 'search', 'filter', 'apply filter']
                        if not any(word in text.lower() for word in exclude_words):
                            href = link.get_attribute('href') or ''
                            # Include if href suggests job or text looks like job title
                            job_url_patterns = ['job', 'career', 'position', 'opening', 'requisition']
                            job_title_words = ['engineer', 'manager', 'developer', 'analyst', 'designer',
                                             'architect', 'lead', 'specialist', 'consultant', 'director',
                                             'associate', 'executive', 'coordinator', 'scientist', 'intern']
                            if any(p in href.lower() for p in job_url_patterns) or any(word in text.lower() for word in job_title_words):
                                job_links.append(link)
                except:
                    continue
            
            if len(job_links) >= 1:
                logger.info(f"Found {len(job_links)} potential job links")
                for idx, link in enumerate(job_links):
                    try:
                        title = link.text.strip()
                        href = link.get_attribute('href') or ''
                        
                        # Try to get more context from parent
                        try:
                            parent = link.find_element(By.XPATH, '..')
                            parent_text = parent.text.strip()
                        except:
                            parent_text = title
                        
                        location = 'India'
                        for city in ['Bangalore', 'Bengaluru', 'Mumbai', 'Delhi', 'Hyderabad', 'Chennai', 'Pune']:
                            if city in parent_text:
                                location = city
                                break
                        
                        city, state, _ = self.parse_location(location)
                        job_id = href.split('#')[-1] if '#' in href else f"flipkart_link_{idx}"
                        
                        jobs.append({
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
                            'apply_url': href if href.startswith('http') else self.base_url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })
                    except Exception as e:
                        logger.debug(f"Error extracting job from link: {e}")
                
                if jobs:
                    logger.info(f"Extracted {len(jobs)} jobs from links")
                    return jobs
            
            # STRATEGY 3: Table-based jobs
            logger.info("Looking for table rows...")
            tables = driver.find_elements(By.TAG_NAME, 'table')
            for table in tables:
                rows = table.find_elements(By.CSS_SELECTOR, 'tbody tr, tr')
                valid_rows = []
                for row in rows:
                    try:
                        if row.text.strip() and len(row.text.strip()) > 30:
                            links = row.find_elements(By.TAG_NAME, 'a')
                            if links:
                                valid_rows.append(row)
                    except:
                        pass
                
                if len(valid_rows) >= 5:
                    logger.info(f"Found {len(valid_rows)} table rows")
                    for idx, row in enumerate(valid_rows):
                        try:
                            cells = row.find_elements(By.TAG_NAME, 'td')
                            if cells:
                                title = cells[0].text.strip()
                                location = cells[1].text.strip() if len(cells) > 1 else 'India'
                                links = row.find_elements(By.TAG_NAME, 'a')
                                apply_url = links[0].get_attribute('href') if links else self.base_url
                                
                                if title and len(title) > 3:
                                    city, state, _ = self.parse_location(location)
                                    jobs.append({
                                        'external_id': self.generate_external_id(f"flipkart_table_{idx}", self.company_name),
                                        'company_name': self.company_name,
                                        'title': title,
                                        'description': '',
                                        'location': location,
                                        'city': city,
                                        'state': state,
                                        'country': 'India',
                                        'employment_type': '',
                                        'department': '',
                                        'apply_url': apply_url,
                                        'posted_date': '',
                                        'job_function': '',
                                        'experience_level': '',
                                        'salary_range': '',
                                        'remote_type': '',
                                        'status': 'active'
                                    })
                        except Exception as e:
                            logger.debug(f"Error extracting from row: {e}")
                    
                    if jobs:
                        return jobs
            
            # If nothing found
            if not jobs:
                logger.warning("No jobs found with any strategy")
                try:
                    # Save debug info
                    import os
                    debug_file = f'/tmp/flipkart_debug_{int(time.time())}.html'
                    with open(debug_file, 'w') as f:
                        f.write(driver.page_source)
                    logger.info(f"Saved page source to {debug_file}")
                    
                    screenshot_file = f'/tmp/flipkart_debug_{int(time.time())}.png'
                    driver.save_screenshot(screenshot_file)
                    logger.info(f"Saved screenshot to {screenshot_file}")
                    
                    body_text = driver.find_element(By.TAG_NAME, 'body').text
                    logger.info(f"Page text (first 1000 chars): {body_text[:1000]}")
                except:
                    pass
        
        except Exception as e:
            logger.error(f"Error in _scrape_page: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        return jobs
    def _extract_job_from_element(self, elem, driver, idx):
        """Extract job data from a single element"""
        try:
            elem_text = elem.text.strip()
            if not elem_text or len(elem_text) < 10:
                return None
            
            # Get job title
            job_title = ""
            job_link = ""
            
            # Try to find title and link
            title_selectors = [
                (By.TAG_NAME, 'h3'),
                (By.TAG_NAME, 'h4'),
                (By.TAG_NAME, 'h2'),
                (By.CSS_SELECTOR, '[class*="title"]'),
                (By.CSS_SELECTOR, '[class*="heading"]'),
                (By.TAG_NAME, 'a'),
            ]
            
            for selector_type, selector_value in title_selectors:
                try:
                    title_elem = elem.find_element(selector_type, selector_value)
                    text = title_elem.text.strip()
                    if text and len(text) > 5:
                        job_title = text.split('\n')[0].strip()
                        # Try to get link
                        if title_elem.tag_name == 'a':
                            job_link = title_elem.get_attribute('href') or ''
                        else:
                            try:
                                link_elem = title_elem.find_element(By.XPATH, './/a | ./ancestor::a')
                                job_link = link_elem.get_attribute('href') or ''
                            except:
                                pass
                        break
                except:
                    continue
            
            # Fallback: use first line as title
            if not job_title:
                lines = elem_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 5 and len(line) < 150:
                        job_title = line
                        break
            
            if not job_title or len(job_title) < 3:
                return None
            
            # Try to find link if not found yet
            if not job_link:
                try:
                    link_elem = elem.find_element(By.TAG_NAME, 'a')
                    job_link = link_elem.get_attribute('href') or ''
                except:
                    pass
            
            # Extract Job ID
            job_id = f"flipkart_{idx}_{hashlib.md5(job_title.encode()).hexdigest()[:8]}"
            if job_link:
                # Try to extract ID from URL
                for pattern in ['/job/', '/jobview/', '?id=', '&id=']:
                    if pattern in job_link:
                        try:
                            parts = job_link.split(pattern)[-1].split('?')[0].split('&')[0].split('/')[0]
                            if parts:
                                job_id = parts
                                break
                        except:
                            pass
            
            # Extract location
            location = ""
            city = ""
            state = ""
            lines = elem_text.split('\n')
            for line in lines[1:]:  # Skip title line
                line = line.strip()
                # Look for location indicators
                if any(indicator in line for indicator in ['India', 'Bangalore', 'Bengaluru', 'Mumbai', 'Delhi', 
                                                            'Hyderabad', 'Chennai', 'Pune', 'Gurgaon', 'Gurugram',
                                                            'Noida', 'Kolkata']):
                    location = line
                    city, state, _ = self.parse_location(location)
                    break
            
            # Extract department/category
            department = ""
            for line in lines[1:]:
                line = line.strip()
                if line and line != location and line != job_title:
                    # Check if it looks like a department
                    if len(line) < 80 and not any(x in line.lower() for x in ['http', 'www', 'apply', 'posted']):
                        department = line
                        break
            
            # Extract posted date
            posted_date = ""
            for line in lines:
                line_lower = line.lower()
                if 'ago' in line_lower or 'posted' in line_lower or 'day' in line_lower:
                    posted_date = line.strip()
                    break
            
            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': job_title,
                'description': '',
                'location': location or 'India',
                'city': city,
                'state': state,
                'country': 'India',
                'employment_type': '',
                'department': department,
                'apply_url': job_link if job_link else self.url,
                'posted_date': posted_date,
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }
            
            # Fetch full details if enabled
            if FETCH_FULL_JOB_DETAILS and job_link and 'http' in job_link:
                try:
                    full_details = self._fetch_job_details(driver, job_link)
                    job_data.update(full_details)
                except Exception as e:
                    logger.warning(f"Could not fetch details for {job_title}: {e}")
            
            return job_data
            
        except Exception as e:
            logger.error(f"Error extracting job from element: {str(e)}")
            return None
    
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
                desc_elem = driver.find_element(By.CSS_SELECTOR, 'div[class*="description"]')
                details['description'] = desc_elem.text.strip()[:2000]
            except:
                pass
            
            # Extract department
            try:
                dept_elem = driver.find_element(By.CSS_SELECTOR, 'span[class*="department"]')
                details['department'] = dept_elem.text.strip()
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

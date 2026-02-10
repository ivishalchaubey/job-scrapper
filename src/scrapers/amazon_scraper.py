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

logger = setup_logger('amazon_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class AmazonScraper:
    def __init__(self):
        self.company_name = 'Amazon'
        self.url = 'https://www.amazon.jobs/en/search?base_query=&loc_query=India'
    
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
        # Use job ID + company name for stable external ID
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Amazon careers page with pagination support"""
        jobs = []
        driver = None
        seen_job_ids = set()  # Track unique jobs to avoid duplicates
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            logger.info("Waiting for initial page load...")
            time.sleep(8)  # Wait longer for dynamic content to load
            
            # Wait for job results to appear
            try:
                wait.until(EC.presence_of_element_located((By.TAG_NAME, 'a')))
                logger.info("Page content loaded")
            except:
                logger.warning("Timeout waiting for page content")
            
            # Scroll to trigger any lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(3)
            
            current_page = 1
            consecutive_empty_pages = 0
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                # Scrape current page
                page_jobs = self._scrape_page(driver, wait)
                
                # Filter out duplicates
                unique_page_jobs = []
                for job in page_jobs:
                    job_id = job['external_id']
                    if job_id not in seen_job_ids:
                        seen_job_ids.add(job_id)
                        unique_page_jobs.append(job)
                
                jobs.extend(unique_page_jobs)
                
                logger.info(f"Scraped {len(unique_page_jobs)} unique jobs from page {current_page} (total: {len(jobs)})")
                
                # Check if we got no jobs
                if len(unique_page_jobs) == 0:
                    consecutive_empty_pages += 1
                    logger.warning(f"No jobs found on page {current_page} (consecutive empty: {consecutive_empty_pages})")
                    
                    # If we get 2 consecutive empty pages, stop
                    if consecutive_empty_pages >= 2:
                        logger.info("Got 2 consecutive empty pages, stopping pagination")
                        break
                else:
                    consecutive_empty_pages = 0
                
                # Try to load more jobs
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more jobs available to load")
                        break
                    time.sleep(5)  # Wait for new jobs to load
                    
                    # Scroll to top to see newly loaded jobs
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(2)
                
                current_page += 1
            
            logger.info(f"Successfully scraped {len(jobs)} total unique jobs from {self.company_name}")
            
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            # Don't raise, return what we have
            logger.info(f"Returning {len(jobs)} jobs collected before error")
        
        finally:
            if driver:
                driver.quit()
        
        return jobs
    
    def _go_to_next_page(self, driver, current_page):
        """Load more jobs by clicking the 'Load more jobs' button"""
        try:
            # Amazon uses a "Load more jobs" button instead of traditional pagination
            logger.info(f"Looking for 'Load more jobs' button to load page {current_page + 1}")
            
            # Scroll to bottom gradually to trigger any lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            # Get all buttons on the page
            all_buttons = driver.find_elements(By.TAG_NAME, 'button')
            logger.info(f"Found {len(all_buttons)} buttons on page")
            
            load_more_button = None
            
            # Search through all buttons for one with "load more" text
            for button in all_buttons:
                try:
                    button_text = button.text.strip().lower()
                    if button_text and ('load more' in button_text or 'loadmore' in button_text):
                        load_more_button = button
                        logger.info(f"Found 'Load more' button with text: '{button.text}'")
                        break
                except:
                    continue
            
            # If not found by text, try by common class patterns
            if not load_more_button:
                button_selectors = [
                    (By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more')]"),
                    (By.XPATH, "//button[contains(@class, 'load')]"),
                    (By.CSS_SELECTOR, "button[class*='load']"),
                    (By.CSS_SELECTOR, "button[class*='Load']"),
                    (By.XPATH, "//button[contains(@aria-label, 'load')]"),
                    (By.XPATH, "//button[contains(@aria-label, 'Load')]"),
                ]
                
                for selector_type, selector_value in button_selectors:
                    try:
                        buttons = driver.find_elements(selector_type, selector_value)
                        for button in buttons:
                            button_text = button.text.strip().lower()
                            aria_label = button.get_attribute('aria-label') or ''
                            if ('load' in button_text and 'more' in button_text) or ('load' in aria_label.lower() and 'more' in aria_label.lower()):
                                load_more_button = button
                                logger.info(f"Found 'Load more' button using selector: {selector_value}")
                                break
                        if load_more_button:
                            break
                    except:
                        continue
            
            if not load_more_button:
                logger.warning("No 'Load more jobs' button found - trying URL-based pagination as fallback")
                # Log all buttons for debugging
                button_texts = []
                for btn in all_buttons[:10]:  # Just first 10
                    try:
                        text = btn.text.strip()
                        if text:
                            button_texts.append(text)
                    except:
                        pass
                if button_texts:
                    logger.info(f"Available buttons: {', '.join(button_texts[:5])}")
                
                # Fallback: Try URL-based pagination with offset
                return self._try_url_pagination(driver, current_page)
            
            # Check if button is visible and enabled
            if not load_more_button.is_displayed():
                logger.warning("'Load more' button exists but is not visible")
                return False
            
            # Scroll button into view
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_button)
            time.sleep(1)
            
            # Click the button
            try:
                load_more_button.click()
                logger.info("Clicked 'Load more jobs' button")
            except:
                # Fallback: use JavaScript click
                driver.execute_script("arguments[0].click();", load_more_button)
                logger.info("Clicked 'Load more jobs' button using JavaScript")
            
            # Wait for new jobs to load
            time.sleep(4)
            
            # Scroll to load any lazy-loaded content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(2)
            
            logger.info(f"Successfully loaded more jobs for page {current_page + 1}")
            return True
                
        except Exception as e:
            logger.error(f"Error loading more jobs: {str(e)}")
            return False
    
    def _try_url_pagination(self, driver, current_page):
        """Fallback method: try URL-based pagination with offset parameter"""
        try:
            # Amazon might use offset parameter: each page shows 10 jobs
            # So offset should be: 10, 20, 30, etc. (0 is the first page)
            new_offset = current_page * 10
            
            # Build new URL with updated offset
            base_url = 'https://www.amazon.jobs/en/search'
            params = f'?base_query=&loc_query=India&offset={new_offset}'
            new_url = base_url + params
            
            logger.info(f"Trying URL pagination with offset {new_offset}: {new_url}")
            
            # Store current job count to verify new jobs loaded
            current_url = driver.current_url
            driver.get(new_url)
            
            # Wait for page to load
            time.sleep(5)
            
            # Scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            
            # Verify URL changed or we're on a different page
            new_current_url = driver.current_url
            if new_current_url != current_url or f'offset={new_offset}' in new_current_url:
                logger.info(f"Successfully navigated using URL pagination")
                return True
            else:
                logger.warning(f"URL pagination might not have worked")
                # Try anyway - maybe the URL doesn't reflect the offset
                return True
                
        except Exception as e:
            logger.error(f"Error in URL pagination: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        
        # Scroll to load all content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight*2/3);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        
        # Scroll back to top to see all jobs
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        
        # Amazon's job search results contain "Read more" links with job IDs
        # Pattern: "Read more about the job <Title>, job Id <ID>"
        # Extract all job links with job IDs from these "Read more" links
        
        logger.info("Searching for job links with IDs...")
        all_links = driver.find_elements(By.TAG_NAME, 'a')
        
        job_info_map = {}  # Map job_id to job info
        
        # First pass: Find all "Read more" links with job IDs
        # Also find title links and match them with job IDs from URLs
        for link in all_links:
            try:
                href = link.get_attribute('href')
                text = link.text.strip()
                
                if not href or '/jobs/' not in href:
                    continue
                
                # Extract job ID from URL: /jobs/3082316/...
                job_id = None
                try:
                    url_parts = href.split('/jobs/')
                    if len(url_parts) > 1:
                        job_id_from_url = url_parts[1].split('/')[0].split('?')[0]
                        if job_id_from_url and (job_id_from_url.isdigit() or len(job_id_from_url) > 5):
                            job_id = job_id_from_url
                except:
                    pass
                
                if not job_id:
                    continue
                
                # Method 1: "Read more about the job Title, job Id XXXXX" format
                if 'job Id' in text and 'Read more' in text:
                    parts = text.split('job Id')
                    if len(parts) >= 2:
                        # Extract title from the text
                        title_part = parts[0].replace('Read more about the job', '').strip()
                        # Remove trailing comma and whitespace
                        title_part = title_part.rstrip(', ')
                        
                        if title_part and len(title_part) > 3:
                            job_info_map[job_id] = {
                                'title': title_part,
                                'apply_url': href,
                                'job_id': job_id
                            }
                            continue
                
                # Method 2: Regular title link (not "Read more")
                if text and len(text) > 3 and 'Read more' not in text and 'job Id' not in text:
                    # This is likely the job title link
                    if job_id not in job_info_map:
                        job_info_map[job_id] = {
                            'title': text.split('\n')[0].strip(),
                            'apply_url': href,
                            'job_id': job_id
                        }
                
            except Exception as e:
                continue
        
        logger.info(f"Found {len(job_info_map)} jobs with IDs from 'Read more' links")
        
        # Try to find job cards to extract additional information like location
        job_cards = []
        selectors = [
            # Most accurate Amazon selectors first
            (By.CSS_SELECTOR, 'div.job-tile'),
            (By.CSS_SELECTOR, 'div[data-test="job-tile"]'),
            (By.CSS_SELECTOR, 'article.job'),
            (By.CSS_SELECTOR, 'div.job'),
            (By.CSS_SELECTOR, '[class*="JobCard"]'),
            (By.CSS_SELECTOR, '[class*="job-listing"]'),
            (By.XPATH, '//div[contains(@class, "job") and .//a[contains(@href, "/jobs/")]]'),
            (By.TAG_NAME, 'article'),
        ]
        
        for selector_type, selector_value in selectors:
            try:
                job_cards = driver.find_elements(selector_type, selector_value)
                if job_cards and len(job_cards) > 0:
                    logger.info(f"Found {len(job_cards)} job cards using selector: {selector_value}")
                    break
            except:
                continue
        
        # If we have job_info_map from "Read more" links, use that as the primary source
        if job_info_map:
            logger.info(f"Using job info map with {len(job_info_map)} jobs")
            
            # If we also have job cards, try to enrich with location data
            location_map = {}
            if job_cards:
                for card in job_cards:
                    try:
                        card_text = card.text
                        if not card_text:
                            continue
                        
                        # Find job ID in card by looking for links
                        card_links = card.find_elements(By.TAG_NAME, 'a')
                        card_job_id = None
                        
                        for clink in card_links:
                            clink_text = clink.text.strip()
                            if 'job Id' in clink_text:
                                parts = clink_text.split('job Id')
                                if len(parts) >= 2:
                                    card_job_id = parts[-1].strip().split()[0].replace(',', '').replace('.', '')
                                    break
                        
                        if not card_job_id:
                            continue
                        
                        # Extract location from card
                        location = ""
                        lines = card_text.split('\n')
                        for line in lines:
                            # Look for Indian locations
                            if any(indicator in line for indicator in [', IND', 'India', 'IND,', ', IN']):
                                location = line.split('|')[0].strip()
                                break
                            # Also check for city names
                            elif any(city_name in line for city_name in ['Bangalore', 'Hyderabad', 'Mumbai', 'Delhi', 'Chennai', 'Pune', 'Gurgaon', 'Noida', 'Bengaluru']):
                                location = line.strip()
                                break
                        
                        if location:
                            location_map[card_job_id] = location
                    except:
                        continue
                
                logger.info(f"Extracted location data for {len(location_map)} jobs from cards")
            
            # Create job data from job_info_map
            for job_id, job_info in job_info_map.items():
                location = location_map.get(job_id, '')
                city, state, _ = self.parse_location(location) if location else ('', '', 'India')
                
                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': job_info['title'],
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': 'India',
                    'employment_type': '',
                    'department': '',
                    'apply_url': job_info['apply_url'],
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                
                jobs.append(job_data)
            
            return jobs
        
        # Fallback: extract from job cards if no job_info_map
        if job_cards:
            # Extract from job cards
            for idx, card in enumerate(job_cards):
                try:
                    card_text = card.text
                    if not card_text or len(card_text) < 10:
                        continue
                    
                    # Get job title and link
                    job_title = ""
                    job_link = ""
                    
                    # Try multiple methods to find the job title link
                    try:
                        # Method 1: Find link with job URL
                        title_links = card.find_elements(By.TAG_NAME, 'a')
                        for link in title_links:
                            href = link.get_attribute('href')
                            if href and '/jobs/' in href:
                                job_link = href
                                job_title = link.text.strip()
                                if job_title and len(job_title) > 3:
                                    break
                    except:
                        pass
                    
                    # Method 2: Try h3 or h2 tags
                    if not job_title:
                        try:
                            title_elem = card.find_element(By.CSS_SELECTOR, 'h3, h2, h1')
                            job_title = title_elem.text.strip()
                        except:
                            pass
                    
                    # Method 3: Use first line of card text
                    if not job_title:
                        job_title = card_text.split('\n')[0].strip()
                    
                    # Clean up job title
                    job_title = job_title.split('\n')[0].strip()
                    if not job_title or len(job_title) < 3:
                        continue
                    
                    # If no job link found, try to find any link in the card
                    if not job_link:
                        try:
                            any_link = card.find_element(By.TAG_NAME, 'a')
                            href = any_link.get_attribute('href')
                            if href and 'amazon.jobs' in href:
                                job_link = href
                        except:
                            pass
                    
                    # Extract Job ID from URL or text
                    job_id = f"amazon_{idx}"
                    if 'Job ID:' in card_text or 'Job ID ' in card_text:
                        try:
                            # Find the job ID in text
                            id_text = card_text
                            if 'Job ID:' in id_text:
                                job_id = id_text.split('Job ID:')[-1].strip().split()[0]
                            elif 'Job ID ' in id_text:
                                job_id = id_text.split('Job ID ')[-1].strip().split()[0]
                            # Remove any trailing punctuation
                            job_id = job_id.rstrip('.,;:')
                        except:
                            pass
                    
                    # Extract from URL if not found in text
                    if job_id.startswith('amazon_') and job_link and '/jobs/' in job_link:
                        try:
                            job_id_part = job_link.split('/jobs/')[1].split('/')[0].split('?')[0]
                            if job_id_part and (job_id_part.isdigit() or len(job_id_part) > 5):
                                job_id = job_id_part
                        except:
                            pass
                    
                    # Extract location - Amazon typically shows it as "City, State, Country"
                    location = ""
                    city = ""
                    state = ""
                    lines = card_text.split('\n')
                    
                    for line in lines:
                        # Look for Indian locations
                        if any(indicator in line for indicator in [', IND', 'India', 'IND,', ', IN']):
                            location = line.split('|')[0].strip()
                            city, state, _ = self.parse_location(location)
                            break
                        # Also check for city names
                        elif any(city_name in line for city_name in ['Bangalore', 'Hyderabad', 'Mumbai', 'Delhi', 'Chennai', 'Pune', 'Gurgaon', 'Noida', 'Bengaluru']):
                            location = line.strip()
                            city, state, _ = self.parse_location(location)
                            break
                    
                    # Extract posted date
                    posted_date = ""
                    for line in lines:
                        if 'Posted' in line or 'posted' in line:
                            posted_date = line.replace('Posted', '').replace('posted', '').strip()
                            break
                    
                    # Extract department if visible
                    department = ""
                    for line in lines:
                        # Amazon shows department/team info
                        if any(keyword in line.lower() for keyword in ['team:', 'department:', 'category:']):
                            department = line.split(':')[-1].strip()
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
                    if FETCH_FULL_JOB_DETAILS and job_link:
                        try:
                            full_details = self._fetch_job_details(driver, job_link)
                            job_data.update(full_details)
                        except Exception as e:
                            logger.warning(f"Could not fetch full details for job {job_id}: {str(e)}")
                    
                    jobs.append(job_data)
                    
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue
        else:
            # Final fallback: extract from any job links on the page
            logger.warning("No job cards or job_info_map found, using final fallback")
            all_links = driver.find_elements(By.TAG_NAME, 'a')
            
            seen_urls = set()
            for link in all_links:
                try:
                    href = link.get_attribute('href')
                    text = link.text.strip()
                    
                    # Skip if not a job link or already seen
                    if not href or '/jobs/' not in href or 'amazon.jobs' not in href:
                        continue
                    if href in seen_urls:
                        continue
                    
                    # Skip "Read more" links
                    if 'Read more' in text or 'job Id' in text:
                        continue
                    
                    # Must have some text that looks like a job title
                    if not text or len(text) < 5:
                        continue
                    
                    seen_urls.add(href)
                    
                    # Extract job ID from URL
                    job_id = f"amazon_fallback_{len(jobs)}"
                    if '/jobs/' in href:
                        try:
                            job_id_part = href.split('/jobs/')[1].split('/')[0].split('?')[0]
                            if job_id_part and (job_id_part.isdigit() or len(job_id_part) > 5):
                                job_id = job_id_part
                        except:
                            pass
                    
                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': text.split('\n')[0].strip(),
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': href,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    
                    jobs.append(job_data)
                    
                except Exception as e:
                    continue
            
            logger.info(f"Extracted {len(jobs)} jobs using final fallback method")
        
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
        
        # Clean up the location string
        location_str = location_str.strip()
        
        # Remove common prefixes
        location_str = location_str.replace('Location:', '').strip()
        
        # Split by comma or pipe
        if '|' in location_str:
            parts = [p.strip() for p in location_str.split('|')[0].split(',')]
        else:
            parts = [p.strip() for p in location_str.split(',')]
        
        city = ''
        state = ''
        
        # Parse based on number of parts
        if len(parts) >= 3:
            # Format: "City, State, Country" or "City, State Code, Country"
            city = parts[0]
            state = parts[1]
        elif len(parts) == 2:
            # Format: "City, State" or "City, Country"
            city = parts[0]
            # Check if second part is likely a state or country
            if parts[1] in ['IND', 'IN', 'India']:
                state = ''
            else:
                state = parts[1]
        elif len(parts) == 1:
            # Just city name
            city = parts[0]
        
        # Clean up state codes (e.g., "TS" -> "Telangana", "KA" -> "Karnataka")
        state_mapping = {
            'TS': 'Telangana',
            'KA': 'Karnataka',
            'MH': 'Maharashtra',
            'DL': 'Delhi',
            'TN': 'Tamil Nadu',
            'HR': 'Haryana',
            'UP': 'Uttar Pradesh',
            'WB': 'West Bengal',
            'GJ': 'Gujarat',
            'RJ': 'Rajasthan',
            'PB': 'Punjab',
        }
        
        if state in state_mapping:
            state = state_mapping[state]
        
        return city, state, 'India'

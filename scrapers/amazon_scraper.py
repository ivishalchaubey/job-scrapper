from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import sys
sys.path.append('.')
from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE
from scrapers.csv_url_resolver import get_company_url

logger = setup_logger('amazon_scraper')

class AmazonScraper:
    def __init__(self):
        self.company_name = "Amazon"
        default_url = "https://www.amazon.jobs/en/search?base_query=&loc_query=India&type=area&longitude=77.21676&latitude=28.63141&country=IND"
        self.url = get_company_url(self.company_name, default_url)
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
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
            
            # Wait for page to load — smart wait instead of blind sleep
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            logger.info("Waiting for initial page load...")
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/jobs/"]')))
                logger.info("Page content loaded")
            except:
                logger.warning("Timeout waiting for page content, using fallback wait")
                time.sleep(5)

            # Quick scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
            
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
                    # No extra sleep needed — _go_to_next_page already waits
                
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
            
            # Quick scroll to bottom to find the button
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
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
            time.sleep(0.5)

            # Capture current job count for change detection
            old_count = len(driver.find_elements(By.CSS_SELECTOR, 'a[href*="/jobs/"]'))

            # Click the button
            try:
                load_more_button.click()
                logger.info("Clicked 'Load more jobs' button")
            except:
                driver.execute_script("arguments[0].click();", load_more_button)
                logger.info("Clicked 'Load more jobs' button using JavaScript")

            # Poll until new jobs appear (max 6s, usually <2s)
            for _ in range(30):
                time.sleep(0.2)
                new_count = len(driver.find_elements(By.CSS_SELECTOR, 'a[href*="/jobs/"]'))
                if new_count > old_count:
                    break
            time.sleep(0.5)
            
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

            # Smart wait for job links instead of blind sleep
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/jobs/"]'))
                )
            except:
                time.sleep(3)

            # Quick scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)
            
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
        
        # Quick scroll to load lazy content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.3)
        
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
                city, state, country = self.parse_location(location) if location else ('', '', '')
                
                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'job_id': job_id,
                    'company_name': self.company_name,
                    'title': job_info['title'],
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': country,
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

                if job_info['apply_url']:
                    try:
                        full_details = self._fetch_job_details(driver, job_info['apply_url'])
                        if full_details:
                            job_data.update(full_details)
                    except Exception as e:
                        logger.warning(f"Could not fetch full details for job {job_id}: {str(e)}")
                
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
                        'job_id': job_id,
                        'company_name': self.company_name,
                        'title': job_title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': '',
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
                        'job_id': job_id,
                        'company_name': self.company_name,
                        'title': text.split('\n')[0].strip(),
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': '',
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
            
            # Extract full description sections from the detail body.
            try:
                section_blocks = driver.find_elements(By.CSS_SELECTOR, "#job-detail-body .content .section")
                section_texts = []
                for block in section_blocks:
                    heading = ''
                    body = ''
                    try:
                        heading = block.find_element(By.TAG_NAME, 'h2').text.strip()
                    except Exception:
                        pass
                    try:
                        body = block.text.strip()
                        if heading and body.startswith(heading):
                            body = body[len(heading):].strip()
                    except Exception:
                        body = ''
                    if body:
                        if heading:
                            section_texts.append(f"{heading}:\n{body}")
                        else:
                            section_texts.append(body)
                if section_texts:
                    details['description'] = '\n\n'.join(section_texts)[:15000]
            except Exception:
                pass

            # Extract department from Job details section
            try:
                # Look for department link (e.g., "Fulfillment & Operations Management")
                dept_elem = driver.find_element(By.CSS_SELECTOR, 'a[href*="/jobs/category/"]')
                details['department'] = dept_elem.text.strip()
            except:
                try:
                    dept_elem = driver.find_element(By.CSS_SELECTOR, 'a[href*="/job_categories/"]')
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
                location_elem = driver.find_element(By.CSS_SELECTOR, "#job-detail-body .association.location-icon li")
                location_text = location_elem.text.strip()
                if location_text:
                    details['location'] = location_text
                    city, state, country = self.parse_location(location_text)
                    details['city'] = city
                    details['state'] = state
                    details['country'] = country
            except Exception:
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
            return '', '', ''
        
        # Clean up the location string
        location_str = location_str.strip()
        
        # Remove common prefixes
        location_str = location_str.replace('Location:', '').strip()
        
        # Split by comma or pipe
        if '|' in location_str:
            parts = [p.strip() for p in location_str.split('|')[0].split(',') if p.strip()]
        else:
            parts = [p.strip() for p in location_str.split(',') if p.strip()]

        city = ''
        state = ''
        country = ''

        # Amazon job details often use "IND, KA, Bengaluru"
        if len(parts) == 3 and parts[0].upper() == 'IND':
            country = 'India'
            state = parts[1]
            city = parts[2]
        elif len(parts) >= 3:
            city = parts[0]
            state = parts[1]
            country = parts[2]
        elif len(parts) == 2:
            city = parts[0]
            state = parts[1]
        elif len(parts) == 1:
            city = parts[0]

        if not country and ('India' in location_str or 'IND' in location_str):
            country = 'India'

        return city, state, country

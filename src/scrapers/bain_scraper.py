from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import hashlib
import time
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('bain_scraper')

class BainScraper:
    def __init__(self):
        self.company_name = 'Bain'
        # Filter for Mumbai, New Delhi, Bengaluru offices
        self.url = 'https://www.bain.com/careers/find-a-role/?filters=offices(275,276,274)%7C'
    
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
        
        # Install and get the correct chromedriver path
        driver_path = ChromeDriverManager().install()
        
        # Fix for macOS ARM - ensure we have the actual chromedriver executable
        from pathlib import Path
        import os
        import stat
        
        driver_path_obj = Path(driver_path)
        if driver_path_obj.name != 'chromedriver':
            # Navigate to find the actual chromedriver
            parent = driver_path_obj.parent
            actual_driver = parent / 'chromedriver'
            if actual_driver.exists():
                driver_path = str(actual_driver)
            else:
                # Search in subdirectories
                for file in parent.rglob('chromedriver'):
                    if file.is_file() and not file.name.endswith('.zip'):
                        driver_path = str(file)
                        break
        
        # Ensure chromedriver has execute permissions
        try:
            current_permissions = os.stat(driver_path).st_mode
            os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            logger.info(f"Set execute permissions on chromedriver: {driver_path}")
        except Exception as e:
            logger.warning(f"Could not set permissions on chromedriver: {str(e)}")
        
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(SCRAPE_TIMEOUT)
        return driver
    
    def generate_external_id(self, job_id, company):
        """Generate stable external_id using MD5 hash"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Main scraping method with Load More button handling"""
        driver = None
        all_jobs = []
        
        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            
            driver.get(self.url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            
            # Wait for job cards to load
            time.sleep(3)
            
            try:
                # Wait for job listings container
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "card--role-results")))
                logger.info("Job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for job cards: {str(e)}")
            
            # Handle Load More pagination
            load_more_clicks = 0
            max_load_more = max_pages - 1  # First page is already loaded
            
            while load_more_clicks < max_load_more:
                # Scrape current visible jobs
                jobs = self._scrape_page(driver, wait)
                all_jobs.extend(jobs)
                logger.info(f"Scraped {len(jobs)} jobs. Total so far: {len(all_jobs)}")
                
                # Try to click "Load More" button
                if not self._click_load_more(driver, wait):
                    logger.info("No more 'Load More' button found or all jobs loaded")
                    break
                
                load_more_clicks += 1
                logger.info(f"Clicked 'Load More' button {load_more_clicks} time(s)")
                
                # Wait for new jobs to load
                time.sleep(2)
            
            # Scrape final set of jobs after last load more
            if load_more_clicks > 0:
                jobs = self._scrape_page(driver, wait)
                # Filter out duplicates based on external_id
                existing_ids = {job['external_id'] for job in all_jobs}
                new_jobs = [job for job in jobs if job['external_id'] not in existing_ids]
                all_jobs.extend(new_jobs)
                logger.info(f"Scraped {len(new_jobs)} new jobs after final load")
            
            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs
            
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")
    
    def _click_load_more(self, driver, wait):
        """Try to click the Load More button. Returns True if clicked, False otherwise."""
        try:
            # Common Load More button selectors
            selectors = [
                "button.load-more",
                "a.load-more",
                "button[class*='load']",
                "a[class*='load-more']",
                "button:contains('Load More')",
                ".btn--load-more",
                "[data-action='load-more']",
                "button.btn-load-more"
            ]
            
            for selector in selectors:
                try:
                    # Try to find the load more button
                    load_more_btn = driver.find_element(By.CSS_SELECTOR, selector)
                    
                    # Check if button is visible and enabled
                    if load_more_btn.is_displayed() and load_more_btn.is_enabled():
                        # Scroll to button
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_btn)
                        time.sleep(0.5)
                        
                        # Click the button
                        try:
                            load_more_btn.click()
                        except:
                            # Try JavaScript click if regular click fails
                            driver.execute_script("arguments[0].click();", load_more_btn)
                        
                        logger.info(f"Clicked 'Load More' button using selector: {selector}")
                        return True
                except:
                    continue
            
            # If no selector worked, try finding by text content
            try:
                buttons = driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if "load" in btn.text.lower() and "more" in btn.text.lower():
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(0.5)
                            try:
                                btn.click()
                            except:
                                driver.execute_script("arguments[0].click();", btn)
                            logger.info("Clicked 'Load More' button by text content")
                            return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.debug(f"Could not find or click Load More button: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape all jobs from current page (all currently visible job cards)"""
        jobs = []
        scraped_ids = set()  # Track scraped job IDs to avoid duplicates
        
        try:
            # Scroll to load all lazy-loaded content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            # Find all job cards
            job_cards = driver.find_elements(By.CSS_SELECTOR, ".card.card--insights.card--role-results")
            logger.info(f"Found {len(job_cards)} total job cards visible on page")
            
            for idx, card in enumerate(job_cards, 1):
                try:
                    # Hover over the card to trigger any hover effects
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(driver)
                        
                        # Scroll card into view
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                        time.sleep(0.3)
                        
                        # Hover over the card
                        actions.move_to_element(card).perform()
                        time.sleep(0.5)  # Wait for hover effects to trigger
                        
                        logger.debug(f"Hovered over card {idx}")
                    except Exception as e:
                        logger.debug(f"Could not hover over card {idx}: {str(e)}")
                    
                    job_data = self._extract_job_from_card(card, driver, wait, idx)
                    if job_data and job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job {len(jobs)}: {job_data.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"Error finding job cards: {str(e)}")
        
        return jobs
    
    def _extract_job_from_card(self, card, driver, wait, idx):
        """Extract job data from a single card"""
        try:
            # Find the content container
            content = card.find_element(By.CLASS_NAME, "card__content-container")
            
            # Extract job title
            try:
                title_elem = content.find_element(By.CSS_SELECTOR, ".card__heading a")
                title = title_elem.text.strip()
                job_url = title_elem.get_attribute('href')
            except Exception as e:
                logger.warning(f"Could not extract title: {str(e)}")
                return None
            
            # Extract job ID from URL
            job_id = job_url.split('jobid=')[-1] if 'jobid=' in job_url else f"bain_{idx}"
            
            # Extract location and employment type from card
            location = ""
            employment_type = ""
            department = ""
            
            try:
                # Get all text in card body
                card_body = content.find_element(By.CLASS_NAME, "card__body")
                info_items = card_body.find_elements(By.TAG_NAME, "p")
                
                for item in info_items:
                    text = item.text.strip()
                    if text:
                        # Check for employment type indicators
                        if "Full-Time" in text or "Part-Time" in text or "Temporary" in text:
                            employment_type = text
                        # Check for department
                        elif "Consulting" in text or "Management" in text:
                            department = text
                        # Assume location if it contains city names or office count
                        elif "office" in text.lower() or any(city in text for city in ["Mumbai", "Delhi", "Bengaluru", "Amsterdam", "Athens"]):
                            location = text
            except Exception as e:
                logger.debug(f"Could not extract additional info from card: {str(e)}")
            
            # Basic job data from listing
            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': location,
                'employment_type': employment_type,
                'department': department,
                'description': '',
                'posted_date': ''
            }
            
            # Fetch full details if enabled
            if FETCH_FULL_JOB_DETAILS:
                try:
                    logger.info(f"Fetching details for: {title}")
                    details = self._fetch_job_details(driver, job_url)
                    job_data.update(details)
                except Exception as e:
                    logger.warning(f"Could not fetch details for {title}: {str(e)}")
            
            # Parse location
            location_parts = self.parse_location(job_data.get('location', ''))
            job_data.update(location_parts)
            
            return job_data
            
        except Exception as e:
            logger.error(f"Error extracting job from card: {str(e)}")
            return None
    
    def _fetch_job_details(self, driver, job_url):
        """Fetch detailed job information from job details page"""
        details = {
            'description': '',
            'posted_date': '',
            'location': ''
        }
        
        try:
            # Open job details in new tab
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
            driver.get(job_url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            
            time.sleep(2)
            
            # Extract description
            try:
                # Look for the main content section
                desc_elem = wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".description-requirements, .job-description, [class*='description']")
                ))
                details['description'] = desc_elem.text.strip()
            except:
                try:
                    # Alternative: get all text from main content area
                    main_content = driver.find_element(By.CSS_SELECTOR, "main, .main-content, [role='main']")
                    # Get all paragraphs
                    paragraphs = main_content.find_elements(By.TAG_NAME, "p")
                    desc_parts = [p.text.strip() for p in paragraphs if p.text.strip()]
                    details['description'] = '\n'.join(desc_parts)
                except Exception as e:
                    logger.debug(f"Could not extract description: {str(e)}")
            
            # Try to extract additional location info
            try:
                location_elems = driver.find_elements(By.CSS_SELECTOR, "[class*='location'], [class*='office']")
                for elem in location_elems:
                    text = elem.text.strip()
                    if text and len(text) > 0:
                        details['location'] = text
                        break
            except:
                pass
            
            # Close tab and switch back
            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            # Make sure we're back on the original window
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass
        
        return details
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        result = {
            'city': '',
            'state': '',
            'country': ''
        }
        
        if not location_str:
            return result
        
        # Clean up location string
        location_str = location_str.replace('+ 57 offices', '').replace('+ 51 offices', '').strip()
        
        # Try to parse location
        parts = [p.strip() for p in location_str.split('|') if p.strip()]
        
        if parts:
            cities = []
            for part in parts:
                if ',' in part:
                    # Format: "City, Country" or "City, State, Country"
                    sub_parts = [sp.strip() for sp in part.split(',')]
                    cities.append(sub_parts[0])
                    if len(sub_parts) >= 2:
                        result['country'] = sub_parts[-1]
                    if len(sub_parts) == 3:
                        result['state'] = sub_parts[1]
                else:
                    cities.append(part)
            
            result['city'] = ', '.join(cities) if cities else parts[0]
        
        # Default to India if office numbers mentioned (our filter is for India offices)
        if not result['country'] and ('office' in location_str.lower() or any(city in location_str for city in ['Mumbai', 'Delhi', 'Bengaluru'])):
            result['country'] = 'India'
        
        return result

if __name__ == "__main__":
    scraper = BainScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

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

logger = setup_logger('indigo_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class IndiGoScraper:
    def __init__(self):
        self.company_name = 'IndiGo'
        self.url = 'https://careers.goindigo.in/'
    
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
        """Scrape jobs from IndiGo careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(10)  # Wait for SPA to render

            # Scroll to trigger lazy loading - more aggressive for IndiGo
            logger.info("Scrolling to trigger content loading...")
            for i in range(8):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try clicking "Load More" / "Show More" buttons
            for _ in range(5):
                try:
                    load_more_btns = driver.find_elements(By.XPATH, '//button[contains(text(), "Load") or contains(text(), "More") or contains(text(), "Show")]')
                    clicked = False
                    for btn in load_more_btns:
                        if btn.is_displayed() and any(w in btn.text.lower() for w in ['load more', 'show more', 'view more', 'see more']):
                            btn.click()
                            time.sleep(3)
                            clicked = True
                            break
                    if not clicked:
                        break
                except:
                    break

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
                    logger.info(f"Clicked next page button")
                    return True
                except:
                    continue
            
            logger.warning("Could not find next page button")
            return False
                
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
            (By.CSS_SELECTOR, 'div.job-card'),
            (By.CSS_SELECTOR, 'div[class*="job"]'),
            (By.CSS_SELECTOR, 'div[class*="opening"]'),
            (By.CSS_SELECTOR, 'div[class*="position"]'),
            (By.CSS_SELECTOR, 'div[class*="career"]'),
            (By.CSS_SELECTOR, 'div[class*="vacancy"]'),
            (By.CSS_SELECTOR, 'div[class*="role"]'),
            (By.CSS_SELECTOR, 'li[class*="job"]'),
            (By.CSS_SELECTOR, 'li[class*="opening"]'),
            (By.CSS_SELECTOR, 'tr[class*="job"]'),
            (By.CSS_SELECTOR, '[class*="card"]'),
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

        if job_cards:
            for idx, card in enumerate(job_cards):
                try:
                    card_text = card.text
                    if not card_text or len(card_text) < 10:
                        continue

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

                    job_id = f"indigo_{idx}"
                    if job_link:
                        for pattern in ['/job/', '/jobs/', '/position/', '/vacancy/']:
                            if pattern in job_link:
                                job_id = job_link.split(pattern)[-1].split('?')[0].split('/')[0]
                                break

                    location = ""
                    lines = card_text.split('\n')
                    for line in lines:
                        if any(c in line for c in ['Delhi', 'Gurgaon', 'Gurugram', 'Mumbai', 'Bangalore', 'Bengaluru', 'Hyderabad', 'Chennai', 'Kolkata', 'India', 'Remote']):
                            location = line.strip()
                            break

                    city, state, _ = self.parse_location(location)

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
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    if FETCH_FULL_JOB_DETAILS and job_link:
                        full_details = self._fetch_job_details(driver, job_link)
                        job_data.update(full_details)

                    jobs.append(job_data)

                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        # FALLBACK: Link-based extraction - check for job links and table rows
        if not jobs:
            logger.info("Trying link-based fallback for IndiGo...")

            # First try table-based extraction (airline career sites often use tables)
            try:
                tables = driver.find_elements(By.TAG_NAME, 'table')
                for table in tables:
                    rows = table.find_elements(By.CSS_SELECTOR, 'tbody tr, tr')
                    for idx, row in enumerate(rows):
                        try:
                            row_text = row.text.strip()
                            if not row_text or len(row_text) < 15:
                                continue
                            links = row.find_elements(By.TAG_NAME, 'a')
                            if links:
                                title = links[0].text.strip()
                                href = links[0].get_attribute('href') or ''
                                if title and len(title) > 3:
                                    cells = row.find_elements(By.TAG_NAME, 'td')
                                    location = ''
                                    if len(cells) > 1:
                                        for cell in cells[1:]:
                                            ct = cell.text.strip()
                                            if any(c in ct for c in ['Delhi', 'Mumbai', 'Bangalore', 'Gurgaon', 'India']):
                                                location = ct
                                                break

                                    city, state, _ = self.parse_location(location)
                                    jobs.append({
                                        'external_id': self.generate_external_id(f"indigo_table_{idx}", self.company_name),
                                        'company_name': self.company_name,
                                        'title': title,
                                        'description': '',
                                        'location': location,
                                        'city': city,
                                        'state': state,
                                        'country': 'India',
                                        'employment_type': '',
                                        'department': '',
                                        'apply_url': href if href.startswith('http') else self.url,
                                        'posted_date': '',
                                        'job_function': '',
                                        'experience_level': '',
                                        'salary_range': '',
                                        'remote_type': '',
                                        'status': 'active'
                                    })
                        except:
                            continue
                    if jobs:
                        break
            except:
                pass

        if not jobs:
            # Generic link-based fallback
            all_links = driver.find_elements(By.TAG_NAME, 'a')
            seen_titles = set()
            for idx, link in enumerate(all_links):
                try:
                    href = link.get_attribute('href') or ''
                    text = link.text.strip()
                    if not text or len(text) < 5 or len(text) > 200:
                        continue
                    job_url_patterns = ['/job/', '/jobs/', '/position/', '/career', '/opening', '/vacancy', 'lever.co', 'greenhouse.io']
                    if any(p in href.lower() for p in job_url_patterns):
                        if text in seen_titles:
                            continue
                        seen_titles.add(text)
                        exclude_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms']
                        if any(w in text.lower() for w in exclude_words):
                            continue

                        job_id = f"indigo_link_{idx}"
                        location = ''
                        try:
                            parent = link.find_element(By.XPATH, '..')
                            parent_text = parent.text
                            for city_name in ['Delhi', 'Gurgaon', 'Gurugram', 'Mumbai', 'Bangalore', 'Bengaluru', 'Hyderabad', 'Chennai', 'Kolkata', 'India']:
                                if city_name in parent_text:
                                    location = city_name
                                    break
                        except:
                            pass

                        city, state, _ = self.parse_location(location)
                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': text,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': 'India',
                            'employment_type': '',
                            'department': '',
                            'apply_url': href if href.startswith('http') else self.url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })
                except:
                    continue
            if jobs:
                logger.info(f"Link-based fallback found {len(jobs)} jobs")

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

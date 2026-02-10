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

logger = setup_logger('uber_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class UberScraper:
    def __init__(self):
        self.company_name = 'Uber'
        self.url = 'https://www.uber.com/in/en/careers/list/?query=&location=IND-Karnataka-Bangalore'
    
    def setup_driver(self):
        """Set up Chrome driver with options"""
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        
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
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            # Fallback: try without service specification
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Uber careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load - Uber uses a React SPA
            wait = WebDriverWait(driver, 5)
            time.sleep(12)  # Wait for React app to render

            # Scroll to trigger lazy loading
            logger.info("Scrolling to trigger content loading...")
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
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

        # Try multiple selectors for job listings (Uber-specific React selectors)
        job_cards = []
        selectors = [
            (By.CSS_SELECTOR, 'a[href*="/careers/list/"]'),
            (By.CSS_SELECTOR, '[class*="job"]'),
            (By.CSS_SELECTOR, 'div.job-card'),
            (By.CSS_SELECTOR, 'div[class*="job"]'),
            (By.CSS_SELECTOR, 'li[class*="result"]'),
            (By.CSS_SELECTOR, '[class*="search-result"]'),
            (By.CSS_SELECTOR, '[class*="posting"]'),
            (By.CSS_SELECTOR, 'a[href*="/job"]'),
            (By.CSS_SELECTOR, 'a[href*="/career"]'),
            (By.CSS_SELECTOR, 'a[href*="/opening"]'),
            (By.CSS_SELECTOR, 'a[href*="/position"]'),
            (By.CSS_SELECTOR, 'a[href*="/vacancy"]'),
            (By.CSS_SELECTOR, 'div[class*="job-card"]'),
            (By.CSS_SELECTOR, 'div[class*="opening"]'),
            (By.CSS_SELECTOR, 'li[class*="job"]'),
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
                    if not card_text or len(card_text) < 5:
                        continue

                    job_title = ""
                    job_link = ""

                    # If the card itself is a link
                    if card.tag_name == 'a':
                        job_title = card_text.split('\n')[0].strip()
                        job_link = card.get_attribute('href')
                    else:
                        try:
                            title_link = card.find_element(By.TAG_NAME, 'a')
                            job_title = title_link.text.strip()
                            job_link = title_link.get_attribute('href')
                        except:
                            job_title = card_text.split('\n')[0].strip()

                    if not job_title or len(job_title) < 3:
                        continue

                    job_id = f"uber_{idx}"
                    if job_link:
                        for pattern in ['/jobs/', '/job/', '/careers/list/']:
                            if pattern in job_link:
                                job_id = job_link.split(pattern)[-1].split('?')[0].split('/')[0]
                                break

                    location = ""
                    lines = card_text.split('\n')
                    for line in lines:
                        if any(c in line for c in ['India', 'Bangalore', 'Bengaluru', 'Hyderabad', 'Mumbai', 'Delhi', 'Gurgaon', 'Remote']):
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

        # FALLBACK: Link-based extraction
        if not jobs:
            logger.info("Trying link-based fallback for Uber...")
            all_links = driver.find_elements(By.TAG_NAME, 'a')
            seen_titles = set()
            for idx, link in enumerate(all_links):
                try:
                    href = link.get_attribute('href') or ''
                    text = link.text.strip()
                    if not text or len(text) < 5 or len(text) > 200:
                        continue
                    job_url_patterns = ['/careers/list/', '/job/', '/jobs/', '/position/']
                    if any(p in href.lower() for p in job_url_patterns):
                        if text in seen_titles:
                            continue
                        seen_titles.add(text)
                        exclude_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'search', 'filter', 'clear']
                        if any(w in text.lower() for w in exclude_words):
                            continue

                        job_id = f"uber_link_{idx}"
                        if '/careers/list/' in href:
                            job_id = href.split('/careers/list/')[-1].split('?')[0].split('/')[0]

                        location = ''
                        try:
                            parent = link.find_element(By.XPATH, '..')
                            parent_text = parent.text
                            for city_name in ['Bangalore', 'Bengaluru', 'Hyderabad', 'Mumbai', 'Delhi', 'India']:
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


        # JS-based link extraction fallback
        if not jobs:
            logger.info("Trying JS-based link extraction fallback")
            try:
                js_links = driver.execute_script("""
                    var results = [];
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            var lhref = href.toLowerCase();
                            if (lhref.includes('/job') || lhref.includes('/position') || lhref.includes('/career') ||
                                lhref.includes('/opening') || lhref.includes('/detail') || lhref.includes('/vacancy') ||
                                lhref.includes('/role') || lhref.includes('/requisition') || lhref.includes('/apply')) {
                                results.push({title: text.split('\n')[0].trim(), url: href});
                            }
                        }
                    });
                    return results;
                """)
                if js_links:
                    seen = set()
                    exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq']
                    for link_data in js_links:
                        title = link_data.get('title', '')
                        url = link_data.get('url', '')
                        if not title or not url or len(title) < 3 or title in seen:
                            continue
                        if any(w in title.lower() for w in exclude):
                            continue
                        seen.add(title)
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '', 'location': '', 'city': '', 'state': '',
                            'country': 'India', 'employment_type': '', 'department': '',
                            'apply_url': url, 'posted_date': '', 'job_function': '',
                            'experience_level': '', 'salary_range': '', 'remote_type': '', 'status': 'active'
                        })
                    if jobs:
                        logger.info(f"JS fallback found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"JS fallback error: {str(e)}")

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

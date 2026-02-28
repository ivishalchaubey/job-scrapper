# STATUS: PLATFORM_DOWN - Skillate platform (axisbank.skillate.com) timing out (tested 2026-02-22)
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

logger = setup_logger('axisbank_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class AxisBankScraper:
    def __init__(self):
        self.company_name = 'Axis Bank'
        # Point to actual job listings, not the careers landing page
        self.url = 'https://axisbank.skillate.com/'
    
    def setup_driver(self):
        """Set up Chrome driver with options"""
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=AppleWebKit/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        
        driver = None
        try:
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info(f"ChromeDriver started with: {CHROMEDRIVER_PATH}")
        except Exception as e:
            logger.warning(f"ChromeDriver with service failed: {e}")
            try:
                driver = webdriver.Chrome(options=chrome_options)
                logger.info("Using default ChromeDriver")
            except Exception as e2:
                logger.error(f"All ChromeDriver attempts failed: {e2}")
                raise

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Axis Bank careers page with pagination support"""
        jobs = []
        driver = None
        
        max_retries = 3
        for attempt in range(max_retries):
          try:
            logger.info(f"Starting scrape for {self.company_name} (attempt {attempt + 1}/{max_retries})")
            driver = self.setup_driver()

            try:
                driver.get(self.url)
            except Exception as nav_err:
                logger.warning(f"Navigation error: {nav_err}")
                if driver:
                    driver.quit()
                    driver = None
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                raise

            short_wait = WebDriverWait(driver, 5)
            time.sleep(15)  # Wait for Skillate SPA to load

            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "div.job-card, div[class*='job-listing'], a[href*='/jobs/'], div[class*='job']"
                )))
                logger.info("Job listings loaded")
            except:
                logger.warning("Timeout waiting for job listings, continuing with fallbacks")

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_page(driver, short_wait)
                jobs.extend(page_jobs)
                
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")
                
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(3)
                
                current_page += 1
            
            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
            break  # Success

          except Exception as e:
            logger.error(f"Error scraping {self.company_name} (attempt {attempt + 1}): {str(e)}")
            if driver:
                driver.quit()
                driver = None
            if attempt < max_retries - 1:
                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                raise

          finally:
            if driver:
                driver.quit()
                driver = None

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
            
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(3)

        # Scroll to load dynamic content
        for scroll_i in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        job_cards = []
        # Skillate platform priority selectors
        selectors = [
            (By.CSS_SELECTOR, 'div.job-card'),
            (By.CSS_SELECTOR, 'div[class*="job-listing"]'),
            (By.CSS_SELECTOR, 'a[href*="/jobs/"]'),
            (By.CSS_SELECTOR, 'div.job-title'),
            (By.CSS_SELECTOR, 'div.job-details'),
            (By.CSS_SELECTOR, '[class*="job-card"]'),
            (By.CSS_SELECTOR, '[class*="jobCard"]'),
            (By.CSS_SELECTOR, '[class*="job-listing"]'),
            (By.CSS_SELECTOR, 'div[class*="job"]'),
            (By.CSS_SELECTOR, 'div[class*="opening"]'),
            (By.CSS_SELECTOR, 'div[class*="position"]'),
            (By.CSS_SELECTOR, 'div[class*="vacancy"]'),
            (By.CSS_SELECTOR, 'div[class*="result"]'),
            (By.XPATH, '//div[contains(@class, "listing")]'),
            (By.TAG_NAME, 'article'),
        ]

        for selector_type, selector_value in selectors:
            try:
                elements = driver.find_elements(selector_type, selector_value)
                if elements and len(elements) >= 1:
                    job_cards = elements
                    logger.info(f"Found {len(job_cards)} job cards using: {selector_value}")
                    break
            except:
                continue

        # Link-based fallback: find <a> tags with job/career-related hrefs
        if not job_cards:
            logger.info("Primary selectors failed, trying link-based fallback")
            try:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                job_links = []
                seen_hrefs = set()
                for link in all_links:
                    href = (link.get_attribute('href') or '').lower()
                    text = (link.text or '').strip()
                    if not href or not text or len(text) < 5:
                        continue
                    if href in seen_hrefs:
                        continue
                    if any(kw in href for kw in ['/job', '/career', '/opening', '/position', '/vacancy', 'requisition', 'apply']):
                        if not any(skip in href for skip in ['login', 'sign-in', 'faq', '#', 'javascript:']):
                            job_links.append(link)
                            seen_hrefs.add(href)
                if job_links:
                    job_cards = job_links
                    logger.info(f"Link-based fallback found {len(job_cards)} job links")
            except Exception as e:
                logger.error(f"Link-based fallback failed: {str(e)}")

        # JavaScript fallback for link extraction
        if not job_cards:
            logger.info("Trying JavaScript fallback for link extraction")
            try:
                js_links = driver.execute_script("""
                    var results = [];
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            if (href.includes('/job') || href.includes('/position') || href.includes('/career') || href.includes('/opening') || href.includes('/requisition')) {
                                results.push({title: text.split('\\n')[0].trim(), url: href});
                            }
                        }
                    });
                    return results;
                """)
                if js_links:
                    logger.info(f"JS fallback found {len(js_links)} job links")
                    for jl in js_links:
                        title = jl.get('title', '').strip()
                        url = jl.get('url', '').strip()
                        if title and url:
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                            job_data = {
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name,
                                'title': title,
                                'description': '',
                                'location': '',
                                'city': '',
                                'state': '',
                                'country': 'India',
                                'employment_type': '',
                                'department': '',
                                'apply_url': url,
                                'posted_date': '',
                                'job_function': '',
                                'experience_level': '',
                                'salary_range': '',
                                'remote_type': '',
                                'status': 'active'
                            }
                            jobs.append(job_data)
                            logger.info(f"JS Extracted: {title}")
                    return jobs
            except Exception as e:
                logger.error(f"JS fallback failed: {str(e)}")

        if not job_cards:
            logger.warning("No job cards found with any selector or fallback")
            return jobs
        
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
                
                job_id = f"axisbank_{idx}"
                if job_link:
                    job_id = hashlib.md5(job_link.encode()).hexdigest()[:12]
                
                location = ""
                city = ""
                state = ""
                lines = card_text.split('\n')
                for line in lines:
                    if 'India' in line or any(city_name in line for city_name in ['Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Hyderabad', 'Pune', 'Kolkata']):
                        location = line.strip()
                        city, state, _ = self.parse_location(location)
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
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, "//div[contains(@class, 'job-description')]"),
                    (By.CSS_SELECTOR, 'div.description'),
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
        
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        
        return city, state, 'India'

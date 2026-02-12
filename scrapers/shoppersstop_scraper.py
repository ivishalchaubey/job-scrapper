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

logger = setup_logger('shoppersstop_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class ShoppersStopScraper:
    def __init__(self):
        self.company_name = 'Shoppers Stop'
        self.url = 'https://www.shoppersstop.com/careers'
    
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
        """Scrape jobs from Shoppers Stop careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)

            # Wait for page to load
            time.sleep(12)

            # Scroll to trigger lazy-loaded content
            for scroll_i in range(4):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((scroll_i + 1) / 4))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                # Scrape current page
                page_jobs = self._scrape_page(driver)
                jobs.extend(page_jobs)
                
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")
                
                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(4)  # Wait for next page to load
                
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
            
            # Scroll to pagination area
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            # Try to find and click next page button
            next_page_selectors = [
                (By.XPATH, '//button[contains(@class, "next")]'),
                (By.XPATH, '//a[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'button.pagination-next'),
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    if next_button.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", next_button)
                        logger.info(f"Clicked next page button")
                        return True
                except:
                    continue
            
            logger.warning("Could not find next page button")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(3)  # Wait for page content to load
        
        # Look for job cards
        job_cards = []
        
        try:
            selectors = [
                (By.CSS_SELECTOR, 'div.job-card'),
                (By.CSS_SELECTOR, 'div.career-listing'),
                (By.CSS_SELECTOR, 'div[class*="job"]'),
                (By.XPATH, '//div[contains(@class, "career")]'),
                (By.CSS_SELECTOR, 'a[href*="/job/"]'),
                (By.CSS_SELECTOR, 'a[href*="/jobs/"]'),
                (By.CSS_SELECTOR, 'a[href*="/careers/"]'),
                (By.CSS_SELECTOR, 'div[class*="opening"]'),
                (By.CSS_SELECTOR, 'div[class*="position"]'),
                (By.CSS_SELECTOR, 'li[class*="job"]'),
                (By.CSS_SELECTOR, 'div[class*="vacancy"]'),
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
                    job_cards = driver.find_elements(selector_type, selector_value)
                    if job_cards and len(job_cards) > 0:
                        logger.info(f"Found {len(job_cards)} job cards using selector: {selector_value}")
                        break
                except:
                    continue
                    
        except Exception as e:
            logger.error(f"Error finding job cards: {str(e)}")
        
        if not job_cards:
            # Fallback: look for all links that might be job listings
            logger.warning("Standard selectors failed, trying link-based fallback")
            try:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                job_keywords = ['/job/', '/jobs/', '/career', '/position/', '/opening/', '/vacancy/', '/apply/']
                seen_urls = set()
                for link in all_links:
                    try:
                        href = link.get_attribute('href') or ''
                        link_text = link.text.strip()
                        if not link_text or len(link_text) < 3:
                            continue
                        if not any(kw in href.lower() for kw in job_keywords):
                            continue
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)

                        job_id = href.split('/')[-1].split('?')[0] if href else f"shoppersstop_link_{len(jobs)}"

                        job_data = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': link_text,
                            'description': '',
                            'location': '',
                            'city': '',
                            'state': '',
                            'country': 'India',
                            'employment_type': '',
                            'department': '',
                            'apply_url': href if href else self.url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        jobs.append(job_data)
                        logger.info(f"Found job via link fallback: '{link_text}'")
                    except:
                        continue
            except Exception as e:
                logger.error(f"Link-based fallback failed: {str(e)}")

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
        
        # Process each job card
        for idx, card in enumerate(job_cards):
            try:
                card_text = card.text
                if not card_text or len(card_text) < 10:
                    continue
                
                # Extract job title
                job_title = ""
                job_link = ""
                try:
                    title_selectors = [
                        (By.CSS_SELECTOR, 'h3'),
                        (By.CSS_SELECTOR, 'h2'),
                        (By.TAG_NAME, 'a'),
                    ]
                    
                    for selector_type, selector_value in title_selectors:
                        try:
                            title_elem = card.find_element(selector_type, selector_value)
                            job_title = title_elem.text.strip()
                            if selector_type == By.TAG_NAME:
                                job_link = title_elem.get_attribute('href')
                            if job_title:
                                break
                        except:
                            continue
                    
                    # Try to get link separately if not found
                    if not job_link:
                        try:
                            link_elem = card.find_element(By.TAG_NAME, 'a')
                            job_link = link_elem.get_attribute('href')
                        except:
                            pass
                except:
                    logger.debug(f"Could not extract title for card {idx}")
                    continue
                
                if not job_title or len(job_title) < 3:
                    logger.debug(f"Skipping card {idx}: Title too short")
                    continue
                
                # Extract job ID from URL or generate one
                job_id = f"shoppersstop_{idx}"
                if job_link:
                    try:
                        if '/job/' in job_link:
                            job_id = job_link.split('/job/')[-1].split('/')[0].split('?')[0]
                    except:
                        pass
                
                # Extract location
                location = ""
                city = ""
                state = ""
                try:
                    loc_selectors = [
                        (By.CSS_SELECTOR, 'span.location'),
                        (By.CSS_SELECTOR, 'div.location'),
                        (By.XPATH, './/*[contains(text(), "India")]'),
                    ]
                    
                    for selector_type, selector_value in loc_selectors:
                        try:
                            loc_elem = card.find_element(selector_type, selector_value)
                            location = loc_elem.text.strip()
                            if location:
                                city, state, _ = self.parse_location(location)
                                break
                        except:
                            continue
                except:
                    pass
                
                # Generate external ID
                external_id = self.generate_external_id(job_id, self.company_name)
                
                logger.info(f"Found job: '{job_title}' (ID: {job_id})")
                
                job_data = {
                    'external_id': external_id,
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
                
                # Fetch full details if enabled
                if FETCH_FULL_JOB_DETAILS and job_link and job_link != self.url:
                    full_details = self._fetch_job_details(driver, job_link)
                    job_data.update(full_details)
                
                jobs.append(job_data)
                logger.info(f"Successfully added job: {job_title}")
                
            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                continue
        
        return jobs
    
    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}
        
        try:
            # Open job in new tab
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
            driver.get(job_url)
            time.sleep(4)
            
            # Extract job description
            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div.job-description'),
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, '//h2[contains(text(), "Description")]/following-sibling::div'),
                    (By.CSS_SELECTOR, 'div.content'),
                ]
                
                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        if desc_elem and desc_elem.text.strip():
                            details['description'] = desc_elem.text.strip()[:2000]
                            logger.debug(f"Extracted description using selector: {selector_value}")
                            break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"Error extracting description: {str(e)}")
            
            # Close tab and return to search results
            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(1)
            
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

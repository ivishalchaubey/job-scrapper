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

logger = setup_logger('metlife_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class MetLifeScraper:
    def __init__(self):
        self.company_name = 'MetLife'
        self.url = 'https://jobs.metlife.com/search/?q=&locationsearch=India'
    
    def setup_driver(self):
        """Set up Chrome driver with anti-detection options"""
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
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Auto-detect failed: {str(e)}, trying explicit path")
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)

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
        """Scrape jobs from MetLife careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)

            # Wait for page to load
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(15)

            # Dismiss cookie consent banner if present
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button, a');
                    for (var i = 0; i < btns.length; i++) {
                        var t = btns[i].innerText.trim();
                        if (t === 'Accept' || t === 'Accept all' || t === 'Accept All') {
                            btns[i].click();
                            break;
                        }
                    }
                """)
                time.sleep(3)
                logger.info("Dismissed cookie consent banner")
            except:
                pass

            # Scroll to trigger lazy-loaded content
            for scroll_i in range(5):
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
                    time.sleep(3)
                
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
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            for selector_type, selector_value in [
                (By.CSS_SELECTOR, 'a.paginationNextLink'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-show-next'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
            ]:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    if next_button.is_displayed() and next_button.is_enabled():
                        driver.execute_script("arguments[0].click();", next_button)
                        logger.info("Clicked next page button")
                        return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page - SuccessFactors platform"""
        jobs = []
        time.sleep(3)

        # Use JavaScript extraction with SuccessFactors-specific selectors
        js_jobs = driver.execute_script("""
            var results = [];
            var seen = {};

            // Strategy 1: SuccessFactors article cards (modern variant)
            var articles = document.querySelectorAll('article.article--result');
            for (var i = 0; i < articles.length; i++) {
                var art = articles[i];
                var titleLink = art.querySelector('h3 a, a.article__header__focusable, a.link');
                if (!titleLink) continue;
                var title = titleLink.innerText.trim();
                if (title === 'Learn More >' || title === 'Learn more' || title === 'Apply') continue;
                var url = titleLink.href || '';
                if (!title || title.length < 3 || seen[url]) continue;
                seen[url] = true;
                var subtitle = art.querySelector('.article__header__text__subtitle');
                var location = '';
                if (subtitle) {
                    var parts = subtitle.innerText.trim().split('\\u2022');
                    if (parts.length > 0) location = parts[0].trim();
                }
                results.push({title: title, url: url, location: location, date: ''});
            }

            // Strategy 2: SuccessFactors table rows (classic)
            if (results.length === 0) {
                var rows = document.querySelectorAll('tr.data-row');
                for (var i = 0; i < rows.length; i++) {
                    var row = rows[i];
                    var titleLink = row.querySelector('a.jobTitle-link, a[href*="/job/"]');
                    if (!titleLink) continue;
                    var title = titleLink.innerText.trim();
                    var url = titleLink.href || '';
                    if (!title || title.length < 3 || seen[url]) continue;
                    seen[url] = true;
                    var locTd = row.querySelector('td.colLocation, [class*="location"], [class*="Location"]');
                    var location = locTd ? locTd.innerText.trim() : '';
                    results.push({title: title, url: url, location: location, date: ''});
                }
            }

            // Strategy 3: h3 links inside articles (fallback for any SuccessFactors variant)
            if (results.length === 0) {
                var h3Links = document.querySelectorAll('article h3 a');
                for (var i = 0; i < h3Links.length; i++) {
                    var el = h3Links[i];
                    var title = el.innerText.trim();
                    var url = el.href || '';
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (title === 'Learn More >' || title === 'Learn more' || title === 'Apply') continue;
                    if (url.includes('login') || url.includes('javascript:')) continue;
                    if (seen[url]) continue;
                    seen[url] = true;
                    results.push({title: title, url: url, location: '', date: ''});
                }
            }

            return results;
        """)

        if not js_jobs:
            logger.warning("No jobs found on this page")
            try:
                body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                logger.info(f"Page body preview: {body_text}")
            except:
                pass
            return jobs

        logger.info(f"JS extraction found {len(js_jobs)} jobs")
        for jdata in js_jobs:
            try:
                title = jdata.get('title', '').strip()
                job_link = jdata.get('url', '').strip()
                location = jdata.get('location', '').strip()
                date = jdata.get('date', '').strip()

                if not title or len(title) < 3:
                    continue

                job_id = f"metlife_{len(jobs)}"
                if job_link:
                    job_id = hashlib.md5(job_link.encode()).hexdigest()[:12]

                city, state, country = self.parse_location(location)

                job_data = {
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
                    'apply_url': job_link if job_link else self.url,
                    'posted_date': date,
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
                logger.error(f"Error extracting job: {str(e)}")
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
            time.sleep(3)
            
            # Extract description
            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div.job-description'),
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, '//div[contains(@class, "description")]'),
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
            
            # Extract department
            try:
                dept_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'Department')]//following-sibling::*")
                details['department'] = dept_elem.text.strip()
            except:
                pass
            
            # Close tab and return to search results
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

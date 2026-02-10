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

logger = setup_logger('marutisuzuki_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class MarutiSuzukiScraper:
    def __init__(self):
        self.company_name = 'Maruti Suzuki'
        self.url = 'https://www.marutisuzuki.com/corporate/career/current-openings'
    
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
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            # Fallback: try without service specification
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Maruti Suzuki careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load - corporate SPA needs generous wait
            wait = WebDriverWait(driver, 5)
            time.sleep(15)

            # Scroll to trigger lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Check for iframes
            try:
                iframes = driver.find_elements(By.TAG_NAME, 'iframe')
                for iframe in iframes:
                    src = iframe.get_attribute('src') or ''
                    if 'job' in src.lower() or 'career' in src.lower() or 'opening' in src.lower():
                        logger.info(f"Switching to iframe: {src}")
                        driver.switch_to.frame(iframe)
                        time.sleep(5)
                        break
            except Exception as e:
                logger.warning(f"Iframe check failed: {str(e)}")
            
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
            next_page_num = current_page + 1
            
            # Scroll to pagination area
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            # Try to find and click next page button
            next_page_selectors = [
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.5)
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
        """Scrape jobs from current page using JS-first extraction"""
        jobs = []
        time.sleep(3)

        # Scroll to load dynamic content
        for scroll_i in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        # Try to click on any "View All" or "Show More" buttons first
        try:
            driver.execute_script("""
                var buttons = document.querySelectorAll('button, a, span[role="button"]');
                for (var i = 0; i < buttons.length; i++) {
                    var text = (buttons[i].innerText || '').trim().toLowerCase();
                    if (text.includes('view all') || text.includes('show all') || text.includes('show more') ||
                        text.includes('load more') || text.includes('see all')) {
                        buttons[i].click();
                    }
                }
            """)
            time.sleep(3)
        except:
            pass

        # Try expanding accordions/collapsibles
        try:
            driver.execute_script("""
                var expandables = document.querySelectorAll('[data-toggle="collapse"], .accordion-header, .panel-heading, [aria-expanded="false"], button[class*="expand"], button[class*="toggle"]');
                for (var i = 0; i < expandables.length; i++) {
                    try { expandables[i].click(); } catch(e) {}
                }
            """)
            time.sleep(2)
        except:
            pass

        # Maruti Suzuki corporate career page - JS-first comprehensive extraction
        logger.info("Using JS-based comprehensive extraction for Maruti Suzuki")
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy A: Look for job/opening cards/tiles
                var cardSelectors = [
                    'div[class*="job-card"]', 'div[class*="job-listing"]',
                    'div[class*="career-card"]', 'div[class*="opening"]',
                    'div[class*="vacancy"]', 'div[class*="position"]',
                    'li[class*="job"]', 'li[class*="career"]', 'li[class*="opening"]',
                    'article', 'div.card', 'div[class*="accordion"]',
                    'div[class*="panel"]', 'div[class*="collapse"]',
                    'tr[class*="job"]', 'tr[class*="data"]',
                    'div[class*="listing"]', 'div[class*="result"]'
                ];

                for (var s = 0; s < cardSelectors.length; s++) {
                    var cards = document.querySelectorAll(cardSelectors[s]);
                    if (cards.length >= 2) {
                        cards.forEach(function(card) {
                            var text = (card.innerText || '').trim();
                            if (text.length < 5 || text.length > 1000) return;
                            var title = text.split('\n')[0].trim();
                            if (title.length < 3 || title.length > 200) return;
                            var link = card.querySelector('a[href]');
                            var url = link ? link.href : '';
                            if (link && link.innerText && link.innerText.trim().length > 3) {
                                title = link.innerText.trim().split('\n')[0];
                            }
                            var key = title + '|' + url;
                            if (seen[key]) return;
                            seen[key] = true;

                            var location = '';
                            var lines = text.split('\n');
                            for (var i = 1; i < lines.length; i++) {
                                var line = lines[i].trim();
                                if (line.match(/Gurgaon|Gurugram|Delhi|Manesar|Mumbai|India|Pune|Chennai|Bangalore/i)) {
                                    location = line;
                                    break;
                                }
                            }
                            results.push({title: title, url: url, location: location, fullText: text});
                        });
                        if (results.length > 0) break;
                    }
                }

                // Strategy B: Find links with job-related patterns
                if (results.length === 0) {
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length < 3 || text.length > 200 || href.length < 10) return;
                        var lhref = href.toLowerCase();
                        var ltext = text.toLowerCase();
                        // Skip navigation links
                        if (['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms',
                             'cookie', 'blog', 'faq', 'menu', 'close', 'search', 'filter',
                             'back', 'submit', 'read more', 'learn more', 'know more',
                             'maruti suzuki', 'corporate', 'investor'].some(function(w) { return ltext === w; })) return;

                        if (lhref.includes('/job/') || lhref.includes('/jobs/') ||
                            lhref.includes('/career') || lhref.includes('/opening') ||
                            lhref.includes('/position') || lhref.includes('/vacancy') ||
                            lhref.includes('/requisition') || lhref.includes('/apply') ||
                            lhref.includes('workday') || lhref.includes('successfactors') ||
                            lhref.includes('smartrecruiters') || lhref.includes('greenhouse')) {
                            var key = text + '|' + href;
                            if (seen[key]) return;
                            seen[key] = true;
                            results.push({title: text.split('\n')[0].trim(), url: href, location: '', fullText: text});
                        }
                    });
                }

                // Strategy C: Repeated sibling elements (job cards pattern)
                if (results.length === 0) {
                    var containers = document.querySelectorAll('div, ul, section, main');
                    for (var c = 0; c < containers.length; c++) {
                        var children = containers[c].children;
                        if (children.length >= 3 && children.length <= 200) {
                            var hasLinks = 0;
                            var sameTag = true;
                            var firstTag = children[0] ? children[0].tagName : '';
                            for (var j = 0; j < Math.min(children.length, 5); j++) {
                                if (children[j].tagName !== firstTag) sameTag = false;
                                if (children[j].querySelector('a[href]')) hasLinks++;
                            }
                            if (sameTag && hasLinks >= 2 && children.length >= 3) {
                                for (var k = 0; k < children.length; k++) {
                                    var child = children[k];
                                    var cText = (child.innerText || '').trim();
                                    if (cText.length < 10 || cText.length > 500) continue;
                                    var cTitle = cText.split('\n')[0].trim();
                                    if (cTitle.length < 3) continue;
                                    var cLink = child.querySelector('a[href]');
                                    var cUrl = cLink ? cLink.href : '';
                                    if (cLink && cLink.innerText) cTitle = cLink.innerText.trim().split('\n')[0];
                                    var cKey = cTitle + '|' + cUrl;
                                    if (seen[cKey]) continue;
                                    seen[cKey] = true;
                                    results.push({title: cTitle, url: cUrl, location: '', fullText: cText});
                                }
                                if (results.length >= 3) break;
                            }
                        }
                    }
                }

                // Strategy D: Tables with job data
                if (results.length === 0) {
                    var tables = document.querySelectorAll('table');
                    for (var t = 0; t < tables.length; t++) {
                        var rows = tables[t].querySelectorAll('tr');
                        if (rows.length >= 2) {
                            for (var r = 1; r < rows.length; r++) {
                                var rowText = (rows[r].innerText || '').trim();
                                if (rowText.length < 10 || rowText.length > 500) continue;
                                var rowTitle = rowText.split('\n')[0].trim();
                                if (rowTitle.length < 3) continue;
                                var rowLink = rows[r].querySelector('a[href]');
                                var rowUrl = rowLink ? rowLink.href : '';
                                if (rowLink && rowLink.innerText) rowTitle = rowLink.innerText.trim().split('\n')[0];
                                var rKey = rowTitle + '|' + rowUrl;
                                if (seen[rKey]) continue;
                                seen[rKey] = true;
                                var rowLoc = '';
                                var rowLines = rowText.split('\n');
                                for (var rl = 1; rl < rowLines.length; rl++) {
                                    if (rowLines[rl].match(/Gurgaon|Gurugram|Delhi|Manesar|Mumbai|India/i)) {
                                        rowLoc = rowLines[rl].trim();
                                        break;
                                    }
                                }
                                results.push({title: rowTitle, url: rowUrl, location: rowLoc, fullText: rowText});
                            }
                            if (results.length > 0) break;
                        }
                    }
                }

                // Strategy E: Find headings that look like job titles
                if (results.length === 0) {
                    var headings = document.querySelectorAll('h2, h3, h4, h5, strong, b');
                    headings.forEach(function(h) {
                        var ht = (h.innerText || '').trim();
                        if (ht.length >= 5 && ht.length <= 150) {
                            if (ht.match(/manager|engineer|analyst|executive|officer|specialist|lead|head|director|associate|trainee|consultant|developer|designer/i)) {
                                var parentLink = h.closest('a');
                                var hUrl = parentLink ? parentLink.href : '';
                                if (!hUrl) {
                                    var nearbyLink = h.parentElement ? h.parentElement.querySelector('a[href]') : null;
                                    if (nearbyLink) hUrl = nearbyLink.href;
                                }
                                var hKey = ht + '|' + hUrl;
                                if (!seen[hKey]) {
                                    seen[hKey] = true;
                                    results.push({title: ht, url: hUrl || '', location: '', fullText: ht});
                                }
                            }
                        }
                    });
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} potential jobs")
                seen_titles = set()
                for item in js_jobs:
                    title = item.get('title', '').strip()
                    url = item.get('url', '').strip()
                    full_text = item.get('fullText', '')

                    if not title or len(title) < 3 or title.lower() in seen_titles:
                        continue
                    # Skip non-job items
                    skip_words = ['home', 'about', 'contact', 'login', 'sign in', 'register',
                                  'privacy', 'cookie', 'terms', 'maruti suzuki', 'corporate']
                    if any(w == title.lower() for w in skip_words):
                        continue
                    seen_titles.add(title.lower())

                    job_id = f"maruti_{len(jobs)}"
                    if url:
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    location = item.get('location', '')
                    city = ''
                    state = ''
                    if location:
                        city, state, _ = self.parse_location(location)

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
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    if FETCH_FULL_JOB_DETAILS and url:
                        full_details = self._fetch_job_details(driver, url)
                        job_data.update(full_details)

                    jobs.append(job_data)

                if jobs:
                    logger.info(f"JS extraction yielded {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"JS extraction error: {str(e)}")

        # Selenium selector fallback
        if not jobs:
            logger.info("Using Selenium selector fallback")
            job_cards = []
            selectors = [
                (By.CSS_SELECTOR, 'div[class*="job-card"]'),
                (By.CSS_SELECTOR, 'div[class*="opening"]'),
                (By.CSS_SELECTOR, 'div[class*="career"]'),
                (By.CSS_SELECTOR, 'li[class*="job"]'),
                (By.CSS_SELECTOR, 'a[href*="/job"]'),
                (By.CSS_SELECTOR, 'a[href*="/career"]'),
                (By.TAG_NAME, 'article'),
            ]
            for selector_type, selector_value in selectors:
                try:
                    elements = driver.find_elements(selector_type, selector_value)
                    if elements and len(elements) >= 2:
                        job_cards = elements
                        logger.info(f"Found {len(job_cards)} elements using: {selector_value}")
                        break
                except:
                    continue

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
                    job_id = f"maruti_{idx}"
                    if job_link:
                        job_id = hashlib.md5(job_link.encode()).hexdigest()[:12]
                    location = ""
                    city = ""
                    state = ""
                    lines = card_text.split('\n')
                    for line in lines:
                        if any(c in line for c in ['Gurgaon', 'Gurugram', 'Delhi', 'Manesar', 'Mumbai', 'India']):
                            location = line.strip()
                            city, state, _ = self.parse_location(location)
                            break
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': job_title,
                        'description': '', 'location': location, 'city': city, 'state': state,
                        'country': 'India', 'employment_type': '', 'department': '',
                        'apply_url': job_link if job_link else self.url,
                        'posted_date': '', 'job_function': '', 'experience_level': '',
                        'salary_range': '', 'remote_type': '', 'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")

        if not jobs:
            logger.warning("No jobs found on this page")
            try:
                body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                logger.info(f"Page body preview: {body_text}")
            except:
                pass

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

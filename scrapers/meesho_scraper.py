from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('meesho_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class MeeshoScraper:
    def __init__(self):
        self.company_name = 'Meesho'
        self.url = 'https://careers.meesho.com/'

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
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

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
        """Scrape jobs from Meesho careers page.

        NOTE: As of Feb 2026, the careers.meesho.com page returns an Akamai/CDN
        error page (Reference #30.xxx). The Meesho careers portal appears to be
        behind a CDN that is blocking or misconfigured. This scraper attempts
        multiple strategies and returns an empty list if no careers page is found.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Strategy 1: Try the main careers URL
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(15)

            # Check if we got an error page (check multiple times as CDN errors can be slow)
            is_error = self._check_if_error_page(driver)
            if not is_error:
                # Wait a bit more and check again - Akamai errors can take time to render
                time.sleep(5)
                is_error = self._check_if_error_page(driver)

            if is_error:
                logger.warning(f"Careers page at {self.url} returns error - page may be blocked or down")

                # Strategy 2: Try Lever jobs page (Meesho uses Lever for job listings)
                logger.info("Trying Lever jobs page for Meesho")
                driver.get('https://jobs.lever.co/meesho')
                time.sleep(12)

                if self._check_if_error_page(driver):
                    # Strategy 3: Try meesho.io/jobs
                    logger.info("Trying meesho.io/jobs")
                    driver.get('https://www.meesho.io/jobs')
                    time.sleep(12)

                    if self._check_if_error_page(driver):
                        logger.error(
                            "Meesho careers page is returning CDN/Akamai error. "
                            "Lever and meesho.io alternatives also failed. "
                            "The careers.meesho.com domain may be temporarily or permanently down."
                        )
                        return jobs

            # If we reach here, we have a working page - try to extract jobs
            # Scroll to trigger lazy loading
            for i in range(4):
                driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {(i + 1) / 4});")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_page(driver)
                jobs.extend(page_jobs)

                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(4)

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _check_if_error_page(self, driver):
        """Check if the current page shows a 404 or CDN error page"""
        try:
            body_text = driver.execute_script("return document.body.innerText.substring(0, 500)")
            title = driver.title.lower()

            # Check title-based error
            if title == 'error' or '404' in title:
                return True

            # CDN/Akamai error pattern (Reference #xx.xxx)
            if 'reference #' in body_text.lower() and 'error' in body_text.lower():
                return True

            # Akamai specific error
            if 'edgesuite.net' in body_text.lower():
                return True

            # Check content-based 404
            if '404' in body_text and ('not found' in body_text.lower() or 'error' in body_text.lower()):
                return True

            # Generic error page indicators
            if 'page not found' in body_text.lower():
                return True

            # Very short body with error keywords
            if len(body_text.strip()) < 200 and ('error' in body_text.lower() or 'an error occurred' in body_text.lower()):
                return True

        except:
            pass
        return False

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page"""
        try:
            next_page_num = current_page + 1

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

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
                    logger.info("Clicked next page button")
                    return True
                except:
                    continue

            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver):
        """Scrape jobs from current page using JavaScript-first extraction"""
        jobs = []
        time.sleep(2)

        # JavaScript-first extraction
        try:
            js_jobs = driver.execute_script("""
                var results = [];

                // Strategy 1: Lever-style extraction (Meesho uses Lever)
                var postings = document.querySelectorAll('.posting');
                if (postings.length > 0) {
                    // Build department map from section headers
                    // Lever groups postings under department headers
                    var currentDept = '';
                    var allElements = document.querySelectorAll('.posting, .posting-category-title');
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        if (el.classList.contains('posting-category-title')) {
                            currentDept = (el.innerText || '').trim();
                            continue;
                        }
                        // This is a posting
                        var titleEl = el.querySelector('.posting-title h5, h5');
                        var title = titleEl ? titleEl.innerText.trim() : '';
                        var link = el.querySelector('a.posting-title, a[href*="lever.co"]');
                        var url = link ? link.href : '';
                        if (!title && link) title = (link.innerText || '').trim().split('\\n')[0];
                        var locEl = el.querySelector('.posting-categories .sort-by-time, .location, .posting-categories span');
                        var location = locEl ? locEl.innerText.trim() : '';
                        // Try to get department from within posting
                        var deptEl = el.querySelector('.posting-categories .department');
                        var department = deptEl ? deptEl.innerText.trim() : '';
                        if (!department) {
                            // Use section header department
                            var prev = el.previousElementSibling;
                            while (prev) {
                                if (prev.classList && prev.classList.contains('posting-category-title')) {
                                    department = (prev.innerText || '').trim();
                                    break;
                                }
                                prev = prev.previousElementSibling;
                            }
                        }
                        // Extract employment type from text
                        var text = (el.innerText || '').trim();
                        var empType = '';
                        if (text.includes('FULL TIME')) empType = 'Full Time';
                        else if (text.includes('INTERN')) empType = 'Intern';
                        else if (text.includes('TRAINEE')) empType = 'Trainee';
                        else if (text.includes('CONTRACT')) empType = 'Contract';

                        if (title.length >= 3 && title !== 'APPLY') {
                            results.push({
                                title: title,
                                url: url,
                                text: text,
                                location: location,
                                department: department,
                                employment_type: empType
                            });
                        }
                    }
                }

                // Strategy 2: Generic card-based extraction
                if (results.length === 0) {
                    var selectors = [
                        'div.job-card', 'div[class*="job-card"]',
                        'div[class*="job"]', 'div[class*="opening"]',
                        'div[class*="position"]', 'li[class*="opening"]',
                        'li[class*="job"]', 'article'
                    ];
                    for (var s = 0; s < selectors.length; s++) {
                        var cards = document.querySelectorAll(selectors[s]);
                        if (cards.length > 0) {
                            for (var i = 0; i < cards.length; i++) {
                                var card = cards[i];
                                var text = (card.innerText || '').trim();
                                if (text.length < 10) continue;
                                var titleElem = card.querySelector('h5, h3, h4');
                                var title = titleElem ? titleElem.innerText.trim() : '';
                                var link = card.querySelector('a[href]');
                                var url = '';
                                if (link) {
                                    if (!title) title = (link.innerText || '').trim().split('\\n')[0];
                                    url = link.href || '';
                                }
                                if (!title) title = text.split('\\n')[0].trim();
                                if (title.length >= 3 && title.length < 200) {
                                    results.push({title: title, url: url, text: text, location: '', department: '', employment_type: ''});
                                }
                            }
                            if (results.length > 0) break;
                        }
                    }
                }

                // Fallback: link-based extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    var exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq'];
                    for (var i = 0; i < links.length; i++) {
                        var href = links[i].href || '';
                        var text = (links[i].innerText || '').trim();
                        if (text.length < 5 || text.length > 200) continue;
                        var lhref = href.toLowerCase();
                        if (lhref.includes('/job') || lhref.includes('/position') || lhref.includes('/career') ||
                            lhref.includes('/opening') || lhref.includes('/vacancy') || lhref.includes('/role') ||
                            lhref.includes('/requisition') || lhref.includes('/apply') || lhref.includes('lever.co') ||
                            lhref.includes('greenhouse.io')) {
                            var skip = false;
                            for (var e = 0; e < exclude.length; e++) {
                                if (text.toLowerCase().includes(exclude[e])) { skip = true; break; }
                            }
                            if (!skip) results.push({title: text.split('\\n')[0].trim(), url: href, text: text, location: '', department: '', employment_type: ''});
                        }
                    }
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"JavaScript extraction found {len(js_jobs)} potential jobs")
                seen_titles = set()
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    url = job_data.get('url', '')
                    text = job_data.get('text', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    employment_type = job_data.get('employment_type', '')

                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    # If no location from structured element, try text scan
                    if not location:
                        city_names = ['Bangalore', 'Bengaluru', 'Mumbai', 'Delhi', 'Hyderabad', 'India', 'Remote', 'BANGALORE', 'KARNATAKA']
                        for line in text.split('\n'):
                            if any(c in line for c in city_names):
                                location = line.strip()
                                break

                    # Clean up Lever-style location (e.g. "BANGALORE, KARNATAKA" -> proper case)
                    if location and location.isupper():
                        location = location.title()

                    city, state, _ = self.parse_location(location)

                    job_id = f"meesho_{idx}"
                    if url:
                        # Lever URL format: /meesho/UUID
                        if 'lever.co' in url:
                            parts = url.rstrip('/').split('/')
                            job_id = parts[-1] if parts else job_id
                        elif '/job/' in url:
                            job_id = url.split('/job/')[-1].split('?')[0]
                        elif '/jobs/' in url:
                            job_id = url.split('/jobs/')[-1].split('?')[0]
                        else:
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

        except Exception as e:
            logger.error(f"JavaScript extraction error: {str(e)}")

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
                desc_elem = driver.find_element(By.CSS_SELECTOR, 'div[class*="description"]')
                details['description'] = desc_elem.text.strip()[:2000]
            except:
                pass

            try:
                dept_elem = driver.find_element(By.CSS_SELECTOR, 'span[class*="department"]')
                details['department'] = dept_elem.text.strip()
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

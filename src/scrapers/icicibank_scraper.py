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

logger = setup_logger('icicibank_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class ICICIBankScraper:
    def __init__(self):
        self.company_name = 'ICICI Bank'
        # Point to actual job search/listings page
        self.url = 'https://www.icicicareers.com/Find-A-Career'

    def setup_driver(self):
        """Set up Chrome driver with anti-detection"""
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

        driver_paths = [
            CHROMEDRIVER_PATH,
            '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133/chromedriver-mac-arm64/chromedriver',
            '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/143.0.7499.192/chromedriver-mac-arm64/chromedriver',
        ]

        driver = None
        for dp in driver_paths:
            try:
                service = Service(dp)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info(f"ChromeDriver started with: {dp}")
                break
            except Exception as e:
                logger.warning(f"ChromeDriver {dp} failed: {e}")
                continue

        if not driver:
            try:
                driver = webdriver.Chrome(options=chrome_options)
                logger.info("Using default ChromeDriver")
            except Exception as e:
                logger.error(f"All ChromeDriver attempts failed: {e}")
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
        """Scrape jobs from ICICI Bank careers page with pagination support.

        The icicicareers.com/Find-A-Career URL often times out. The actual job listing
        page is at icicicareers.com/CareerApplicant/Career/job-listing/ which has
        card-based job listings with pagination.
        """
        jobs = []
        driver = None

        max_retries = 3
        for attempt in range(max_retries):
          try:
            logger.info(f"Starting scrape for {self.company_name} (attempt {attempt + 1}/{max_retries})")
            driver = self.setup_driver()

            # The Find-A-Career URL tends to time out. Navigate to the working job listing URL.
            job_listing_url = 'https://www.icicicareers.com/CareerApplicant/Career/job-listing/'

            # First try the original URL with a shorter timeout
            try:
                driver.get(self.url)
                time.sleep(5)
                current = driver.current_url
                # If we got redirected to the home page or stuck, go to job listing
                if 'Find-A-Career' not in current and 'job-listing' not in current:
                    logger.info(f"Redirected to {current}, navigating to job listing page")
                    driver.get(job_listing_url)
                elif 'Find-A-Career' in current:
                    # Check if the page actually loaded or just shows error
                    body = driver.find_element(By.TAG_NAME, 'body').text
                    if 'took too long' in body or 'ERR_' in body or len(body) < 100:
                        logger.info("Find-A-Career page timed out, using job listing URL")
                        driver.get(job_listing_url)
            except Exception as e:
                logger.warning(f"Original URL failed ({e}), navigating to job listing page")
                # Reset timeout and navigate to the working URL
                try:
                    driver.quit()
                except:
                    pass
                driver = self.setup_driver()
                driver.get(job_listing_url)

            time.sleep(15)

            # Check we're on the right page
            current_url = driver.current_url
            logger.info(f"Current URL: {current_url}")

            # If we ended up on the home page, navigate to job listing
            if 'Home' in current_url and 'job-listing' not in current_url:
                logger.info("On home page, navigating to job listing")
                driver.get(job_listing_url)
                time.sleep(15)

            # Scrape all pages
            current_page = 1
            max_actual_pages = min(max_pages, 10)  # Safety limit

            while current_page <= max_actual_pages:
                logger.info(f"Scraping page {current_page}")

                page_jobs = self._extract_jobs_from_page(driver)
                jobs.extend(page_jobs)
                logger.info(f"Found {len(page_jobs)} jobs on page {current_page}")

                if not page_jobs:
                    logger.info("No jobs found on this page, stopping pagination")
                    break

                # Try to go to next page
                if current_page < max_actual_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(5)

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

    def _extract_jobs_from_page(self, driver):
        """Extract jobs from the current ICICI careers page using JavaScript"""
        jobs = []

        # Scroll to load content
        for i in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        # Primary: Extract from .img__wrap cards which contain job titles and links
        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};
                // ICICI careers uses .img__wrap divs with card-heightpx class as job cards
                var cards = document.querySelectorAll('.img__wrap, [class*="card-heightpx"]');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var title = card.innerText.trim();
                    if (!title || title.length < 3) continue;

                    // Find the link inside the card
                    var link = card.querySelector('a[href*="job-details"]');
                    if (!link) {
                        // Try parent
                        var parent = card.closest('a[href*="job-details"]');
                        if (parent) link = parent;
                    }
                    if (!link) {
                        // Try any link in the card
                        link = card.querySelector('a[href]');
                    }

                    var href = link ? link.href : '';
                    if (!href || seen[href]) continue;
                    seen[href] = true;

                    results.push({
                        title: title.split('\\n')[0].trim(),
                        href: href
                    });
                }

                // Fallback: try finding links to job-details pages directly
                if (results.length === 0) {
                    document.querySelectorAll('a[href*="job-details"]').forEach(function(a) {
                        var text = (a.innerText || '').trim();
                        var href = a.href;
                        if (text.length > 3 && text.length < 200 && !seen[href]) {
                            seen[href] = true;
                            results.push({
                                title: text.split('\\n')[0].trim(),
                                href: href
                            });
                        }
                    });
                }

                return results;
            """)

            if job_data:
                logger.info(f"Found {len(job_data)} job cards on page")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '')
                    href = jd.get('href', '')

                    if not title or len(title) < 3:
                        continue

                    # Extract job ID from URL (e.g., job-details/2241232)
                    job_id = f"icicibank_{idx}"
                    if href and 'job-details/' in href:
                        job_id = href.split('job-details/')[-1].split('?')[0].split('/')[0]

                    jobs.append({
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
                        'apply_url': href if href else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
        except Exception as e:
            logger.error(f"JS card extraction failed: {e}")

        # Link-based fallback
        if not jobs:
            logger.info("Card extraction failed, trying link-based fallback")
            try:
                all_links = driver.execute_script("""
                    var results = [];
                    var seen = {};
                    document.querySelectorAll('a[href]').forEach(function(a) {
                        var text = (a.innerText || '').trim();
                        var href = a.href;
                        if (text.length > 3 && text.length < 200 && href.length > 10 && !seen[href]) {
                            var lhref = href.toLowerCase();
                            if (lhref.includes('/job') || lhref.includes('/career') || lhref.includes('/position')) {
                                var exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'faq',
                                               'download', 'video', 'trending', 'programmes', 'know-us'];
                                var skip = false;
                                for (var i = 0; i < exclude.length; i++) {
                                    if (text.toLowerCase().includes(exclude[i]) || lhref.includes(exclude[i])) {
                                        skip = true; break;
                                    }
                                }
                                if (!skip && !lhref.endsWith('/job-listing/') && !lhref.endsWith('/job-listing')) {
                                    seen[href] = true;
                                    results.push({title: text.split('\\n')[0].trim(), href: href});
                                }
                            }
                        }
                    });
                    return results;
                """)
                if all_links:
                    for ld in all_links:
                        title = ld.get('title', '')
                        href = ld.get('href', '')
                        if not title or len(title) < 3:
                            continue
                        job_id = hashlib.md5(href.encode()).hexdigest()[:12]
                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '', 'location': '', 'city': '', 'state': '',
                            'country': 'India', 'employment_type': '', 'department': '',
                            'apply_url': href, 'posted_date': '', 'job_function': '',
                            'experience_level': '', 'salary_range': '', 'remote_type': '', 'status': 'active'
                        })
                    if jobs:
                        logger.info(f"Link fallback found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"Link fallback failed: {e}")

        return jobs

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page.

        ICICI careers uses pagination buttons with page numbers (1, 2, 3, 4).
        These are <a> tags without href attributes, so we need to click them.
        """
        try:
            next_page_num = current_page + 1

            # Try clicking the next page number
            page_selectors = [
                (By.XPATH, f'//a[normalize-space(text())="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'.cust-page-item a'),
                (By.XPATH, f'//li[contains(@class,"cust-page-item")]//a[text()="{next_page_num}"]'),
            ]

            for sel_type, sel_value in page_selectors:
                try:
                    elements = driver.find_elements(sel_type, sel_value)
                    for elem in elements:
                        text = elem.text.strip()
                        if text == str(next_page_num):
                            # Scroll to pagination area
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", elem)
                            logger.info(f"Clicked page {next_page_num}")
                            time.sleep(3)
                            return True
                except:
                    continue

            # Fallback: try JS click on pagination
            try:
                clicked = driver.execute_script(f"""
                    var pages = document.querySelectorAll('.cust-page-item a, .cust-pagination a');
                    for (var i = 0; i < pages.length; i++) {{
                        if (pages[i].innerText.trim() === '{next_page_num}') {{
                            pages[i].click();
                            return true;
                        }}
                    }}
                    return false;
                """)
                if clicked:
                    logger.info(f"JS clicked page {next_page_num}")
                    time.sleep(3)
                    return True
            except:
                pass

            logger.warning(f"Could not find page {next_page_num} button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

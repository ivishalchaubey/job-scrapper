# Starbucks India (Tata Starbucks) Scraper
# Site: careers.starbucks.in - SAP SuccessFactors platform
# The homepage shows nav links only; the /search/ page lists all jobs.
# Structure: tr.data-row with a.jobTitle-link, span.jobLocation, span.jobDate, span.jobFacility
# Pagination: 25 per page via startrow query param

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('starbucks_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class StarbucksScraper:
    def __init__(self):
        self.company_name = "Starbucks"
        # Use the search page directly -- the homepage only has nav links, not job listings
        self.url = "https://careers.starbucks.in/search/?createNewAlert=false&q=&locationsearch=India"

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
        """Scrape jobs from Starbucks India (Tata Starbucks) SuccessFactors career portal."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            driver.get(self.url)

            # Smart wait for SuccessFactors job table to load
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a.jobTitle-link, tr.data-row'))
                )
            except Exception:
                time.sleep(5)  # Fallback if selectors not found

            # Quick scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

            current_page = 1
            seen_ids = set()
            consecutive_empty_pages = 0

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                jobs = self._scrape_page(driver, seen_ids)
                all_jobs.extend(jobs)
                logger.info(f"Page {current_page}: found {len(jobs)} new jobs (total: {len(all_jobs)})")

                # Stop if we get 2 consecutive pages with no new jobs
                if len(jobs) == 0:
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= 2:
                        logger.info("No new jobs on 2 consecutive pages, stopping pagination")
                        break
                else:
                    consecutive_empty_pages = 0

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        break
                current_page += 1

            logger.info(f"Total jobs scraped for {self.company_name}: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during {self.company_name} scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page of SuccessFactors search results."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            # Capture current first job text for change detection
            old_first = driver.execute_script("""
                var card = document.querySelector('a.jobTitle-link');
                return card ? card.innerText.substring(0, 50) : '';
            """)

            # SuccessFactors pagination: try specific page number link first, then last-page arrow
            next_selectors = [
                (By.CSS_SELECTOR, f'a[title="Page {current_page + 1}"]'),
                (By.CSS_SELECTOR, 'a.paginationItemLast'),
                (By.CSS_SELECTOR, 'a.next'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.XPATH, '//a[contains(@class,"paginationItemLast")]'),
            ]

            for selector_type, selector_value in next_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    if not next_button.is_displayed() or not next_button.is_enabled():
                        continue
                    btn_class = next_button.get_attribute('class') or ''
                    if 'disabled' in btn_class or 'active' in btn_class:
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", next_button)

                    # Poll for page change instead of blind sleep
                    for _ in range(20):
                        time.sleep(0.2)
                        new_first = driver.execute_script("""
                            var card = document.querySelector('a.jobTitle-link');
                            return card ? card.innerText.substring(0, 50) : '';
                        """)
                        if new_first and new_first != old_first:
                            break
                    time.sleep(0.5)
                    logger.info(f"Navigated to page {current_page + 1}")
                    return True
                except Exception:
                    continue

            # Try clicking on the specific page number in the pagination list
            try:
                page_links = driver.find_elements(By.CSS_SELECTOR, '.pagination a')
                for link in page_links:
                    text = link.text.strip()
                    if text == str(current_page + 1):
                        driver.execute_script("arguments[0].click();", link)
                        for _ in range(20):
                            time.sleep(0.2)
                            new_first = driver.execute_script("""
                                var card = document.querySelector('a.jobTitle-link');
                                return card ? card.innerText.substring(0, 50) : '';
                            """)
                            if new_first and new_first != old_first:
                                break
                        time.sleep(0.5)
                        logger.info(f"Navigated to page {current_page + 1} via page number link")
                        return True
            except Exception:
                pass

            logger.warning("Could not find next page button")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver, seen_ids):
        """Scrape jobs from the current page using JavaScript for reliable extraction."""
        jobs = []

        try:
            # Quick scroll to load all content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)

            # Primary: JS extraction from SuccessFactors DOM
            # Each tr.data-row contains:
            #   - span.jobTitle.hidden-phone > a.jobTitle-link  (title + URL)
            #   - span.jobLocation  (location)
            #   - span.jobDate  (posted date)
            #   - span.jobFacility  (store/facility name)
            js_jobs = driver.execute_script("""
                var results = [];

                // Strategy 1: Extract from desktop view (span.jobTitle.hidden-phone > a.jobTitle-link)
                var titleLinks = document.querySelectorAll('span.jobTitle.hidden-phone a.jobTitle-link');
                if (titleLinks.length === 0) {
                    titleLinks = document.querySelectorAll('a.jobTitle-link');
                }
                if (titleLinks.length > 0) {
                    titleLinks.forEach(function(link) {
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || link.getAttribute('href') || '';
                        if (!title || !href) return;

                        var row = link.closest('tr');
                        var location = '';
                        var facility = '';
                        var postedDate = '';

                        if (row) {
                            var locElem = row.querySelector('td.colLocation span.jobLocation, span.jobLocation');
                            if (locElem) location = (locElem.innerText || locElem.textContent || '').trim();

                            var dateElem = row.querySelector('span.jobDate');
                            if (dateElem) postedDate = (dateElem.innerText || dateElem.textContent || '').trim();

                            var facElem = row.querySelector('td.colFacility span.jobFacility, span.jobFacility');
                            if (facElem) facility = (facElem.innerText || facElem.textContent || '').trim();
                        }

                        results.push({
                            title: title,
                            url: href,
                            location: location,
                            facility: facility,
                            postedDate: postedDate
                        });
                    });
                }

                // Strategy 2: table rows directly
                if (results.length === 0) {
                    var rows = document.querySelectorAll('tr.data-row');
                    rows.forEach(function(row) {
                        var link = row.querySelector('a.jobTitle-link') || row.querySelector('a[href*="/job/"]');
                        if (!link) return;
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || link.getAttribute('href') || '';
                        if (!title || !href || href === '#') return;

                        var location = '';
                        var facility = '';
                        var postedDate = '';
                        var locElem = row.querySelector('span.jobLocation');
                        if (locElem) location = (locElem.innerText || locElem.textContent || '').trim();
                        var facElem = row.querySelector('span.jobFacility');
                        if (facElem) facility = (facElem.innerText || facElem.textContent || '').trim();
                        var dateElem = row.querySelector('span.jobDate');
                        if (dateElem) postedDate = (dateElem.innerText || dateElem.textContent || '').trim();

                        results.push({
                            title: title.split('\\n')[0].trim(),
                            url: href,
                            location: location,
                            facility: facility,
                            postedDate: postedDate
                        });
                    });
                }

                // Strategy 3: Fallback - any link containing /job/ in the path
                if (results.length === 0) {
                    document.querySelectorAll('a[href*="/job/"]').forEach(function(link) {
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || '';
                        if (title && title.length > 3 && title.length < 200 && href) {
                            results.push({
                                title: title.split('\\n')[0].trim(),
                                url: href,
                                location: '',
                                facility: '',
                                postedDate: ''
                            });
                        }
                    });
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JavaScript extraction found {len(js_jobs)} jobs")
                for jl in js_jobs:
                    title = jl.get('title', '').strip()
                    url = jl.get('url', '').strip()
                    if not title or not url:
                        continue

                    job_id = self._extract_job_id(url)
                    external_id = self.generate_external_id(job_id, self.company_name)

                    if external_id in seen_ids:
                        continue

                    location = jl.get('location', '').strip()
                    facility = jl.get('facility', '').strip()
                    posted_date = jl.get('postedDate', '').strip()

                    # Build a combined location string from location and facility
                    # SuccessFactors location is like "Mumbai, IN" and facility is the store name
                    full_location = location
                    if facility and facility not in location:
                        full_location = f"{location} - {facility}" if location else facility

                    job_data = {
                        'external_id': external_id,
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url,
                        'location': full_location,
                        'department': facility,
                        'employment_type': '',
                        'description': '',
                        'posted_date': posted_date,
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    location_parts = self.parse_location(location)
                    job_data.update(location_parts)

                    jobs.append(job_data)
                    seen_ids.add(external_id)
                    logger.info(f"Extracted: {title} | {full_location}")
            else:
                logger.warning("JavaScript extraction found no jobs, trying Selenium fallback")
                jobs = self._scrape_page_selenium(driver, seen_ids)

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        # Log diagnostic info if no jobs found
        if not jobs:
            try:
                body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                logger.info(f"Page body preview: {body_text}")
                current_url = driver.current_url
                logger.info(f"Current URL: {current_url}")
            except Exception:
                pass

        return jobs

    def _scrape_page_selenium(self, driver, seen_ids):
        """Fallback Selenium-based extraction for the page."""
        jobs = []

        try:
            job_elements = []
            selectors = [
                "tr.data-row",
                "a.jobTitle-link",
                "span.jobTitle a",
                "a[href*='/job/']",
            ]

            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Selenium found {len(elements)} elements using: {selector}")
                        break
                except Exception:
                    continue

            if not job_elements:
                logger.warning("Selenium fallback found no job elements")
                return jobs

            for idx, elem in enumerate(job_elements, 1):
                try:
                    job_data = self._extract_job_from_element(elem, idx)
                    if job_data and job_data['external_id'] not in seen_ids:
                        jobs.append(job_data)
                        seen_ids.add(job_data['external_id'])
                        logger.info(f"Selenium extracted: {job_data.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Selenium fallback error: {str(e)}")

        return jobs

    def _extract_job_from_element(self, job_elem, idx):
        """Extract job data from a single Selenium element."""
        try:
            title = ""
            job_url = ""

            tag_name = job_elem.tag_name
            if tag_name == 'a':
                title = job_elem.text.strip()
                job_url = job_elem.get_attribute('href')
            else:
                title_selectors = [
                    "a.jobTitle-link",
                    "span.jobTitle a",
                    "a[href*='/job/']",
                    "a"
                ]
                for selector in title_selectors:
                    try:
                        title_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip()
                        job_url = title_elem.get_attribute('href')
                        if title and job_url:
                            break
                    except Exception:
                        continue

            if not title:
                text = job_elem.text.strip()
                if text:
                    title = text.split('\n')[0].strip()

            if not title or not job_url:
                return None

            job_id = self._extract_job_id(job_url)

            location = ""
            facility = ""
            try:
                loc_elem = job_elem.find_element(By.CSS_SELECTOR, "span.jobLocation")
                location = loc_elem.text.strip()
            except Exception:
                pass

            try:
                fac_elem = job_elem.find_element(By.CSS_SELECTOR, "span.jobFacility")
                facility = fac_elem.text.strip()
            except Exception:
                pass

            full_location = location
            if facility and facility not in location:
                full_location = f"{location} - {facility}" if location else facility

            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': full_location,
                'department': facility,
                'employment_type': '',
                'description': '',
                'posted_date': '',
                'city': '',
                'state': '',
                'country': 'India',
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            location_parts = self.parse_location(location)
            job_data.update(location_parts)

            return job_data

        except Exception as e:
            logger.error(f"Error extracting job data: {str(e)}")
            return None

    def _extract_job_id(self, job_url):
        """Extract numeric job ID from a SuccessFactors URL like /job/Mumbai-Barista/1356742066/"""
        job_id = ""
        if '/job/' in job_url:
            parts = job_url.rstrip('/').split('/')
            for part in reversed(parts):
                if part.isdigit():
                    job_id = part
                    break
        if not job_id:
            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]
        return job_id

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(4)

            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div.job-description'),
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.CSS_SELECTOR, '.jobDisplay .content'),
                    (By.XPATH, '//h2[contains(text(), "Description")]/following-sibling::div'),
                    (By.CSS_SELECTOR, 'div[id*="description"]'),
                ]

                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        if desc_elem and desc_elem.text.strip():
                            details['description'] = desc_elem.text.strip()[:3000]
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass

        return details

    def parse_location(self, location_str):
        """Parse SuccessFactors location string like 'Mumbai, IN' into city, state, country.

        Handles edge cases:
          - 'Mumbai, IN' -> city=Mumbai, country=India
          - 'IN' -> city='', country=India  (country code only, no city)
          - 'Delhi, Maharashtra, IN' -> city=Delhi, state=Maharashtra, country=India
        """
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result

        country_codes = ['IN', 'IND', 'India']

        parts = [p.strip() for p in location_str.split(',')]

        # Single part that is just a country code -- no city info
        if len(parts) == 1:
            if parts[0] in country_codes:
                return result
            result['city'] = parts[0]
        elif len(parts) == 2:
            if parts[1] in country_codes:
                result['city'] = parts[0]
                result['country'] = 'India'
            else:
                result['city'] = parts[0]
                result['state'] = parts[1]
        elif len(parts) >= 3:
            result['city'] = parts[0]
            result['state'] = parts[1]
            if parts[2] in country_codes:
                result['country'] = 'India'
            else:
                result['country'] = parts[2]

        return result


if __name__ == "__main__":
    scraper = StarbucksScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['apply_url']}")

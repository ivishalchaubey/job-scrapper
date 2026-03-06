from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('shoppersstop_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class ShoppersStopScraper:
    def __init__(self):
        self.company_name = 'Shoppers Stop'
        # Shoppers Stop uses DarwinBox v1 for their careers portal.
        # The old URL (shoppersstop.com/careers) returns a 404.
        # ss-people.darwinbox.in is their active DarwinBox tenant.
        # The candidatev2 URL redirects to the v1 /ms/candidate/careers page,
        # which uses a server-rendered table layout (not the v2 SPA tiles).
        self.url = 'https://ss-people.darwinbox.in/ms/candidate/careers'

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
        """Scrape jobs from Shoppers Stop DarwinBox careers page.

        The DarwinBox v1 portal at ss-people.darwinbox.in renders jobs
        in a server-side table (table.db-table-one). Each table row has
        cells for: title (with link), department, location, employee type,
        posted date. Pagination uses li.pagination-page / li.pagination-next.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(15)

            # Check if the page has content or is just a stub
            body_text = driver.find_element(By.TAG_NAME, 'body').text.strip()
            if not body_text or body_text == '-' or body_text == f'{self.company_name} -':
                logger.info("DarwinBox portal has no active job postings at this time")
                return jobs

            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")

                page_jobs = self._scrape_darwinbox_table(driver)
                jobs.extend(page_jobs)
                logger.info(f"Found {len(page_jobs)} jobs on page {current_page}")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver):
                        logger.info("No more pages available")
                        break
                    time.sleep(5)

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _go_to_next_page(self, driver):
        """Click the next page button in DarwinBox v1 pagination."""
        try:
            # DarwinBox v1 pagination uses li.pagination-next with an <a> inside
            next_btn = driver.find_elements(By.CSS_SELECTOR, 'li.pagination-next:not(.disabled) a.page-link')
            if next_btn:
                driver.execute_script("arguments[0].click();", next_btn[0])
                logger.info("Clicked next page button")
                return True

            # Fallback: try clicking the next numbered page
            active_page = driver.find_elements(By.CSS_SELECTOR, 'li.pagination-page.active')
            if active_page:
                next_sibling = driver.execute_script(
                    "return arguments[0].nextElementSibling;", active_page[0]
                )
                if next_sibling:
                    cls = next_sibling.get_attribute('class') or ''
                    if 'pagination-page' in cls:
                        link = next_sibling.find_elements(By.TAG_NAME, 'a')
                        if link:
                            driver.execute_script("arguments[0].click();", link[0])
                            logger.info("Clicked next numbered page")
                            return True

            logger.info("No next page button found")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_darwinbox_table(self, driver):
        """Extract jobs from the DarwinBox v1 table layout using JavaScript.

        DarwinBox v1 DOM structure:
        - table.db-table-one > tbody > tr (job rows)
        - Each tr has 6 td cells:
          [0] title (contains <a href="/ms/candidate/careers/JOBID">)
          [1] department
          [2] location (e.g. "Store - City Mall, City, State, India")
          [3] employee type (e.g. "Apprentice", "General")
          [4] posted date (e.g. "Feb 27, 2026")
          [5] empty / actions
        """
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: DarwinBox v1 table (db-table-one)
                var table = document.querySelector('table.db-table-one');
                if (table) {
                    var rows = table.querySelectorAll('tbody tr');
                    for (var i = 0; i < rows.length; i++) {
                        var cells = rows[i].querySelectorAll('td');
                        if (cells.length < 4) continue;

                        var titleCell = cells[0];
                        var link = titleCell.querySelector('a[href*="/careers/"]');
                        var title = (link ? link.innerText : titleCell.innerText).trim();
                        var href = link ? link.href : '';

                        if (!title || title.length < 3 || seen[href || title]) continue;
                        seen[href || title] = true;

                        var department = cells.length > 1 ? cells[1].innerText.trim() : '';
                        var location = cells.length > 2 ? cells[2].innerText.trim() : '';
                        var employeeType = cells.length > 3 ? cells[3].innerText.trim() : '';
                        var postedDate = cells.length > 4 ? cells[4].innerText.trim() : '';

                        results.push({
                            title: title,
                            url: href,
                            department: department,
                            location: location,
                            employment_type: employeeType,
                            posted_date: postedDate
                        });
                    }
                }

                // Strategy 2: Fallback — any clickable job links in the page
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/careers/"]');
                    for (var i = 0; i < links.length; i++) {
                        var a = links[i];
                        var text = a.innerText.trim();
                        var href = a.href;
                        // Skip navigation links
                        if (!text || text.length < 3 || text === 'apply here' ||
                            text.includes('LOGIN') || text.includes('SIGN UP')) continue;
                        if (seen[href]) continue;
                        seen[href] = true;

                        // Try to get context from parent row
                        var row = a.closest('tr');
                        var department = '';
                        var location = '';
                        var employeeType = '';
                        var postedDate = '';
                        if (row) {
                            var cells = row.querySelectorAll('td');
                            if (cells.length > 1) department = cells[1].innerText.trim();
                            if (cells.length > 2) location = cells[2].innerText.trim();
                            if (cells.length > 3) employeeType = cells[3].innerText.trim();
                            if (cells.length > 4) postedDate = cells[4].innerText.trim();
                        }

                        results.push({
                            title: text,
                            url: href,
                            department: department,
                            location: location,
                            employment_type: employeeType,
                            posted_date: postedDate
                        });
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"DarwinBox extraction found {len(js_jobs)} jobs on current page")
                seen_urls = set()
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    url = job_data.get('url', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    employment_type = job_data.get('employment_type', '')
                    posted_date = job_data.get('posted_date', '')

                    if not title:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    city, state, _ = self.parse_location(location)

                    # Extract job ID from URL (e.g. /careers/a69a1853d4a808)
                    job_id = f"shoppersstop_{idx}"
                    if url and '/careers/' in url:
                        job_id = url.split('/careers/')[-1].split('?')[0].split('/')[0]
                    elif url:
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
                        'posted_date': posted_date,
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No job rows found on DarwinBox page")

        except Exception as e:
            logger.error(f"DarwinBox extraction error: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        """Parse DarwinBox v1 location string into city, state, country.

        DarwinBox v1 locations look like:
        "Store - City Mall, City, State, India"
        """
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]

        city = ''
        state = ''
        for part in parts:
            part_clean = part.strip()
            if part_clean == 'India':
                continue
            # Skip store/branch identifiers (contain hyphens or special chars)
            if ' - ' in part_clean and not city:
                # Extract city name from "Store - CityName Mall" patterns
                after_dash = part_clean.split(' - ', 1)[-1].strip()
                # Remove common suffixes like "Mall", "Store"
                for suffix in ['Mall', 'Store', 'Outlet', 'Shop', 'Branch', 'Airport']:
                    if after_dash.endswith(suffix):
                        after_dash = after_dash[:-(len(suffix))].strip()
                if after_dash:
                    city = after_dash
                continue
            if '#' in part_clean or '_' in part_clean:
                continue
            if '..+' in part_clean:
                continue
            if not city:
                city = part_clean
            elif not state:
                state = part_clean

        return city, state, 'India'


if __name__ == '__main__':
    scraper = ShoppersStopScraper()
    results = scraper.scrape()
    print(f"Scraped {len(results)} jobs from {scraper.company_name}")
    for job in results[:15]:
        print(f"  - {job['title']} | {job['department']} | {job['location']} | {job['employment_type']} | {job['posted_date']}")

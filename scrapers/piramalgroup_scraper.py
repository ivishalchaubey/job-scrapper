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

logger = setup_logger('piramalgroup_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class PiramalGroupScraper:
    def __init__(self):
        self.company_name = 'Piramal Group'
        self.url = 'https://www.piramal.com/careers'

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
        """Scrape jobs from Piramal Group careers.

        The piramal.com/careers page returns 404. Piramal Group uses Darwinbox for
        job listings at piramalgroup.darwinbox.in/ms/candidate/careers. The scraper
        navigates from the main piramal.com page to find the Darwinbox careers link.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # piramal.com/careers returns 404, navigate through main site
            # The main piramal.com links to subsidiary career pages which use Darwinbox
            darwinbox_url = 'https://piramalgroup.darwinbox.in/ms/candidate/careers'

            # First try the original URL, if it 404s go to the Darwinbox page
            driver.get(self.url)
            time.sleep(8)

            # Check if page loaded properly or is a 404
            body_text = driver.find_element(By.TAG_NAME, 'body').text
            is_404 = '404' in body_text or "can't be found" in body_text or 'not found' in body_text.lower()

            if is_404:
                logger.info("Careers page returned 404, navigating to main site to find careers link")
                driver.get('https://www.piramal.com')
                time.sleep(12)

                # Look for career links that lead to Darwinbox
                try:
                    career_links = driver.execute_script("""
                        var results = [];
                        document.querySelectorAll('a[href]').forEach(function(a) {
                            var href = a.href.toLowerCase();
                            if (href.includes('darwinbox') || href.includes('piramalfinance.com/career')) {
                                results.push(a.href);
                            }
                        });
                        return results;
                    """)
                    if career_links:
                        darwinbox_url = career_links[0]
                        logger.info(f"Found career link: {darwinbox_url}")
                except Exception as e:
                    logger.warning(f"Could not find career link on main page: {e}")

                # If we found a piramalfinance link, follow it to find the Darwinbox link
                if 'piramalfinance' in darwinbox_url:
                    driver.get(darwinbox_url)
                    time.sleep(10)
                    try:
                        db_links = driver.execute_script("""
                            var results = [];
                            document.querySelectorAll('a[href]').forEach(function(a) {
                                if (a.href.includes('darwinbox')) {
                                    results.push(a.href);
                                }
                            });
                            return results;
                        """)
                        if db_links:
                            darwinbox_url = db_links[0]
                            logger.info(f"Found Darwinbox link: {darwinbox_url}")
                    except:
                        darwinbox_url = 'https://piramalgroup.darwinbox.in/ms/candidate/careers'

            logger.info(f"Navigating to Darwinbox careers: {darwinbox_url}")
            driver.get(darwinbox_url)
            time.sleep(15)

            # Scroll to load
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Extract jobs from Darwinbox
            jobs = self._extract_darwinbox_jobs(driver)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_darwinbox_jobs(self, driver):
        """Extract jobs from the Darwinbox careers page using JavaScript"""
        jobs = []

        # Primary: Extract job listings from Darwinbox links
        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};
                // Darwinbox job listings are <a> tags linking to individual career pages
                document.querySelectorAll('a[href*="/ms/candidate/careers/"]').forEach(function(a) {
                    var href = a.href;
                    var text = (a.innerText || '').trim();
                    // Skip non-job links (main page, apply here, etc.)
                    if (href.endsWith('/careers') || href.endsWith('/careers/') || href.includes('/others')) return;
                    if (text.length < 3 || text.length > 300 || seen[href]) return;
                    seen[href] = true;

                    // Try to extract structured data from the link text
                    // Darwinbox format: "Title Department Location EmployeeType Date"
                    var lines = text.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                    var title = lines[0] || text.split('\\n')[0].trim();
                    var department = '';
                    var location = '';
                    var employeeType = '';
                    var postedDate = '';

                    // Try to find department, location from sibling/parent elements
                    var row = a.closest('tr') || a.closest('[class*="row"]') || a.closest('div');
                    if (row) {
                        var rowText = row.innerText.trim();
                        var rowLines = rowText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        if (rowLines.length > 1) {
                            title = rowLines[0];
                            department = rowLines.length > 1 ? rowLines[1] : '';
                            location = rowLines.length > 2 ? rowLines[2] : '';
                            employeeType = rowLines.length > 3 ? rowLines[3] : '';
                            postedDate = rowLines.length > 4 ? rowLines[4] : '';
                        }
                    }

                    results.push({
                        title: title,
                        href: href,
                        department: department,
                        location: location,
                        employeeType: employeeType,
                        postedDate: postedDate
                    });
                });
                return results;
            """)

            if job_data:
                logger.info(f"Darwinbox extraction found {len(job_data)} jobs")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '')
                    href = jd.get('href', '')
                    department = jd.get('department', '')
                    location = jd.get('location', '')
                    employee_type = jd.get('employeeType', '')
                    posted_date = jd.get('postedDate', '')

                    if not title or len(title) < 3:
                        continue

                    # Generate job ID from Darwinbox URL hash
                    job_id = href.split('/careers/')[-1].split('?')[0] if '/careers/' in href else f"piramal_{idx}"

                    city, state, country = self.parse_location(location)

                    # Map employee type
                    emp_type = ''
                    if employee_type:
                        et_lower = employee_type.lower()
                        if 'intern' in et_lower or 'contingent' in et_lower:
                            emp_type = 'Intern'
                        elif 'contract' in et_lower:
                            emp_type = 'Contract'
                        elif 'employee' in et_lower:
                            emp_type = 'Full-time'

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country if country else 'India',
                        'employment_type': emp_type,
                        'department': department,
                        'apply_url': href if href else self.url,
                        'posted_date': posted_date,
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
        except Exception as e:
            logger.error(f"Darwinbox extraction failed: {e}")

        # Fallback: Extract from page text using broader approach
        if not jobs:
            logger.info("Primary extraction failed, trying text-based fallback")
            try:
                body_text = driver.find_element(By.TAG_NAME, 'body').text
                all_links = driver.execute_script("""
                    var results = [];
                    document.querySelectorAll('a[href]').forEach(function(a) {
                        var text = (a.innerText || '').trim();
                        var href = a.href;
                        if (text.length > 5 && text.length < 200 && href.length > 10) {
                            var lhref = href.toLowerCase();
                            if (lhref.includes('/career') || lhref.includes('/job') || lhref.includes('/opening')) {
                                var exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'careers', 'darwinbox.com'];
                                var skip = false;
                                for (var i = 0; i < exclude.length; i++) {
                                    if (text.toLowerCase() === exclude[i] || href.includes(exclude[i])) { skip = true; break; }
                                }
                                if (!skip) {
                                    results.push({title: text.split('\\n')[0].trim(), href: href});
                                }
                            }
                        }
                    });
                    return results;
                """)

                if all_links:
                    seen = set()
                    for ld in all_links:
                        title = ld.get('title', '')
                        href = ld.get('href', '')
                        if not title or href in seen:
                            continue
                        seen.add(href)
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
                        logger.info(f"Fallback found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"Text fallback failed: {e}")

        return jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        # Handle "Multiple locations" case
        if 'multiple' in location_str.lower():
            return 'Multiple locations', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        # Check for India in the location
        country = 'India'
        if parts and 'india' in parts[-1].lower():
            country = 'India'
            if len(parts) > 2:
                state = parts[-2]

        return city, state, country

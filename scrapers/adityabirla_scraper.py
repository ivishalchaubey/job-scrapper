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

logger = setup_logger('adityabirla_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class AdityaBirlaScraper:
    def __init__(self):
        self.company_name = 'Aditya Birla Group'
        self.url = 'https://careers.adityabirla.com/job-search'

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
            driver_path = CHROMEDRIVER_PATH
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
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
        """Scrape jobs from Aditya Birla careers page with pagination support"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)

            # Wait for page to load
            time.sleep(15)

            # Scroll to trigger lazy-loaded content (with null checks for document.body)
            for scroll_i in range(5):
                driver.execute_script("var b=document.body; var h=document.documentElement; if(b&&h){var m=Math.max(b.scrollHeight||0,h.scrollHeight||0);window.scrollTo(0,m*%s);}" % str((scroll_i + 1) / 5))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                # Scrape current page using JS extraction
                page_jobs = self._scrape_page_js(driver)
                jobs.extend(page_jobs)

                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(5)
                    # Scroll again after page change (with null checks)
                    for scroll_i in range(3):
                        driver.execute_script("var b=document.body; var h=document.documentElement; if(b&&h){var m=Math.max(b.scrollHeight||0,h.scrollHeight||0);window.scrollTo(0,m*%s);}" % str((scroll_i + 1) / 3))
                        time.sleep(1)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)

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
            # Scroll to bottom where pagination is (with null check)
            driver.execute_script("var b=document.body; var h=document.documentElement; if(b&&h){var m=Math.max(b.scrollHeight||0,h.scrollHeight||0);window.scrollTo(0,m);}")
            time.sleep(1)

            # Try clicking next page - the site uses numbered pagination and next buttons
            next_clicked = driver.execute_script("""
                // Try to find a "next" or ">" button
                var buttons = document.querySelectorAll('button, a');
                for (var i = 0; i < buttons.length; i++) {
                    var text = (buttons[i].textContent || '').trim();
                    var ariaLabel = (buttons[i].getAttribute('aria-label') || '').toLowerCase();
                    if (text === '>' || text === 'Next' || text === 'next' ||
                        ariaLabel.includes('next') || ariaLabel.includes('forward')) {
                        buttons[i].click();
                        return true;
                    }
                }
                // Try numbered page button
                var nextPageNum = """ + str(current_page + 1) + """;
                for (var j = 0; j < buttons.length; j++) {
                    var btnText = (buttons[j].textContent || '').trim();
                    if (btnText === String(nextPageNum)) {
                        buttons[j].click();
                        return true;
                    }
                }
                return false;
            """)

            if next_clicked:
                logger.info(f"Clicked next page button")
                return True

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page_js(self, driver):
        """Scrape jobs from current page using JavaScript extraction"""
        jobs = []
        time.sleep(3)

        try:
            # Extract job data using JavaScript - the page has links like
            # /job-search/job-details/ABG98609 with job title as link text
            # Job blocks contain: location, title, position, experience, organisation, date, #ABG ID
            js_jobs = driver.execute_script("""
                var jobs = [];
                var seen = {};

                // Find all job detail links (each job has two: title link + "See Details" link)
                var links = document.querySelectorAll('a[href*="/job-search/job-details/"]');

                for (var i = 0; i < links.length; i++) {
                    var link = links[i];
                    var text = (link.textContent || '').trim();
                    var href = link.href || '';

                    // Skip "See Details" links and duplicates
                    if (text === 'See Details' || text.length < 3) continue;

                    // Extract ABG ID from URL
                    var match = href.match(/job-details\\/(ABG\\d+)/);
                    var abgId = match ? match[1] : '';

                    if (!abgId || seen[abgId]) continue;
                    seen[abgId] = true;

                    // Get the parent container to extract other fields
                    var container = link;
                    // Walk up to find the job card container (usually a few levels up)
                    for (var p = 0; p < 10; p++) {
                        if (container.parentElement) {
                            container = container.parentElement;
                            var containerText = container.innerText || '';
                            if (containerText.includes('#' + abgId) && containerText.includes('Experience')) {
                                break;
                            }
                        }
                    }

                    var containerText = (container.innerText || '').trim();
                    var lines = containerText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                    var location = '';
                    var position = '';
                    var experience = '';
                    var organisation = '';
                    var postedDate = '';

                    for (var j = 0; j < lines.length; j++) {
                        var line = lines[j];
                        if (line.startsWith('India,') || line.startsWith('USA,') || line.startsWith('Thailand,') || line.startsWith('Egypt,')) {
                            location = line;
                        }
                        if (line.startsWith('Position:')) {
                            position = line.replace('Position:', '').trim();
                        }
                        if (line.startsWith('Experience:')) {
                            experience = line.replace('Experience:', '').trim();
                        }
                        if (line.startsWith('Organisation:')) {
                            organisation = line.replace('Organisation:', '').trim();
                        }
                        if (line.startsWith('Posted on')) {
                            postedDate = line.replace('Posted on', '').trim();
                        }
                    }

                    jobs.push({
                        title: text,
                        url: href,
                        abgId: abgId,
                        location: location,
                        position: position,
                        experience: experience,
                        organisation: organisation,
                        postedDate: postedDate
                    });
                }

                return jobs;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                for job_data in js_jobs:
                    title = job_data.get('title', '')
                    if not title or len(title) < 3:
                        continue

                    abg_id = job_data.get('abgId', '')
                    location = job_data.get('location', '')
                    city, state, country = self.parse_location(location)

                    # Extract employment type from experience field
                    experience = job_data.get('experience', '')
                    employment_type = ''
                    if 'Full time' in experience or 'Full Time' in experience:
                        employment_type = 'Full-time'
                    elif 'Part time' in experience or 'Part Time' in experience:
                        employment_type = 'Part-time'
                    elif 'Contract' in experience:
                        employment_type = 'Contract'

                    job = {
                        'external_id': self.generate_external_id(abg_id or title, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': f"Position: {job_data.get('position', '')}. Experience: {experience}",
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': employment_type,
                        'department': job_data.get('organisation', ''),
                        'apply_url': job_data.get('url', self.url),
                        'posted_date': job_data.get('postedDate', ''),
                        'job_function': job_data.get('position', ''),
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job)
            else:
                logger.warning("JS extraction found no jobs")

        except Exception as e:
            logger.error(f"Error in JS extraction: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        # Format is typically: "India, State, City/Office, Detail"
        country = parts[0] if len(parts) > 0 else 'India'
        state = parts[1] if len(parts) > 1 else ''
        city = parts[2] if len(parts) > 2 else ''

        return city, state, country

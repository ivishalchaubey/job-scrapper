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

logger = setup_logger('hindalco_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class HindalcoScraper:
    def __init__(self):
        self.company_name = 'Hindalco Industries'
        # Hindalco jobs are listed on Aditya Birla Group's careers portal under Metals
        self.url = 'https://careers.adityabirla.com/nf-metals'

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
        """Scrape jobs from Hindalco Industries via Aditya Birla Group careers portal"""
        jobs = []
        driver = None

        max_retries = 3
        job_search_url = 'https://careers.adityabirla.com/job-search'

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

            time.sleep(15)

            # Scroll to trigger lazy-loaded content
            for scroll_i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((scroll_i + 1) / 5))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Scrape jobs from the Metals page
            page_jobs = self._scrape_page_js(driver)
            jobs.extend(page_jobs)

            # If no jobs found on metals page, try the general job-search page
            if not jobs:
                logger.info("No jobs on metals page, trying general job-search page")
                driver.get(job_search_url)
                time.sleep(15)
                for scroll_i in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((scroll_i + 1) / 3))
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)
                search_jobs = self._scrape_page_js(driver)
                jobs.extend(search_jobs)

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

    def _scrape_page_js(self, driver):
        """Scrape jobs using JavaScript extraction - same pattern as Aditya Birla portal"""
        jobs = []
        time.sleep(3)

        try:
            # Extract job data - links have pattern /job-search/job-details/ABG{ID}
            js_jobs = driver.execute_script("""
                var jobs = [];
                var seen = {};

                // Try result-card structure first (cp-jobs-card > result-card)
                var resultCards = document.querySelectorAll('.result-card');
                for (var r = 0; r < resultCards.length; r++) {
                    var card = resultCards[r];
                    var titleEl = card.querySelector('.job-title h3, .job-title a, .job-title');
                    if (!titleEl) continue;
                    var title = (titleEl.textContent || '').trim();
                    if (title === 'No Jobs Available' || title.length < 3) continue;

                    var linkEl = card.querySelector('a[href*="job-details"]');
                    var href = linkEl ? linkEl.href : '';
                    var match = href ? href.match(/job-details\/(ABG\d+)/) : null;
                    var abgId = match ? match[1] : '';

                    if (abgId && seen[abgId]) continue;
                    if (abgId) seen[abgId] = true;

                    var infoEl = card.querySelector('.job-info, .job-data');
                    var infoText = infoEl ? infoEl.innerText : '';

                    jobs.push({
                        title: title,
                        url: href || '',
                        abgId: abgId || title,
                        location: '',
                        position: '',
                        experience: '',
                        organisation: 'Metals',
                        postedDate: ''
                    });
                }

                if (jobs.length > 0) return jobs;

                // Fallback: Find all job detail links
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
                        if (line.startsWith('India,') || line.startsWith('USA,') || line.startsWith('Thailand,')) {
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
                        if (line.startsWith('Posted on') || line.match(/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)/)) {
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
                        'department': job_data.get('organisation', 'Metals'),
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

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
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('delhivery_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class DelhiveryScraper:
    def __init__(self):
        self.company_name = 'Delhivery'
        self.url = 'https://www.delhivery.com/careers/'

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
        """Scrape jobs from Delhivery careers page.

        NOTE: As of Feb 2026, the delhivery.com/careers/ (with trailing slash)
        redirects to /404. The careers landing page at /careers (no trailing slash)
        works but is just a landing page. Actual job listings are hosted on
        Darwinbox at delhivery.darwinbox.in. This scraper navigates from the
        careers landing page to the Darwinbox job listings and extracts jobs
        from div.job-tile elements.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Strategy 1: Navigate to the careers landing page
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(12)

            # Check if we got a 404 or error page
            if self._check_if_error_page(driver):
                logger.warning(f"Careers page at {self.url} returns 404/error - trying without trailing slash")
                driver.get('https://www.delhivery.com/careers')
                time.sleep(8)

            # Strategy 2: Look for the Darwinbox jobs link on the careers page
            darwinbox_url = None
            try:
                darwinbox_url = driver.execute_script("""
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var href = links[i].href || '';
                        if (href.includes('darwinbox.in') && (href.includes('careers') || href.includes('jobs'))) {
                            return href;
                        }
                    }
                    return null;
                """)
            except:
                pass

            if darwinbox_url:
                logger.info(f"Found Darwinbox careers link: {darwinbox_url}")
                driver.get(darwinbox_url)
                time.sleep(12)

                # Check if we're on the careers home page and navigate to allJobs
                current_url = driver.current_url
                if '/careers/home' in current_url or current_url.endswith('/careers'):
                    # Click "Open Jobs" or navigate to allJobs
                    all_jobs_url = None
                    try:
                        all_jobs_url = driver.execute_script("""
                            var links = document.querySelectorAll('a[href]');
                            for (var i = 0; i < links.length; i++) {
                                var href = links[i].href || '';
                                if (href.includes('allJobs') || href.includes('all-jobs') || href.includes('openJobs')) {
                                    return href;
                                }
                            }
                            return null;
                        """)
                    except:
                        pass

                    if all_jobs_url:
                        logger.info(f"Navigating to all jobs page: {all_jobs_url}")
                        driver.get(all_jobs_url)
                        time.sleep(12)
            else:
                # Fallback: go directly to known Darwinbox URL
                logger.info("No Darwinbox link found on careers page, trying direct URL")
                driver.get('https://delhivery.darwinbox.in/ms/candidatev2/main/careers/allJobs')
                time.sleep(12)

            # Scroll to load all job tiles
            for i in range(5):
                driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                time.sleep(2)
            driver.execute_script('window.scrollTo(0, 0);')
            time.sleep(2)

            # Extract jobs from the Darwinbox page
            page_jobs = self._scrape_darwinbox_jobs(driver)
            jobs.extend(page_jobs)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _check_if_error_page(self, driver):
        """Check if the current page shows a 404 or error page"""
        try:
            body_text = driver.execute_script("return document.body.innerText.substring(0, 500)")
            current_url = driver.current_url.lower()

            if '/404' in current_url:
                return True
            if '404' in body_text and ('error' in body_text.lower() or 'not found' in body_text.lower()):
                return True
            if 'wrong route' in body_text.lower():
                return True
            if 'page not found' in body_text.lower():
                return True
        except:
            pass
        return False

    def _scrape_darwinbox_jobs(self, driver):
        """Extract jobs from the Darwinbox allJobs page using JavaScript"""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                // Darwinbox uses div.job-tile with span.job-title for each job
                var tiles = document.querySelectorAll('div.job-tile, div.jobs-section');
                for (var i = 0; i < tiles.length; i++) {
                    var tile = tiles[i];
                    var text = (tile.innerText || '').trim();
                    if (text.length < 5) continue;

                    // Get title from span.job-title or first line
                    var titleEl = tile.querySelector('span.job-title, .title-section');
                    var title = titleEl ? titleEl.innerText.trim() : text.split('\\n')[0].trim();

                    // Get the apply link
                    var linkEl = tile.querySelector('a[href*="jobDetails"]');
                    var url = linkEl ? linkEl.href : '';

                    // Get location - it's typically the second line
                    var lines = text.split('\\n');
                    var location = '';
                    var experience = '';
                    var employment_type = '';
                    for (var j = 0; j < lines.length; j++) {
                        var line = lines[j].trim();
                        if (line.includes('India') || line.includes('Haryana') || line.includes('Gujarat') ||
                            line.includes('Maharashtra') || line.includes('Karnataka') || line.includes('Goa') ||
                            line.includes('Delhi') || line.includes('Tamil Nadu')) {
                            location = line;
                        }
                        if (line.includes('Years') || line.includes('years')) {
                            experience = line;
                        }
                        if (line === 'Permanent' || line === 'Contract' || line === 'Probation' || line === 'Intern') {
                            employment_type = line;
                        }
                    }

                    if (title.length >= 3 && title !== 'View and Apply') {
                        results.push({
                            title: title,
                            url: url,
                            location: location,
                            experience: experience,
                            employment_type: employment_type
                        });
                    }
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"Darwinbox extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    url = job_data.get('url', '')
                    location = job_data.get('location', '')
                    experience = job_data.get('experience', '')
                    employment_type = job_data.get('employment_type', '')

                    if not title:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    # Parse location
                    city, state, _ = self.parse_location(location)

                    # Generate job ID from URL or index
                    job_id = f"delhivery_{idx}"
                    if url and 'jobDetails/' in url:
                        job_id = url.split('jobDetails/')[-1].split('?')[0]
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
                        'department': '',
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No job tiles found on Darwinbox page")

        except Exception as e:
            logger.error(f"Darwinbox extraction error: {str(e)}")

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

        # Darwinbox format: "GGN_HQ04 # (Haryana), Gurgaon, Haryana, India"
        # Extract city and state from comma-separated parts
        parts = [p.strip() for p in location_str.split(',')]

        city = ''
        state = ''
        for part in parts:
            part_clean = part.strip()
            if part_clean == 'India':
                continue
            # Skip office codes like "GGN_HQ04 # (Haryana)"
            if '#' in part_clean or '_' in part_clean:
                # Try to extract state from parentheses
                if '(' in part_clean and ')' in part_clean:
                    state = part_clean.split('(')[-1].split(')')[0].strip()
                continue
            if '..+' in part_clean:
                continue
            if not city:
                city = part_clean
            elif not state:
                state = part_clean

        return city, state, 'India'

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

logger = setup_logger('royalenfield_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class RoyalEnfieldScraper:
    def __init__(self):
        self.company_name = 'Royal Enfield'
        self.url = 'https://careers.royalenfield.com/us/en/search-results'

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
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--ignore-ssl-errors=yes')
        chrome_options.add_argument('--disable-web-security')
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
        """Scrape jobs from Royal Enfield careers page (Phenom platform)"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Retry page load up to 3 times to handle 'Max retries exceeded' errors
            page_loaded = False
            for attempt in range(3):
                try:
                    logger.info(f"Loading URL (attempt {attempt + 1}): {self.url}")
                    driver.get(self.url)
                    page_loaded = True
                    break
                except Exception as e:
                    logger.warning(f"Page load attempt {attempt + 1} failed: {str(e)}")
                    if attempt < 2:
                        time.sleep(5)
                    else:
                        raise

            # Wait for Phenom platform to load
            time.sleep(15)

            # Try to wait for Phenom job links
            try:
                short_wait = WebDriverWait(driver, 10)
                short_wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, 'a[data-ph-at-id="job-link"], a[href*="/job/"]'
                )))
            except:
                logger.warning("Timeout waiting for Phenom job links")

            # Scroll to trigger lazy-loaded content
            for scroll_i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((scroll_i + 1) / 5))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                # Scrape current page using Phenom-specific JS extraction
                page_jobs = self._scrape_page_js(driver)
                jobs.extend(page_jobs)

                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                # Try to navigate to next page
                if current_page < max_pages and page_jobs:
                    if not self._go_to_next_page(driver):
                        logger.info("No more pages available")
                        break
                    time.sleep(5)
                    # Scroll after page change
                    for scroll_i in range(3):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((scroll_i + 1) / 3))
                        time.sleep(1)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                else:
                    break

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
        """Navigate to the next page on Phenom platform"""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # Phenom uses "View more" or "Load More" buttons, or pagination
            next_clicked = driver.execute_script("""
                // Try Phenom "View more" / "Load more" button
                var buttons = document.querySelectorAll('button, a');
                for (var i = 0; i < buttons.length; i++) {
                    var text = (buttons[i].textContent || '').trim().toLowerCase();
                    if (text.includes('view more') || text.includes('load more') || text.includes('show more')) {
                        buttons[i].click();
                        return true;
                    }
                }
                // Try Phenom next page button
                var nextBtn = document.querySelector('[data-ph-at-id="pagination-next"], button[aria-label*="next"], a[aria-label*="next"]');
                if (nextBtn && !nextBtn.disabled) {
                    nextBtn.click();
                    return true;
                }
                return false;
            """)

            if next_clicked:
                logger.info("Clicked next/load more button")
                return True

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page_js(self, driver):
        """Scrape jobs using JavaScript - Phenom platform"""
        jobs = []
        time.sleep(3)

        try:
            # Phenom platform: job links have data-ph-at-id="job-link" or href containing /job/
            js_jobs = driver.execute_script("""
                var jobs = [];
                var seen = {};

                // Method 1: Phenom-specific job link attribute
                var phenomLinks = document.querySelectorAll('a[data-ph-at-id="job-link"]');
                for (var i = 0; i < phenomLinks.length; i++) {
                    var link = phenomLinks[i];
                    var title = (link.textContent || '').trim();
                    var href = link.href || '';

                    if (!title || title.length < 3 || seen[href]) continue;
                    seen[href] = true;

                    // Extract job ID from URL like /job/P-101050/Global-Marquee-rides
                    var jobId = '';
                    var match = href.match(/\\/job\\/(P-\\d+)/);
                    if (match) jobId = match[1];

                    // Get parent container for location and category
                    var container = link;
                    for (var p = 0; p < 8; p++) {
                        if (container.parentElement) {
                            container = container.parentElement;
                            if (container.tagName === 'LI' || container.getAttribute('data-ph-at-id') === 'job-listing') {
                                break;
                            }
                        }
                    }

                    var containerText = (container.innerText || '').trim();
                    var lines = containerText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                    var location = '';
                    var category = '';
                    var postedDate = '';

                    for (var j = 0; j < lines.length; j++) {
                        var line = lines[j];
                        // Match lines containing city/country names but NOT the word "Location" alone
                        if ((line.includes('India') || line.includes('Gurugram') || line.includes('Chennai') ||
                            line.includes('Mumbai') || line.includes('Bangalore') || line.includes('Pune')) &&
                            line !== 'Location' && line !== title && line.length > 5) {
                            location = line;
                        }
                        if (line.startsWith('Category')) {
                            category = lines[j+1] || '';
                        }
                        if (line.startsWith('Posted Date') || line.includes('Posted')) {
                            postedDate = lines[j+1] || line.replace('Posted Date', '').replace('Posted', '').trim();
                        }
                    }

                    // Try Phenom location attribute - clean up the text
                    var locSpan = container.querySelector('[data-ph-at-id="job-location"], span[class*="location"]');
                    if (locSpan) {
                        var locText = locSpan.textContent.trim();
                        // Remove "Location" prefix if present
                        locText = locText.replace(/^Location\\s*/i, '').trim();
                        if (locText.length > 3) location = locText;
                    }

                    jobs.push({
                        title: title,
                        url: href,
                        jobId: jobId,
                        location: location,
                        category: category,
                        postedDate: postedDate
                    });
                }

                // Method 2: If Phenom attribute not found, try generic /job/ links
                if (jobs.length === 0) {
                    var genericLinks = document.querySelectorAll('a[href*="/job/"]');
                    for (var k = 0; k < genericLinks.length; k++) {
                        var gLink = genericLinks[k];
                        var gTitle = (gLink.textContent || '').trim();
                        var gHref = gLink.href || '';

                        if (!gTitle || gTitle.length < 3 || seen[gHref]) continue;
                        // Skip navigation-type links
                        if (gTitle.toLowerCase().includes('home') || gTitle.toLowerCase().includes('search')) continue;
                        seen[gHref] = true;

                        var gJobId = '';
                        var gMatch = gHref.match(/\\/job\\/(P-\\d+)/);
                        if (gMatch) gJobId = gMatch[1];

                        jobs.push({
                            title: gTitle,
                            url: gHref,
                            jobId: gJobId,
                            location: '',
                            category: '',
                            postedDate: ''
                        });
                    }
                }

                return jobs;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                for job_data in js_jobs:
                    title = job_data.get('title', '')
                    if not title or len(title) < 3:
                        continue

                    job_id = job_data.get('jobId', '') or hashlib.md5(job_data.get('url', '').encode()).hexdigest()[:12]
                    location = job_data.get('location', '')
                    city, state, country = self.parse_location(location)

                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country or 'India',
                        'employment_type': '',
                        'department': job_data.get('category', ''),
                        'apply_url': job_data.get('url', self.url),
                        'posted_date': job_data.get('postedDate', ''),
                        'job_function': '',
                        'experience_level': '',
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
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        country = parts[2] if len(parts) > 2 else 'India'

        return city, state, country

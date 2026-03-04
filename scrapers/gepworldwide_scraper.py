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
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('gepworldwide_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class GEPWorldwideScraper:
    def __init__(self):
        self.company_name = 'GEP Worldwide'
        self.url = 'https://jobsindia-apac-gep.icims.com/jobs/search?ss=1&searchRelation=keyword_all&searchLocation=13228-13248-Airoli'
        self.base_url = 'https://jobsindia-apac-gep.icims.com'

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
        """Scrape jobs from GEP Worldwide iCIMS careers page"""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(12)

            # iCIMS may use iframes - check and switch if needed
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                logger.info(f"Found {len(iframes)} iframes")
                for iframe in iframes:
                    try:
                        src = iframe.get_attribute('src') or ''
                        iframe_id = iframe.get_attribute('id') or ''
                        if 'job' in src.lower() or 'search' in src.lower() or 'icims' in src.lower():
                            driver.switch_to.frame(iframe)
                            logger.info("Switched to iCIMS iframe")
                            time.sleep(3)
                            break
                    except:
                        continue

            # Scroll to load content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            for page in range(max_pages):
                page_jobs = self._extract_jobs(driver)
                if not page_jobs:
                    break
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if not self._go_to_next_page(driver):
                    break
                time.sleep(5)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver):
        """Extract jobs from the iCIMS page using JavaScript"""
        jobs = []

        try:
            # Scroll to ensure content is loaded
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: iCIMS row-based listings (GEP pattern)
                var rows = document.querySelectorAll('.iCIMS_JobsTable .row, .row');
                for (var i = 0; i < rows.length; i++) {
                    var row = rows[i];
                    var titleDiv = row.querySelector('.col-xs-12.title, div[class*="title"]');
                    if (!titleDiv) continue;

                    var h3 = titleDiv.querySelector('h3, h2');
                    var linkEl = titleDiv.querySelector('a.iCIMS_Anchor, a[href*="/jobs/"]');
                    if (!h3 && !linkEl) continue;

                    var title = '';
                    if (h3) {
                        title = h3.innerText.trim();
                    } else if (linkEl) {
                        // Filter out sr-only labels
                        var clone = linkEl.cloneNode(true);
                        var srOnly = clone.querySelectorAll('.sr-only');
                        srOnly.forEach(function(el) { el.remove(); });
                        title = clone.innerText.trim();
                    }
                    title = title.split('\\n')[0].trim();

                    var href = linkEl ? (linkEl.href || '') : '';
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (title === 'Title' || title === 'Location' || title === 'Date') continue;
                    if (href && seen[href]) continue;

                    // Location from iCIMS_JobHeaderTag
                    var location = '';
                    var headerTags = row.querySelectorAll('.iCIMS_JobHeaderTag');
                    var posType = '';
                    for (var j = 0; j < headerTags.length; j++) {
                        var label = headerTags[j].querySelector('dt');
                        var value = headerTags[j].querySelector('dd span');
                        if (label && value) {
                            var labelText = label.innerText.trim().toLowerCase();
                            if (labelText.includes('location')) {
                                location = value.innerText.trim();
                            } else if (labelText.includes('position type') || labelText.includes('employment')) {
                                posType = value.innerText.trim();
                            }
                        }
                    }

                    if (href) seen[href] = true;
                    results.push({title: title, url: href || '', location: location, date: '', department: '', employment_type: posType});
                }

                // Strategy 2: Generic job links from iCIMS
                if (results.length === 0) {
                    var links = document.querySelectorAll('a.iCIMS_Anchor[href*="/jobs/"]');
                    for (var i = 0; i < links.length; i++) {
                        var el = links[i];
                        var h3 = el.querySelector('h3, h2');
                        var title = '';
                        if (h3) {
                            title = h3.innerText.trim();
                        } else {
                            var clone = el.cloneNode(true);
                            var srOnly = clone.querySelectorAll('.sr-only');
                            srOnly.forEach(function(s) { s.remove(); });
                            title = clone.innerText.trim().split('\\n')[0].trim();
                        }
                        var href = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (title === 'Title' || title === 'Location' || title === 'Date') continue;
                        if (href.includes('login') || href.includes('/jobs/search') || href.includes('/jobs/intro')) continue;
                        if (seen[href]) continue;
                        seen[href] = true;
                        results.push({title: title, url: href, location: '', date: '', department: '', employment_type: ''});
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    date = jdata.get('date', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    employment_type = jdata.get('employment_type', '').strip()

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/jobs/' in url:
                        import re
                        id_match = re.search(r'/jobs/(\d+)', url)
                        if id_match:
                            job_id = id_match.group(1)

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': url or self.url,
                        'posted_date': date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                    page_url = driver.current_url
                    logger.info(f"Current URL: {page_url}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to next page in iCIMS pagination"""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # iCIMS pagination selectors
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a.iCIMS_Paging_Next'),
                (By.CSS_SELECTOR, 'a[class*="paging"][class*="next"]'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'a.next'),
                (By.CSS_SELECTOR, 'li.next a'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.XPATH, '//a[contains(@class, "Next")]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), ">")]'),
                (By.XPATH, '//a[contains(@title, "Next")]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except:
                    continue

            return False
        except:
            return False

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = GEPWorldwideScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

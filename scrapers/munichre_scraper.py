from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from pathlib import Path


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('munichre_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

INDIA_KEYWORDS = ['india', 'mumbai', 'delhi', 'bangalore', 'bengaluru', 'hyderabad',
                  'chennai', 'pune', 'kolkata', 'gurgaon', 'gurugram', 'noida',
                  'ahmedabad', 'jaipur', 'lucknow', 'chandigarh', 'kochi', 'coimbatore',
                  'thiruvananthapuram', 'indore', 'nagpur', 'vadodara', 'visakhapatnam']


class MunichReScraper:
    def __init__(self):
        self.company_name = 'Munich Re'
        self.url = 'https://careers.munichre.com/en/search-jobs'
        self.base_url = 'https://careers.munichre.com'

    def setup_driver(self):
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
            logger.warning(f"Primary driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _is_india_job(self, location):
        """Check if a job location is in India"""
        if not location:
            return False
        loc_lower = location.lower()
        return any(kw in loc_lower for kw in INDIA_KEYWORDS)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Wait for job cards to appear
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/job/"]'))
                )
            except:
                time.sleep(5)

            # Scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

            for page in range(max_pages):
                page_jobs = self._extract_jobs(driver)
                if not page_jobs:
                    break
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if page < max_pages - 1:
                    if not self._go_to_next_page(driver):
                        break

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver):
        jobs = []

        try:
            # Scroll to load content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)

            # Munich Re custom platform: div.search-results-list__details cards
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Munich Re uses div.search-results-list__details with a[href*="/job/"] links
                var cards = document.querySelectorAll('div.search-results-list__details, div.job-list-01-list__details');
                if (cards.length === 0) cards = document.querySelectorAll('a[href*="/job/"]');

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var linkEl = card.querySelector('a[href*="/job/"]');
                    if (!linkEl) {
                        if (card.tagName === 'A' && card.href && card.href.includes('/job/')) {
                            linkEl = card;
                        } else {
                            continue;
                        }
                    }
                    var href = linkEl.href;
                    if (!href || seen[href]) continue;
                    seen[href] = true;

                    var title = linkEl.innerText.trim();
                    if (!title || title.length < 3) continue;

                    // Get location from card text lines
                    var cardText = card.innerText || '';
                    var lines = cardText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                    var location = '';
                    var department = '';
                    for (var j = 0; j < lines.length; j++) {
                        var line = lines[j];
                        if (line === title) continue;
                        // Location lines typically have commas (city, country)
                        if (!location && (line.includes(',') || line.includes('India') || line.includes('Remote'))) {
                            location = line.replace(/^\\s*/, '');
                        }
                        // Department is typically the line after location
                        if (location && !department && line !== location && !line.includes(',') &&
                            line !== 'Professional' && line !== 'Internship & Working Student') {
                            department = line;
                        }
                    }

                    results.push({title: title, location: location, url: href, department: department});
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs (before India filter)")
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue

                    # India location filter
                    if not self._is_india_job(location):
                        continue

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url or self.url,
                        'location': location,
                        'department': department,
                        'employment_type': '',
                        'description': '',
                        'posted_date': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    job_data.update(self.parse_location(location))
                    jobs.append(job_data)

                logger.info(f"After India filter: {len(jobs)} jobs")

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            # Get current first card to detect page change
            old_first = driver.execute_script("""
                var card = document.querySelector('div.search-results-list__details a[href*="/job/"]');
                return card ? card.innerText.substring(0, 50) : '';
            """)

            # Munich Re pagination: a.next
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a.next:not(.disabled)'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        # Poll for page change
                        for _ in range(20):
                            time.sleep(0.2)
                            new_first = driver.execute_script("""
                                var card = document.querySelector('div.search-results-list__details a[href*="/job/"]');
                                return card ? card.innerText.substring(0, 50) : '';
                            """)
                            if new_first and new_first != old_first:
                                break
                        time.sleep(0.5)
                        return True
                except:
                    continue
            return False
        except:
            return False

    def parse_location(self, location_str):
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
    scraper = MunichReScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

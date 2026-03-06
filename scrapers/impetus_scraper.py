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

logger = setup_logger('impetus_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class ImpetusScraper:
    def __init__(self):
        self.company_name = 'Impetus Technologies'
        self.url = 'https://impetus.openings.co/'
        self.base_url = 'https://impetus.openings.co'

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
        except Exception:
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

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) >= 1 else ''
        state = parts[1] if len(parts) >= 2 else ''
        return city, state, 'India'

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Impetus Technologies on openings.co (AngularJS SPA)"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)

            # AngularJS SPA with hash routing — wait for full render
            time.sleep(15)

            # Scroll to trigger lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            # Try to click on "All Jobs" or similar tab if available
            try:
                driver.execute_script("""
                    var tabs = document.querySelectorAll('a[href*="#/jobs"], a[href*="#/openings"], a[href*="#/all"], [class*="tab"], [class*="nav-link"]');
                    for (var i = 0; i < tabs.length; i++) {
                        var text = tabs[i].innerText.toLowerCase();
                        if (text.includes('all') || text.includes('job') || text.includes('opening')) {
                            tabs[i].click();
                            break;
                        }
                    }
                """)
                time.sleep(5)
            except Exception:
                pass

            # Extract job listings from the AngularJS-rendered DOM
            for page in range(max_pages):
                page_jobs = self._extract_jobs(driver)

                if not page_jobs:
                    if page == 0:
                        logger.warning("No jobs found on initial page load")
                    break

                jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: found {len(page_jobs)} jobs (total: {len(jobs)})")

                # Try to go to next page
                if not self._go_to_next_page(driver):
                    break
                time.sleep(5)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs(self, driver):
        """Extract job listings from the current page"""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // openings.co uses AngularJS with specific DOM patterns
                // Strategy 1: openings.co specific selectors
                var cards = document.querySelectorAll('.job-listing, .job-card, .job-item, .opening-item, .job-row, [ng-repeat*="job"], [ng-repeat*="opening"], [ng-repeat*="position"]');
                if (cards.length === 0) {
                    cards = document.querySelectorAll('[class*="job"], [class*="opening"], [class*="position"], [class*="listing"]');
                }

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = card.innerText.trim();
                    if (text.length < 5 || text.length > 2000) continue;

                    var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="name"], [class*="designation"], strong, a');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title) title = text.split('\\n')[0].trim();

                    var locEl = card.querySelector('[class*="location"], [class*="city"], [class*="place"], [class*="loc"]');
                    var location = locEl ? locEl.innerText.trim() : '';
                    if (!location) {
                        var lines = text.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            var line = lines[j].trim();
                            if (line.match(/Indore|Bangalore|Bengaluru|Mumbai|Delhi|Noida|Hyderabad|Pune|Gurgaon|Gurugram|Remote/i)) {
                                location = line;
                                break;
                            }
                        }
                    }

                    var deptEl = card.querySelector('[class*="department"], [class*="dept"], [class*="team"], [class*="category"], [class*="function"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';

                    var linkEl = card.querySelector('a[href]');
                    var url = linkEl ? linkEl.href : '';

                    if (title && title.length > 2 && title.length < 200 && !seen[title + location]) {
                        seen[title + location] = true;
                        results.push({
                            title: title, location: location, department: department, url: url
                        });
                    }
                }

                // Strategy 2: Table rows (openings.co sometimes uses tables)
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var cells = rows[i].querySelectorAll('td');
                        if (cells.length < 1) continue;
                        var title = cells[0].innerText.trim();
                        if (!title || title.length < 3) continue;
                        var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                        var department = cells.length > 2 ? cells[2].innerText.trim() : '';
                        var link = rows[i].querySelector('a[href]');
                        var url = link ? link.href : '';

                        if (!seen[title + location]) {
                            seen[title + location] = true;
                            results.push({title: title, location: location, department: department, url: url});
                        }
                    }
                }

                // Strategy 3: li-based listings
                if (results.length === 0) {
                    var items = document.querySelectorAll('ul li, ol li');
                    for (var i = 0; i < items.length; i++) {
                        var li = items[i];
                        var text = li.innerText.trim();
                        if (text.length < 5 || text.length > 500) continue;

                        var titleEl = li.querySelector('a, h3, h4, strong, [class*="title"]');
                        var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : text.split('\\n')[0].trim();
                        var linkEl = li.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';

                        if (title && title.length > 2 && title.length < 200 && !seen[title]) {
                            // Filter out navigation items
                            if (!title.match(/^(Home|About|Contact|Login|Sign|Menu|Close|Privacy|Terms|FAQ)/i)) {
                                seen[title] = true;
                                results.push({title: title, location: '', department: '', url: url});
                            }
                        }
                    }
                }

                // Strategy 4: Links with job-related patterns
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href || '';
                        if (text.length > 3 && text.length < 200 && !seen[text]) {
                            if (href.includes('#/job') || href.includes('#/opening') || href.includes('#/position') || href.includes('/details') || href.includes('/view')) {
                                if (!href.includes('login') && !href.includes('javascript:')) {
                                    seen[text] = true;
                                    results.push({title: text, location: '', department: '', url: href});
                                }
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Extraction found {len(js_jobs)} jobs on current page")
                seen_urls = set()
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    url = job_data.get('url', '')

                    if not title or len(title) < 3:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    job_id = hashlib.md5(f"{title}_{location}_{idx}".encode()).hexdigest()[:12]
                    if url and '#/' in url:
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found on current page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Job extraction error: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Try to navigate to the next page"""
        try:
            result = driver.execute_script("""
                var selectors = [
                    'a[ng-click*="next"]', 'a[ng-click*="Next"]',
                    'button[ng-click*="next"]', 'button[ng-click*="Next"]',
                    '.pagination .next a', '.pagination li.next a',
                    'a[aria-label="Next"]', 'button[aria-label="Next"]',
                    'a.next-page', 'a[rel="next"]',
                    '[class*="pagination"] [class*="next"]',
                    'a:not([disabled])[href*="page"]'
                ];

                for (var i = 0; i < selectors.length; i++) {
                    var btn = document.querySelector(selectors[i]);
                    if (btn && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                }

                // Try XPath for text-based buttons
                var xpath = '//a[contains(text(), "Next")] | //button[contains(text(), "Next")] | //a[contains(text(), ">")] | //a[contains(text(), "»")]';
                var result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                if (result.singleNodeValue && result.singleNodeValue.offsetParent !== null) {
                    result.singleNodeValue.click();
                    return true;
                }

                return false;
            """)
            if result:
                logger.info("Navigated to next page")
            return result
        except Exception:
            return False


if __name__ == '__main__':
    scraper = ImpetusScraper()
    results = scraper.scrape()
    print(f"\nTotal jobs found: {len(results)}")
    for job in results[:10]:
        print(f"  - {job['title']} | {job['location']} | {job['department']} | {job['apply_url']}")

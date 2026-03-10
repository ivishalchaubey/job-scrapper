from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import re

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('eichermotors_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class EicherMotorsScraper:
    def __init__(self):
        self.company_name = "Eicher Motors"
        self.url = "https://careers.vecv.in/search/?createNewAlert=false&q=&locationsearch=&optionsFacetsDD_location=&optionsFacetsDD_city=&optionsFacetsDD_department=\nhttps://careers.royalenfield.com/us/en/home?_gl=1*y9ntof*_gcl_au*MjEyNTMxOTY3NC4xNzcxNTc2ODg5*_ga*MTUyNjI5NjQ3MC4xNzcxNTc2ODg5*_ga_7746PERT32*czE3NzE1NzY4ODkkbzEkZzEkdDE3NzE1NzY5MjAkajI5JGwwJGgw"
        self.base_url = 'https://careers.vecv.in'

    def setup_driver(self):
        """Set up Chrome with enhanced anti-detection for Cloudflare bypass."""
        chrome_options = Options()

        # Cloudflare detects standard headless mode; use non-headless if
        # HEADLESS_MODE is set, but add extra flags to reduce detection.
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')

        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--lang=en-US,en;q=0.9')
        chrome_options.add_argument(
            '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        )
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Exclude common automation indicators
        chrome_options.add_experimental_option('prefs', {
            'credentials_enable_service': False,
            'profile.password_manager_enabled': False,
        })

        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception:
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)

        # Override navigator properties to avoid detection
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "platform": "macOS",
            "acceptLanguage": "en-US,en;q=0.9",
        })

        # Patch navigator properties
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
            '''
        })

        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Eicher Motors/VECV jobs from SAP SuccessFactors behind Cloudflare.

        Strategy:
        1. Load the page and wait for Cloudflare challenge to complete
        2. Extract jobs from SuccessFactors DOM (table#searchresults, a.jobTitle-link)
        3. Paginate using startrow parameter
        """
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Wait for Cloudflare challenge to complete - this is the critical part.
            # Cloudflare JS challenge typically takes 5-10 seconds.
            logger.info("Waiting for Cloudflare challenge to complete...")

            # Poll until the Cloudflare challenge page is gone
            cloudflare_passed = False
            for attempt in range(12):
                time.sleep(5)
                try:
                    page_title = driver.title.lower()
                    current_url = driver.current_url
                    body_text = driver.execute_script(
                        'return document.body ? document.body.innerText.substring(0, 200) : ""'
                    )
                    logger.info(
                        f"Cloudflare check {attempt + 1}: title='{page_title[:50]}' "
                        f"url='{current_url[:80]}'"
                    )

                    # Check if we're past Cloudflare
                    if ('just a moment' not in page_title
                            and 'attention required' not in page_title
                            and 'cloudflare' not in page_title
                            and 'challenge' not in body_text.lower()[:100]):
                        cloudflare_passed = True
                        logger.info("Cloudflare challenge appears to be completed")
                        break
                except Exception as e:
                    logger.debug(f"Error checking page state: {str(e)}")

            if not cloudflare_passed:
                logger.warning(
                    "Cloudflare challenge may not have completed. "
                    "Attempting extraction anyway."
                )

            # Additional wait for SuccessFactors to load
            time.sleep(5)

            # Scroll to trigger content loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Check for iframes (SuccessFactors sometimes uses them)
            try:
                iframes = driver.find_elements(By.TAG_NAME, 'iframe')
                for iframe in iframes:
                    src = iframe.get_attribute('src') or ''
                    iframe_id = iframe.get_attribute('id') or ''
                    if any(k in src.lower() for k in ['career', 'job', 'search']):
                        logger.info(f"Switching to iframe: id={iframe_id} src={src[:80]}")
                        driver.switch_to.frame(iframe)
                        time.sleep(5)
                        break
            except Exception as e:
                logger.warning(f"Iframe check failed: {str(e)}")

            # Wait for SuccessFactors search results
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'table#searchresults, a.jobTitle-link, span.jobTitle, '
                        'tr.data-row, table.searchResults, a[href*="/job/"]'
                    ))
                )
                logger.info("SuccessFactors job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for SF results: {str(e)}")

            scraped_ids = set()
            current_page = 1
            consecutive_empty = 0

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                page_jobs = self._extract_jobs(driver, scraped_ids)
                all_jobs.extend(page_jobs)
                logger.info(
                    f"Page {current_page}: found {len(page_jobs)} new jobs "
                    f"(total: {len(all_jobs)})"
                )

                if len(page_jobs) == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        logger.info("No new jobs on 2 consecutive pages, stopping")
                        break
                else:
                    consecutive_empty = 0

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        break
                    time.sleep(5)

                current_page += 1

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _extract_jobs(self, driver, scraped_ids):
        """Extract jobs from SuccessFactors table using JS."""
        jobs = []

        try:
            # Scroll to load content
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: SuccessFactors standard - a.jobTitle-link
                var titleLinks = document.querySelectorAll(
                    'a.jobTitle-link, span.jobTitle a, a[href*="/job/"]'
                );

                if (titleLinks.length > 0) {
                    for (var i = 0; i < titleLinks.length; i++) {
                        var link = titleLinks[i];
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || link.getAttribute('href') || '';
                        if (!title || !href) continue;
                        if (seen[href]) continue;
                        seen[href] = true;

                        var row = link.closest('tr, div.data-row, li');
                        var location = '', department = '', postedDate = '';
                        if (row) {
                            var locElem = row.querySelector(
                                'span.jobLocation, .jobLocation, [class*="location"]'
                            );
                            if (locElem) location = locElem.innerText.trim();
                            var dateElem = row.querySelector(
                                'span.jobDate, .jobDate, [class*="date"]'
                            );
                            if (dateElem) postedDate = dateElem.innerText.trim();
                            var deptElem = row.querySelector(
                                'span.jobDepartment, .jobDepartment, [class*="department"]'
                            );
                            if (deptElem) department = deptElem.innerText.trim();
                        }
                        results.push({
                            title: title, url: href, location: location,
                            department: department, postedDate: postedDate
                        });
                    }
                }

                // Strategy 2: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll(
                        'table#searchresults tr, table.searchResults tr, tr.data-row'
                    );
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        if (row.querySelector('th')) continue;
                        var titleEl = row.querySelector(
                            'a.jobTitle-link, a[href*="/job/"], a[href*="jobDetail"], td a'
                        );
                        if (!titleEl) continue;
                        var title = titleEl.innerText.trim().split('\\n')[0].trim();
                        var href = titleEl.href || '';
                        if (!title || title.length < 3 || (href && seen[href])) continue;
                        if (href) seen[href] = true;

                        var locEl = row.querySelector(
                            'span.jobLocation, td.colLocation, td[class*="location"]'
                        );
                        if (!locEl) {
                            var tds = row.querySelectorAll('td');
                            if (tds.length >= 2) locEl = tds[1];
                        }
                        var loc = locEl ? locEl.innerText.trim() : '';
                        results.push({
                            title: title, url: href || '', location: loc,
                            department: '', postedDate: ''
                        });
                    }
                }

                // Strategy 3: Div-based cards
                if (results.length === 0) {
                    var cards = document.querySelectorAll(
                        'div[class*="job-card"], div[class*="job-result"], ' +
                        'div[class*="jobResult"], li[class*="job"]'
                    );
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var linkEl = card.querySelector('a[href]');
                        if (!linkEl) continue;
                        var title = linkEl.innerText.trim().split('\\n')[0];
                        var href = linkEl.href;
                        if (!title || title.length < 3 || (href && seen[href])) continue;
                        if (href) seen[href] = true;
                        var locEl = card.querySelector('[class*="location"]');
                        results.push({
                            title: title, url: href || '', location: locEl ? locEl.innerText.trim() : '',
                            department: '', postedDate: ''
                        });
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    posted_date = jdata.get('postedDate', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Extract job ID from URL
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url:
                        req_match = re.search(r'job_req_id=(\d+)', url)
                        if req_match:
                            job_id = req_match.group(1)
                        elif '/job/' in url:
                            parts = url.split('/job/')[-1].split('/')
                            if parts[0]:
                                job_id = parts[0].split('?')[0]
                        # Also try numeric IDs at end of URL
                        num_match = re.search(r'/(\d{6,})/?', url)
                        if num_match:
                            job_id = num_match.group(1)

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'employment_type': '',
                        'department': department,
                        'apply_url': url or self.url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                    scraped_ids.add(ext_id)
                    logger.info(f"Extracted: {title} | {location}")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script(
                        'return document.body ? document.body.innerText.substring(0, 500) : ""'
                    )
                    logger.info(f"Page body preview: {body_text[:200]}")
                    page_url = driver.current_url
                    logger.info(f"Current URL: {page_url}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page using SuccessFactors pagination."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Strategy 1: Standard SF pagination selectors
            next_selectors = [
                (By.CSS_SELECTOR, 'a.paginationItemLast'),
                (By.CSS_SELECTOR, 'a.next'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.XPATH, '//a[contains(@class,"paginationItemLast")]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, f'a[title="Page {current_page + 1}"]'),
            ]

            for sel_type, sel_val in next_selectors:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if not btn.is_displayed() or not btn.is_enabled():
                        continue
                    btn_class = btn.get_attribute('class') or ''
                    if 'disabled' in btn_class:
                        continue
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", btn
                    )
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info(f"Navigated to page {current_page + 1}")
                    return True
                except Exception:
                    continue

            # Strategy 2: URL-based pagination with startrow parameter
            try:
                current_url = driver.current_url
                results_per_page = 25
                new_startrow = current_page * results_per_page

                if 'startrow=' in current_url:
                    new_url = re.sub(
                        r'startrow=\d+', f'startrow={new_startrow}', current_url
                    )
                else:
                    separator = '&' if '?' in current_url else '?'
                    new_url = f"{current_url}{separator}startrow={new_startrow}"

                logger.info(f"Navigating via URL: startrow={new_startrow}")
                driver.get(new_url)
                time.sleep(8)

                new_body = driver.execute_script(
                    'return document.body ? document.body.innerText.substring(0, 200) : ""'
                )
                if 'no results' in new_body.lower() or 'no jobs' in new_body.lower():
                    logger.info("No more results at this startrow")
                    return False

                return True
            except Exception as e:
                logger.warning(f"URL-based pagination failed: {str(e)}")

            logger.warning("Could not find next page button")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
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
            if parts[1] in ['IN', 'IND', 'India']:
                result['country'] = 'India'
            else:
                result['state'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = EicherMotorsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

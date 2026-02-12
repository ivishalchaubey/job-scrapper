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

logger = setup_logger('continental_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class ContinentalScraper:
    def __init__(self):
        self.company_name = 'Continental'
        self.url = 'https://jobs.continental.com/en/#/?location=%7B%22title%22:%22India%22,%22type%22:%22country%22,%22countryCode%22:%22in%22%7D'
        self.base_url = 'https://jobs.continental.com'

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
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Auto-detect failed: {str(e)}, trying explicit path")
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(12)

            # Click the Search button to trigger results loading
            try:
                clicked = driver.execute_script("""
                    var searchBtn = null;
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var txt = buttons[i].innerText.trim().toLowerCase();
                        if (txt.includes('search') || txt.includes('suche')) {
                            searchBtn = buttons[i];
                            break;
                        }
                    }
                    if (!searchBtn) {
                        searchBtn = document.querySelector('button[type="submit"]');
                    }
                    if (searchBtn) {
                        searchBtn.click();
                        return true;
                    }
                    return false;
                """)
                if clicked:
                    logger.info("Clicked Search button, waiting for results...")
                    time.sleep(10)
            except Exception as e:
                logger.warning(f"Could not click search button: {e}")

            # Scroll to trigger lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

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
        jobs = []

        try:
            # Brief scroll to ensure content is loaded
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 0: Continental-specific selectors
                // Job rows use class 'c-jobs-list__row has-shadow' (header row has 'is-header')
                // Columns by index: 0=title, 1=location, 2=flexibility, 3=field, 4=date
                var jobRows = document.querySelectorAll('.c-jobs-list__row.has-shadow');
                if (jobRows.length > 0) {
                    for (var i = 0; i < jobRows.length; i++) {
                        var row = jobRows[i];
                        var linkEl = row.querySelector('a.c-jobs-list__link');
                        if (!linkEl) continue;
                        var href = linkEl.href || '';
                        if (!href || seen[href]) continue;
                        // Title is in the first span.d-block inside the link
                        var titleSpan = linkEl.querySelector('span.d-block');
                        var title = titleSpan ? titleSpan.innerText.trim() : linkEl.innerText.trim().split('\\n')[0];
                        if (!title || title.length < 3) continue;
                        // Get all columns (title col has 'is-title', others are generic)
                        var cols = row.querySelectorAll('.c-jobs-list__col');
                        var location = cols.length > 1 ? cols[1].innerText.trim() : '';
                        var flexibility = cols.length > 2 ? cols[2].innerText.trim() : '';
                        var fieldOfWork = cols.length > 3 ? cols[3].innerText.trim() : '';
                        var date = cols.length > 4 ? cols[4].innerText.trim() : '';
                        // Clean up field of work (dash means empty)
                        if (fieldOfWork === '-') fieldOfWork = '';
                        seen[href] = true;
                        results.push({title: title, location: location, url: href, date: date, flexibility: flexibility, department: fieldOfWork});
                    }
                }

                // Strategy 1: Continental detail-page links (fallback if rows not found)
                if (results.length === 0) {
                    var detailLinks = document.querySelectorAll('a[href*="detail-page/job-detail"]');
                    for (var i = 0; i < detailLinks.length; i++) {
                        var el = detailLinks[i];
                        var href = el.href || '';
                        if (!href || seen[href]) continue;
                        var titleSpan = el.querySelector('span.d-block');
                        var title = titleSpan ? titleSpan.innerText.trim() : el.innerText.trim().split('\\n')[0];
                        if (!title || title.length < 3 || title.length > 200) continue;
                        // Skip nav links
                        if (title.toLowerCase() === 'job subscription' || title.toLowerCase() === 'career website') continue;
                        seen[href] = true;
                        var location = '';
                        var parent = el.closest('.c-jobs-list__row, div[class*="jobs-list"]');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="is-location"], [class*="location"]');
                            if (locEl) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: href, location: location, date: '', flexibility: ''});
                    }
                }

                // Strategy 2: Generic fallback - all links containing detail-page
                if (results.length === 0) {
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var href = link.href || '';
                        var text = (link.innerText || '').trim();
                        if (text.length > 5 && text.length < 200 && href.includes('detail-page/job-detail')) {
                            if (!seen[href]) {
                                seen[href] = true;
                                var title = text.split('\\n')[0].trim();
                                // Filter out known navigation text
                                var lower = title.toLowerCase();
                                if (lower === 'job subscription' || lower === 'career website' ||
                                    lower === 'subscribe to job alert' || lower === 'jobs') return;
                                results.push({title: title, url: href, location: '', date: '', flexibility: ''});
                            }
                        }
                    });
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
                    flexibility = jdata.get('flexibility', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue
                    # Filter out navigation links that aren't real job titles
                    title_lower = title.lower()
                    if title_lower in ['job subscription', 'career website', 'subscribe to job alert',
                                       'jobs', 'all jobs at a glance', 'contact us']:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Extract REF job ID from Continental URLs
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/job-detail/' in url:
                        # URL pattern: /job-detail/REF93800M-p-.../
                        parts = url.split('/job-detail/')[-1].split('/')
                        if parts[0]:
                            ref_id = parts[0].split('-p-')[0]  # Get just the REF ID
                            if ref_id:
                                job_id = ref_id
                    elif url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    # Determine remote type from flexibility
                    remote_type = ''
                    if flexibility:
                        flex_lower = flexibility.lower()
                        if 'remote' in flex_lower:
                            remote_type = 'Remote'
                        elif 'hybrid' in flex_lower:
                            remote_type = 'Hybrid'
                        elif 'onsite' in flex_lower or 'on-site' in flex_lower:
                            remote_type = 'On-site'

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': department, 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': remote_type, 'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except: pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Continental uses c-pagination__item--next for the next page button
            clicked = driver.execute_script("""
                // Try Continental-specific pagination first
                var nextItem = document.querySelector('li.c-pagination__item--next, li[class*="pagination__item--next"]');
                if (nextItem) {
                    var link = nextItem.querySelector('a, button');
                    if (link) {
                        link.click();
                        return true;
                    }
                    nextItem.click();
                    return true;
                }
                return false;
            """)
            if clicked:
                logger.info("Navigated to next page via Continental pagination")
                time.sleep(8)
                # Scroll to load lazy content on new page
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                return True

            # Fallback: generic pagination selectors
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
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
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str: return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1: result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str: result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = ContinentalScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
                print(f"- {job['title']} | {job['location']}")

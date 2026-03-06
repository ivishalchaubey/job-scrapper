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

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

logger = setup_logger('gallagher_scraper')


class GallagherScraper:
    def __init__(self):
        self.company_name = 'Gallagher'
        # Jibe (iCIMS) AngularJS SPA
        self.url = 'https://jobs.ajg.com/ajg-global/jobs?locations=Bangalore,Karnataka,India'
        self.base_url = 'https://jobs.ajg.com'

    def setup_driver(self):
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception:
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

            # Wait for Jibe/iCIMS AngularJS SPA to render job listings
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'a[class*="job-title"], div[class*="job-card"], jibe-job-card, [class*="jibe-search-result"]'
                    ))
                )
                logger.info("Jibe job listings detected")
            except Exception:
                logger.warning("Timeout waiting for Jibe render, using fallback wait")
                time.sleep(15)

            # Scroll to trigger lazy-loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            scraped_ids = set()

            for page in range(max_pages):
                page_jobs = self._extract_jobs(driver, scraped_ids)
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

    def _extract_jobs(self, driver, scraped_ids):
        jobs = []

        try:
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Jibe job cards (AngularJS components)
                var cards = document.querySelectorAll('jibe-job-card, div[class*="jibe-search-result"], div[class*="job-card"], div[class*="search-result-card"]');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var linkEl = card.querySelector('a[class*="job-title"], a[href*="/jobs/"], a[href*="/job/"]');
                    if (!linkEl) linkEl = card.querySelector('a[href]');
                    if (!linkEl) continue;

                    var href = linkEl.href;
                    if (!href || seen[href] || href.includes('#') || href.includes('login')) continue;
                    seen[href] = true;

                    var title = '';
                    var titleEl = card.querySelector('[class*="job-title"], h2, h3, h4');
                    if (titleEl) title = titleEl.innerText.trim().split('\\n')[0];
                    if (!title) title = linkEl.innerText.trim().split('\\n')[0];
                    if (!title || title.length < 3 || title.length > 200) continue;

                    var locEl = card.querySelector('[class*="job-location"], [class*="location"], [class*="Location"]');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var dateEl = card.querySelector('[class*="date"], [class*="posted"]');
                    var date = dateEl ? dateEl.innerText.trim() : '';

                    var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';

                    results.push({title: title, url: href, location: location, department: department, date: date});
                }

                // Strategy 2: Direct job links (fallback for Jibe)
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="/jobs/"], a[href*="/job/"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var a = jobLinks[i];
                        var href = a.href;
                        if (!href || seen[href] || href.includes('#') || href.includes('login')) continue;
                        // Skip pagination/filter links
                        if (href.includes('?page=') && !href.includes('/jobs/')) continue;
                        if (href.match(/\\/jobs\\/?$/)) continue;
                        if (href.match(/\\/jobs\\?/)) continue;
                        seen[href] = true;

                        var text = (a.innerText || '').trim().split('\\n')[0].trim();
                        if (!text || text.length < 3 || text.length > 200) continue;
                        if (/^(Home|About|Search|Sign|Log|Back|Next|Prev|View All|Filter)/i.test(text)) continue;

                        var location = '';
                        var parent = a.closest('li, div[class*="job"], div[class*="card"], article, tr');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl && locEl !== a) location = locEl.innerText.trim();
                        }
                        results.push({title: text, url: href, location: location, department: '', date: ''});
                    }
                }

                // Strategy 3: Generic link-based fallback
                if (results.length === 0) {
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var href = link.href || '';
                        var text = (link.innerText || '').trim();
                        if (text.length > 5 && text.length < 200 && !seen[href]) {
                            var lhref = href.toLowerCase();
                            if ((lhref.includes('/job') || lhref.includes('/position') || lhref.includes('/career')) && !lhref.includes('login') && !lhref.includes('#')) {
                                seen[href] = true;
                                results.push({title: text.split('\\n')[0].trim(), url: href, location: '', department: '', date: ''});
                            }
                        }
                    });
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
                    date = jdata.get('date', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Extract job ID from URL
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if '/jobs/' in url or '/job/' in url:
                        path_part = url.split('/jobs/')[-1] if '/jobs/' in url else url.split('/job/')[-1]
                        slug = path_part.split('?')[0].split('#')[0].rstrip('/')
                        if slug:
                            job_id = slug

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    # Filter for India-based jobs
                    if location and 'india' not in location.lower() and not any(
                        city in location for city in [
                            'Mumbai', 'Bengaluru', 'Bangalore', 'Hyderabad', 'Delhi',
                            'Chennai', 'Pune', 'Kolkata', 'Gurgaon', 'Gurugram', 'Noida',
                            'Karnataka', 'Maharashtra', 'Telangana'
                        ]
                    ):
                        continue

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': department, 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': department, 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })
                    scraped_ids.add(ext_id)

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            old_first = driver.execute_script("""
                var card = document.querySelector('a[class*="job-title"], jibe-job-card a, a[href*="/jobs/"]');
                return card ? card.innerText.substring(0, 50) : '';
            """)

            # Jibe uses AngularJS pagination -- look for next page button
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '[class*="pagination"] [class*="next"] a'),
                (By.CSS_SELECTOR, '[class*="pagination"] [class*="next"] button'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                # Jibe specific: "Show more" or "Load more"
                (By.XPATH, '//button[contains(text(), "Show more")]'),
                (By.XPATH, '//button[contains(text(), "Load more")]'),
                (By.CSS_SELECTOR, 'button[class*="load-more"]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", btn)

                        # Poll for page change
                        for _ in range(25):
                            time.sleep(0.2)
                            new_first = driver.execute_script("""
                                var card = document.querySelector('a[class*="job-title"], jibe-job-card a, a[href*="/jobs/"]');
                                return card ? card.innerText.substring(0, 50) : '';
                            """)
                            if new_first and new_first != old_first:
                                break
                        time.sleep(0.5)
                        logger.info("Navigated to next page")
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
    scraper = GallagherScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

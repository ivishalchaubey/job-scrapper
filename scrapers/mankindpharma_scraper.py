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

logger = setup_logger('mankindpharma_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class MankindPharmaScraper:
    def __init__(self):
        self.company_name = 'Mankind Pharma'
        self.url = 'https://careers.mankindpharma.com/'
        self.base_url = 'https://careers.mankindpharma.com'
        # Direct search URL that shows all jobs
        self.search_url = 'https://careers.mankindpharma.com/search/?createNewAlert=false&q=&locationsearch=&optionsFacetsDD_title=&optionsFacetsDD_city=&optionsFacetsDD_department='

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
            logger.info(f"Starting {self.company_name} scraping from {self.search_url}")

            # Go directly to search results page
            driver.get(self.search_url)

            # Wait for SuccessFactors search results to load
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'tr.data-row, a.jobTitle-link, [class*="searchResult"]'))
                )
            except:
                time.sleep(5)

            # Accept cookies if present
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button, a, div[role="button"]');
                    for (var i = 0; i < btns.length; i++) {
                        var txt = (btns[i].innerText || '').toLowerCase().trim();
                        if (txt === 'accept' || txt.includes('accept')) {
                            btns[i].click();
                            break;
                        }
                    }
                """)
                time.sleep(1)
            except:
                pass

            # Quick scroll
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
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: SuccessFactors table rows (tr.data-row with a.jobTitle-link)
                var rows = document.querySelectorAll('tr.data-row');
                for (var i = 0; i < rows.length; i++) {
                    var row = rows[i];
                    var titleLink = row.querySelector('a.jobTitle-link, a[class*="jobTitle"]');
                    if (!titleLink) continue;
                    var title = titleLink.innerText.trim();
                    var href = titleLink.href || '';
                    if (!title || title.length < 3 || !href || seen[href]) continue;
                    seen[href] = true;

                    var locEl = row.querySelector('[class*="location"], td:nth-child(2)');
                    var location = locEl ? locEl.innerText.trim() : '';
                    var deptEl = row.querySelector('[class*="department"], [class*="category"]');
                    var dept = deptEl ? deptEl.innerText.trim() : '';

                    results.push({title: title, url: href, location: location, department: dept});
                }

                // Strategy 2: Any job links on SuccessFactors pages
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="/job/"], a[href*="jobDetail"], a.jobTitle-link');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var el = jobLinks[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var url = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (url.includes('login') || url.includes('javascript:')) continue;
                        if (seen[url]) continue;
                        seen[url] = true;
                        var parent = el.closest('tr, li, div[class*="job"], article');
                        var location = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"]');
                            if (locEl) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: url, location: location, department: ''});
                    }
                }

                // Strategy 3: Card-based or list-based job items (exclude nav/UI elements)
                if (results.length === 0) {
                    var cards = document.querySelectorAll('[class*="job-card"], [class*="jobCard"], [class*="job-item"], [class*="searchResult"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var link = card.querySelector('a[href]');
                        if (!link) continue;
                        var titleEl = card.querySelector('h2, h3, h4, [class*="title"]');
                        var title = titleEl ? titleEl.innerText.trim() : link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (!title || title.length < 3 || !href || seen[href]) continue;
                        // Skip non-job elements (language selectors, nav items, etc.)
                        var skipWords = ['language', 'view profile', 'english', 'home', 'privacy', 'disclaimer', 'contact', 'sign in', 'log in'];
                        var titleLower = title.toLowerCase();
                        var skip = false;
                        for (var j = 0; j < skipWords.length; j++) {
                            if (titleLower === skipWords[j] || titleLower.indexOf(skipWords[j]) === 0) { skip = true; break; }
                        }
                        if (skip) continue;
                        seen[href] = true;
                        var locEl = card.querySelector('[class*="location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        results.push({title: title, url: href, location: location, department: ''});
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
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url or self.url,
                        'location': location,
                        'department': department,
                        'employment_type': '',
                        'description': '',
                        'posted_date': '',
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found - Mankind Pharma may have no open positions currently")

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            old_first = driver.execute_script("""
                var link = document.querySelector('a.jobTitle-link, tr.data-row a');
                return link ? link.innerText.substring(0, 50) : '';
            """)

            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        for _ in range(20):
                            time.sleep(0.2)
                            new_first = driver.execute_script("""
                                var link = document.querySelector('a.jobTitle-link, tr.data-row a');
                                return link ? link.innerText.substring(0, 50) : '';
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
    scraper = MankindPharmaScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

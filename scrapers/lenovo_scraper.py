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

logger = setup_logger('lenovo_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class LenovoScraper:
    def __init__(self):
        self.company_name = 'Lenovo'
        self.url = 'https://jobs.lenovo.com/en_US/careers/SearchJobs/'
        self.base_url = 'https://jobs.lenovo.com'

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
            time.sleep(15)

            # Dismiss cookie consent banner if present
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button, a');
                    for (var i = 0; i < btns.length; i++) {
                        var t = btns[i].innerText.trim();
                        if (t === 'Accept All' || t === 'Accept all' || t === 'ACCEPT ALL') {
                            btns[i].click();
                            break;
                        }
                    }
                """)
                time.sleep(3)
                logger.info("Dismissed cookie consent banner")
            except:
                pass

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

                // Strategy 1: SuccessFactors article cards (modern variant)
                var articles = document.querySelectorAll('article.article--result');
                for (var i = 0; i < articles.length; i++) {
                    var art = articles[i];
                    var titleLink = art.querySelector('h3 a, a.article__header__focusable, a.link');
                    if (!titleLink) continue;
                    var title = titleLink.innerText.trim();
                    var url = titleLink.href || '';
                    if (!title || title.length < 3 || seen[url]) continue;
                    seen[url] = true;
                    var subtitle = art.querySelector('.article__header__text__subtitle');
                    var location = '';
                    var date = '';
                    if (subtitle) {
                        var subText = subtitle.innerText.trim();
                        var lines = subText.split('\\n');
                        if (lines.length > 0) location = lines[0].trim();
                        for (var j = 0; j < lines.length; j++) {
                            if (lines[j].includes('Posted')) {
                                date = lines[j].replace('Posted', '').trim();
                            }
                        }
                    }
                    results.push({title: title, url: url, location: location, date: date});
                }

                // Strategy 2: SuccessFactors table rows (classic)
                if (results.length === 0) {
                    var rows = document.querySelectorAll('tr.data-row');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        var titleLink = row.querySelector('a.jobTitle-link, a[href*="/job/"]');
                        if (!titleLink) continue;
                        var title = titleLink.innerText.trim();
                        var url = titleLink.href || '';
                        if (!title || title.length < 3 || seen[url]) continue;
                        seen[url] = true;
                        var locTd = row.querySelector('td.colLocation, [class*="location"], [class*="Location"]');
                        var location = locTd ? locTd.innerText.trim() : '';
                        results.push({title: title, url: url, location: location, date: ''});
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

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': '', 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
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

            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a.paginationNextLink'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-show-next'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
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
    scraper = LenovoScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
                print(f"- {job['title']} | {job['location']}")

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

logger = setup_logger('cbre_scraper')


class CBREScraper:
    def __init__(self):
        self.company_name = "CBRE Group"
        # Avature SPA -- field 9577=17142 is India filter
        self.url = "https://careers.cbre.com/en_US/careers/SearchJobs/?9577=%5B17142%5D&9577_format=10224&listFilterMode=1&jobSort=relevancy&jobRecordsPerPage=25&"
        self.base_url = 'https://careers.cbre.com'

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

            # Wait for Avature SPA to render job listings
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'article.article--result, a[href*="JobDetail"], li.sort__item--job, div[class*="search-result"]'
                    ))
                )
                logger.info("Job listings detected")
            except Exception:
                logger.warning("Timeout waiting for job listings, using fallback wait")
                time.sleep(15)

            # Scroll to trigger lazy-loading
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

                // Strategy 1: Avature article cards (modern variant -- same as L'Oreal/Siemens)
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
                    var locText = '';
                    if (subtitle) {
                        var parts = subtitle.innerText.trim().split('\\u2022');
                        if (parts.length > 0) locText = parts[0].trim();
                    }
                    results.push({title: title, url: url, location: locText, date: ''});
                }

                // Strategy 2: Avature sort list items (li.sort__item--job)
                if (results.length === 0) {
                    var sortItems = document.querySelectorAll('li.sort__item--job, li.sort__item');
                    for (var i = 0; i < sortItems.length; i++) {
                        var item = sortItems[i];
                        var linkEl = item.querySelector('a.link.link_result, a[href*="JobDetail"], a[href*="/job/"]');
                        if (!linkEl) continue;
                        var title = linkEl.innerText.trim().split('\\n')[0];
                        var url = linkEl.href || '';
                        if (!title || title.length < 3 || seen[url]) continue;
                        seen[url] = true;

                        var locEl = item.querySelector('[class*="location"], span[class*="loc"]');
                        var location = locEl ? locEl.innerText.trim() : '';

                        results.push({title: title, url: url, location: location, date: ''});
                    }
                }

                // Strategy 3: JobDetail links (Avature uses /JobDetail/ URLs)
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="JobDetail"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var a = jobLinks[i];
                        var href = a.href;
                        if (!href || seen[href]) continue;
                        seen[href] = true;
                        var text = (a.innerText || '').trim().split('\\n')[0].trim();
                        if (!text || text.length < 3 || text.length > 200) continue;
                        if (/^(View|Apply|Save|Share|Sign|Log)/i.test(text)) continue;

                        var location = '';
                        var parent = a.closest('article, li, div[class*="job"], div[class*="result"]');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl && locEl !== a) location = locEl.innerText.trim();
                        }
                        results.push({title: text, url: href, location: location, date: ''});
                    }
                }

                // Strategy 4: Generic fallback
                if (results.length === 0) {
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var href = link.href || '';
                        var text = (link.innerText || '').trim();
                        if (text.length > 5 && text.length < 200 && !seen[href]) {
                            var lhref = href.toLowerCase();
                            if ((lhref.includes('/job') || lhref.includes('/position') || lhref.includes('/career')) && !lhref.includes('login') && !lhref.includes('#')) {
                                seen[href] = true;
                                results.push({title: text.split('\\n')[0].trim(), url: href, location: '', date: ''});
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

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Extract job ID from URL
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if 'JobDetail' in url:
                        parts = url.split('/')
                        job_id = parts[-1].split('?')[0] if parts[-1] else parts[-2]
                    elif '/job/' in url:
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
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Avature uses "View more results" or pagination next links
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, "a[class*='viewMoreResults']"),
                (By.XPATH, "//a[contains(text(), 'View more')]"),
                (By.XPATH, "//button[contains(text(), 'View more')]"),
                (By.CSS_SELECTOR, 'a.paginationNextLink'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-show-next'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
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
    scraper = CBREScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

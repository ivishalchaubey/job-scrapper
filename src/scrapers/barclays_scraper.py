from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('barclays_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class BarclaysScraper:
    def __init__(self):
        self.company_name = 'Barclays'
        self.url = 'https://search.jobs.barclays/search-jobs/India/13015/2/1269750/22/79/50/2'

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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(15)

            # Scroll for lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            for page in range(max_pages):
                jobs = self._extract_jobs(driver)
                if not jobs:
                    break
                all_jobs.extend(jobs)
                logger.info(f"Page {page + 1}: {len(jobs)} jobs (total: {len(all_jobs)})")

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
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            # JavaScript extraction with NAS/Radancy platform selectors
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: NAS/Radancy platform - li[data-job-id] elements
                var jobItems = document.querySelectorAll('li[data-job-id]');
                for (var i = 0; i < jobItems.length; i++) {
                    var item = jobItems[i];
                    var jobId = item.getAttribute('data-job-id') || '';
                    var titleEl = item.querySelector('a.job-result-title, h2 a, h3 a, [class*="title"] a, a[href*="/job/"]');
                    if (!titleEl) continue;
                    var title = titleEl.innerText.trim();
                    var url = titleEl.href || '';
                    if (!title || title.length < 3 || seen[url || title]) continue;
                    seen[url || title] = true;
                    var location = '';
                    var locEl = item.querySelector('.job-result-location, [class*="location"], [class*="Location"]');
                    if (locEl) location = locEl.innerText.trim();
                    var date = '';
                    var dateEl = item.querySelector('.job-result-date, [class*="date"], [class*="Date"]');
                    if (dateEl) date = dateEl.innerText.trim();
                    results.push({title: title, url: url, location: location, date: date, jobId: jobId});
                }

                // Strategy 2: NAS search results section
                if (results.length === 0) {
                    var resultSection = document.querySelector('#search-results-list, [id*="search-results"], [class*="search-results"]');
                    if (resultSection) {
                        var items = resultSection.querySelectorAll('li, article, [class*="job-result"]');
                        for (var i = 0; i < items.length; i++) {
                            var item = items[i];
                            var link = item.querySelector('a[href]');
                            if (!link) continue;
                            var title = '';
                            var titleEl = item.querySelector('h2, h3, h4, [class*="title"], a.job-result-title');
                            if (titleEl) title = titleEl.innerText.trim().split('\\n')[0];
                            if (!title) title = link.innerText.trim().split('\\n')[0];
                            var url = link.href || '';
                            if (!title || title.length < 3 || !url || seen[url]) continue;
                            seen[url] = true;
                            var location = '';
                            var locEl = item.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl) location = locEl.innerText.trim();
                            results.push({title: title, url: url, location: location, date: '', jobId: ''});
                        }
                    }
                }

                // Strategy 3: Direct job links
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/job/"], a[href*="/search-jobs/"]');
                    for (var i = 0; i < links.length; i++) {
                        var el = links[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var url = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (url.includes('login') || url.includes('sign-in') || url.includes('javascript:')) continue;
                        // Skip navigation links (search-jobs without job ID)
                        if (url.match(/search-jobs\\/[^/]+\\/\\d+/) && !url.match(/\\/job\\//)) continue;
                        if (seen[url]) continue;
                        seen[url] = true;
                        var location = '';
                        var parent = el.closest('li, div[class*="job"], article');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: url, location: location, date: '', jobId: ''});
                    }
                }

                // Strategy 4: Generic link extraction
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var href = allLinks[i].href || '';
                        var text = (allLinks[i].innerText || '').trim();
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            if ((href.includes('/job') || href.includes('/position') || href.includes('/career') || href.includes('/opening')) && !seen[href]) {
                                if (!href.includes('login') && !href.includes('sign-in') && !href.includes('javascript:')) {
                                    seen[href] = true;
                                    results.push({title: text.split('\\n')[0].trim(), url: href, location: '', date: '', jobId: ''});
                                }
                            }
                        }
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
                    nas_job_id = jdata.get('jobId', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    if url and url.startswith('/'):
                        url = f"https://search.jobs.barclays{url}"

                    job_id = nas_job_id or hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    loc_data = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url or self.url,
                        'location': location,
                        'department': '',
                        'employment_type': '',
                        'description': '',
                        'posted_date': date,
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
                logger.warning("No jobs found on this page")

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.CSS_SELECTOR, '.pagination-paging a.next'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] a[class*="next"]'),
                (By.CSS_SELECTOR, 'a.pagination-next-link'),
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
    scraper = BarclaysScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

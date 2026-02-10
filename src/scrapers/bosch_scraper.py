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

logger = setup_logger('bosch_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class BoschScraper:
    def __init__(self):
        self.company_name = 'Bosch'
        self.url = 'https://careers.smartrecruiters.com/BoschGroup/india'

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

            # Scroll extensively for SmartRecruiters infinite scroll
            for _ in range(8):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
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

            # JavaScript extraction with SmartRecruiters platform selectors
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: SmartRecruiters standard selectors
                var openings = document.querySelectorAll('li.opening-job, li[class*="opening"], section.opening-job');
                for (var i = 0; i < openings.length; i++) {
                    var item = openings[i];
                    var titleEl = item.querySelector('a.link--block, a[class*="link"], h4 a, h3 a, a[href*="/BoschGroup/"]');
                    if (!titleEl) titleEl = item.querySelector('a[href]');
                    if (!titleEl) continue;
                    var title = '';
                    var tEl = item.querySelector('.job-title, h4, h3, [class*="title"]');
                    if (tEl) title = tEl.innerText.trim().split('\\n')[0];
                    if (!title) title = titleEl.innerText.trim().split('\\n')[0];
                    var url = titleEl.href || '';
                    if (!title || title.length < 3 || seen[url || title]) continue;
                    seen[url || title] = true;
                    var location = '';
                    var locEl = item.querySelector('.job-location, [class*="location"], [class*="Location"]');
                    if (locEl) location = locEl.innerText.trim();
                    var department = '';
                    var deptEl = item.querySelector('.department, [class*="department"], [class*="Department"]');
                    if (deptEl) department = deptEl.innerText.trim();
                    results.push({title: title, url: url, location: location, department: department});
                }

                // Strategy 2: SmartRecruiters job list with various class patterns
                if (results.length === 0) {
                    var items = document.querySelectorAll('[class*="opening"], [class*="job-item"], [class*="job-card"], [class*="job-listing"]');
                    for (var i = 0; i < items.length; i++) {
                        var item = items[i];
                        var link = item.querySelector('a[href]');
                        if (!link) continue;
                        var title = '';
                        var titleEl = item.querySelector('h2, h3, h4, [class*="title"], [class*="Title"]');
                        if (titleEl) title = titleEl.innerText.trim().split('\\n')[0];
                        if (!title) title = link.innerText.trim().split('\\n')[0];
                        var url = link.href || '';
                        if (!title || title.length < 3 || !url || seen[url]) continue;
                        seen[url] = true;
                        var location = '';
                        var locEl = item.querySelector('[class*="location"], [class*="Location"]');
                        if (locEl) location = locEl.innerText.trim();
                        results.push({title: title, url: url, location: location, department: ''});
                    }
                }

                // Strategy 3: Direct job link extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/BoschGroup/"], a[href*="/job/"]');
                    for (var i = 0; i < links.length; i++) {
                        var el = links[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var url = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (url.includes('login') || url.includes('sign-in') || url.includes('javascript:')) continue;
                        // Skip non-job pages (company pages, category pages)
                        if (url.endsWith('/india') || url.endsWith('/BoschGroup') || url.endsWith('/BoschGroup/')) continue;
                        if (seen[url]) continue;
                        seen[url] = true;
                        var location = '';
                        var parent = el.closest('li, div, article, section');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl) location = locEl.innerText.trim();
                            if (!location) {
                                var lines = parent.innerText.split('\\n');
                                for (var j = 0; j < lines.length; j++) {
                                    var line = lines[j].trim();
                                    if (line && (line.includes('India') || line.includes('Mumbai') || line.includes('Bangalore') ||
                                        line.includes('Hyderabad') || line.includes('Chennai') || line.includes('Delhi') ||
                                        line.includes('Pune') || line.includes('Gurgaon') || line.includes('Coimbatore'))) {
                                        location = line;
                                        break;
                                    }
                                }
                            }
                        }
                        results.push({title: title, url: url, location: location, department: ''});
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
                                    results.push({title: text.split('\\n')[0].trim(), url: href, location: '', department: ''});
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
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    if url and url.startswith('/'):
                        url = f"https://careers.smartrecruiters.com{url}"

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
                logger.warning("No jobs found on this page")

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            # SmartRecruiters often uses infinite scroll - scroll more to load
            last_height = driver.execute_script("return document.body.scrollHeight")
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            # Also try pagination buttons
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'li.next a'),
                (By.CSS_SELECTOR, 'button.load-more'),
                (By.CSS_SELECTOR, '[class*="load-more"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Load more")]'),
                (By.XPATH, '//button[contains(text(), "Show more")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] a[class*="next"]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page / loaded more")
                        time.sleep(3)
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
    scraper = BoschScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

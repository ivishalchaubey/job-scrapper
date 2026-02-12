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

logger = setup_logger('visa_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class VisaScraper:
    def __init__(self):
        self.company_name = 'Visa'
        self.url = 'https://www.visa.co.in/en_in/jobs/?cities=Bangalore&cities=Mumbai'
        self.base_url = 'https://www.visa.co.in'

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
            short_wait = WebDriverWait(driver, 5)
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(15)

            # Accept cookies if present
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button, a, div[role="button"]');
                    for (var i = 0; i < btns.length; i++) {
                        var txt = (btns[i].innerText || '').toLowerCase();
                        if (txt.includes('accept') || txt.includes('agree') || txt.includes('got it') || txt.includes('ok')) {
                            if (txt.length < 30) {
                                btns[i].click();
                                break;
                            }
                        }
                    }
                """)
                time.sleep(2)
            except:
                pass

            # Scroll to load lazy content
            for scroll_i in range(5):
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
            # Scroll to ensure content is loaded
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Links with /job/ or /jobs/ in href (Visa career portal pattern)
                var jobLinks = document.querySelectorAll('a[href*="/job/"], a[href*="/jobs/"], a[href*="jobId"], a[href*="job-detail"], a[href*="requisition"]');
                for (var i = 0; i < jobLinks.length; i++) {
                    var el = jobLinks[i];
                    var href = el.href || '';
                    if (!href || seen[href]) continue;
                    var title = (el.innerText || el.textContent || '').trim().split('\\n')[0].trim();
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (title.toLowerCase() === 'jobs' || title.toLowerCase() === 'careers' ||
                        title.toLowerCase() === 'apply' || title.toLowerCase() === 'search') continue;

                    seen[href] = true;

                    var parent = el.closest('div[class*="job"], li[class*="job"], article, div[class*="card"], div[class*="result"], div[class*="listing"], div[class*="item"], tr');
                    var location = '';
                    var dept = '';
                    var date = '';

                    if (parent) {
                        var locEl = parent.querySelector('[class*="location"], [class*="Location"], [class*="city"], [class*="City"]');
                        if (locEl && locEl !== el) location = locEl.innerText.trim();

                        var deptEl = parent.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="team"]');
                        if (deptEl && deptEl !== el) dept = deptEl.innerText.trim();

                        var dateEl = parent.querySelector('[class*="date"], [class*="Date"], [class*="posted"], time');
                        if (dateEl && dateEl !== el) date = dateEl.innerText.trim();
                    }

                    results.push({title: title, url: href, location: location, date: date, department: dept});
                }

                // Strategy 2: Job card divs
                if (results.length === 0) {
                    var cards = document.querySelectorAll('div[class*="job-card"], div[class*="jobCard"], div[class*="job-listing"], div[class*="jobListing"], div[class*="job-item"], div[class*="jobItem"], article[class*="job"], li[class*="job"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var linkEl = card.querySelector('a[href]');
                        var titleEl = card.querySelector('h2, h3, h4, [class*="title"], [class*="Title"]');
                        var title = '';
                        var href = '';

                        if (titleEl) {
                            title = titleEl.innerText.trim().split('\\n')[0].trim();
                            var tLink = titleEl.querySelector('a[href]') || titleEl.closest('a[href]');
                            if (tLink) href = tLink.href;
                        }
                        if (!title && linkEl) {
                            title = linkEl.innerText.trim().split('\\n')[0].trim();
                        }
                        if (!href && linkEl) href = linkEl.href || '';

                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (href && seen[href]) continue;
                        if (href) seen[href] = true;

                        var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                        var dept = deptEl ? deptEl.innerText.trim() : '';

                        results.push({title: title, url: href || '', location: location, date: '', department: dept});
                    }
                }

                // Strategy 3: Generic card/tile divs
                if (results.length === 0) {
                    var cards = document.querySelectorAll('div.card, div[class*="card"], div[class*="tile"], div[class*="Tile"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var linkEl = card.querySelector('a[href]');
                        if (!linkEl) continue;
                        var href = linkEl.href || '';
                        if (!href || seen[href]) continue;
                        // Only consider links that look job-related
                        if (!href.includes('job') && !href.includes('career') && !href.includes('position') &&
                            !href.includes('opening') && !href.includes('req')) continue;

                        var title = linkEl.innerText.trim().split('\\n')[0].trim();
                        if (!title || title.length < 3 || title.length > 200) continue;
                        seen[href] = true;

                        var locEl = card.querySelector('[class*="location"]');
                        var location = locEl ? locEl.innerText.trim() : '';

                        results.push({title: title, url: href, location: location, date: '', department: ''});
                    }
                }

                // Strategy 4: Table rows with job data
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        if (row.querySelector('th')) continue;
                        var link = row.querySelector('a[href]');
                        if (!link) continue;
                        var title = link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (!title || title.length < 3 || title.length > 200 || !href || seen[href]) continue;
                        if (href.includes('javascript:') || href.includes('#') || href.includes('login')) continue;
                        seen[href] = true;
                        var tds = row.querySelectorAll('td');
                        var location = tds.length >= 2 ? tds[1].innerText.trim() : '';
                        results.push({title: title, url: href, location: location, date: '', department: ''});
                    }
                }

                // Strategy 5: Any anchor with href containing job-like patterns in the main content area
                if (results.length === 0) {
                    var mainContent = document.querySelector('main, [role="main"], #content, .content, #main, .main');
                    var container = mainContent || document.body;
                    var allLinks = container.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var el = allLinks[i];
                        var href = el.href || '';
                        if (!href || seen[href]) continue;
                        if (!href.includes('job') && !href.includes('position') && !href.includes('career') && !href.includes('opening')) continue;
                        if (href.includes('javascript:') || href.includes('#') || href.includes('login') || href.includes('signup')) continue;
                        var title = el.innerText.trim().split('\\n')[0].trim();
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (title.toLowerCase() === 'jobs' || title.toLowerCase() === 'careers' || title.toLowerCase() === 'apply now') continue;
                        seen[href] = true;
                        results.push({title: title, url: href, location: '', date: '', department: ''});
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
                    if url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]
                    elif url and 'jobId=' in url:
                        import re
                        id_match = re.search(r'jobId=(\w+)', url)
                        if id_match:
                            job_id = id_match.group(1)

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
                        'remote_type': '', 'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                    page_url = driver.current_url
                    logger.info(f"Current URL: {page_url}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            next_selectors = [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), ">")]'),
                (By.XPATH, '//a[contains(@class, "next")]'),
                (By.XPATH, '//button[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.CSS_SELECTOR, 'button[title="Next"]'),
            ]

            for sel_type, sel_val in next_selectors:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except:
                    continue

            # Try JS fallback for pagination
            clicked = driver.execute_script("""
                var els = document.querySelectorAll('a, button');
                for (var i = 0; i < els.length; i++) {
                    var txt = (els[i].innerText || '').trim().toLowerCase();
                    var label = (els[i].getAttribute('aria-label') || '').toLowerCase();
                    if (txt === 'next' || txt === '>' || txt === '>>' || label.includes('next')) {
                        if (els[i].offsetParent !== null) {
                            els[i].click();
                            return true;
                        }
                    }
                }
                return false;
            """)
            if clicked:
                logger.info("Navigated to next page via JS fallback")
                return True

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
    scraper = VisaScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

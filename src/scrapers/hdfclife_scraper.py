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

logger = setup_logger('hdfclife_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class HDFCLifeScraper:
    def __init__(self):
        self.company_name = 'HDFC Life'
        self.url = 'https://www.hdfclife.com/hdfc-careers/'
        self.base_url = 'https://www.hdfclife.com'

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
            # The main careers page only has department categories (Sales, Operations, Technology, Support).
            # Actual job listings are loaded dynamically on the find-your-fit.html page via encrypted API calls.
            # We navigate directly to find-your-fit.html which triggers JS to load all open requisitions.
            fit_url = self.url.rstrip('/') + '/find-your-fit.html'
            logger.info(f"Starting {self.company_name} scraping from {fit_url}")
            driver.get(fit_url)
            time.sleep(15)

            # Scroll to trigger lazy loading and allow JS to fully render job cards
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            # Wait for job cards to appear (the page loads them via encrypted API)
            # The JS renders .main-job-card-list divs for each job
            for attempt in range(6):
                card_count = driver.execute_script(
                    "return document.querySelectorAll('.main-job-card-list').length;"
                )
                if card_count > 0:
                    logger.info(f"Found {card_count} job cards after {(attempt+1)*3}s wait")
                    break
                logger.info(f"Waiting for job cards to load... attempt {attempt+1}")
                time.sleep(3)

            # Also try clicking each job role tab to load all categories
            try:
                tabs = driver.find_elements(By.CSS_SELECTOR, '.job-type')
                if tabs:
                    logger.info(f"Found {len(tabs)} job role tabs")
                    for tab in tabs:
                        try:
                            tab_text = tab.text.strip()
                            if not tab_text or 'Front Line Sales' in tab_text:
                                continue
                            driver.execute_script("arguments[0].click();", tab)
                            time.sleep(5)
                            page_jobs = self._extract_jobs(driver)
                            if page_jobs:
                                all_jobs.extend(page_jobs)
                                logger.info(f"Tab '{tab_text}': {len(page_jobs)} jobs (total: {len(all_jobs)})")
                        except Exception as e:
                            logger.warning(f"Error clicking tab: {str(e)}")
                            continue
            except Exception as e:
                logger.warning(f"Could not find tabs: {str(e)}")

            # If no tabs found or tabs didn't work, extract from current page
            if not all_jobs:
                page_jobs = self._extract_jobs(driver)
                if page_jobs:
                    all_jobs.extend(page_jobs)
                    logger.info(f"Extracted {len(page_jobs)} jobs from main page")

            # Deduplicate by external_id
            seen_ids = set()
            unique_jobs = []
            for job in all_jobs:
                if job['external_id'] not in seen_ids:
                    seen_ids.add(job['external_id'])
                    unique_jobs.append(job)
            all_jobs = unique_jobs

            logger.info(f"Total unique jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver):
        jobs = []
        try:
            # Scroll to load all lazy content
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: HDFC Life find-your-fit page renders job cards as .main-job-card-list
                // Each card has: data-id (JOB_ROLE), req-id (REQID)
                // Inside: .job-card-title-list (role), .job-card-sub-title (designation),
                //         .card-loc-text (city), .exp-text (experience), salary text
                var cards = document.querySelectorAll('.main-job-card-list');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var reqId = card.getAttribute('req-id') || '';
                    var jobRole = card.getAttribute('data-id') || '';

                    var titleEl = card.querySelector('.job-card-sub-title');
                    var roleEl = card.querySelector('.job-card-title-list');
                    var locEl = card.querySelector('.card-loc-text');
                    var expEl = card.querySelector('.exp-text');
                    var salaryEl = card.querySelector('.sal-text p, [class*="sal"] p');

                    var designation = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    var role = roleEl ? roleEl.innerText.trim() : '';
                    var title = designation || role;
                    if (!title) continue;

                    var location = locEl ? locEl.innerText.trim() : '';
                    var experience = expEl ? expEl.innerText.trim() : '';
                    var salary = salaryEl ? salaryEl.innerText.trim() : '';
                    var department = role || jobRole;

                    var key = reqId || title + '_' + location;
                    if (seen[key]) continue;
                    seen[key] = true;

                    results.push({
                        title: title,
                        location: location,
                        url: '',
                        date: '',
                        department: department,
                        experience: experience,
                        salary: salary,
                        reqId: reqId
                    });
                }

                // Strategy 2: If no .main-job-card-list found, look for job cards in .fit-page-card
                if (results.length === 0) {
                    var fitCards = document.querySelectorAll('.fit-page-card > div, .job-card > div');
                    for (var i = 0; i < fitCards.length; i++) {
                        var card = fitCards[i];
                        var text = card.innerText.trim();
                        if (!text || text.length < 5 || text === 'No Result Found') continue;

                        var titleEl = card.querySelector('h3, h4, [class*="title"], [class*="sub-title"]');
                        var locEl = card.querySelector('[class*="loc"], [class*="city"]');
                        var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : text.split('\\n')[0];
                        var location = locEl ? locEl.innerText.trim() : '';
                        var reqId = card.getAttribute('req-id') || '';

                        var key = reqId || title + '_' + location;
                        if (seen[key]) continue;
                        seen[key] = true;

                        results.push({
                            title: title,
                            location: location,
                            url: '',
                            date: '',
                            department: '',
                            experience: '',
                            salary: '',
                            reqId: reqId
                        });
                    }
                }

                // Strategy 3: Generic fallback - look for any job-related links on the page
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="find-your-fit"], a[href*="career"], a[href*="job"]');
                    for (var i = 0; i < links.length; i++) {
                        var el = links[i];
                        var text = (el.innerText || '').trim().split('\\n')[0];
                        var href = el.href || '';
                        if (!text || text.length < 3 || text.length > 200) continue;
                        if (href.includes('javascript:') || href.includes('#') || href.includes('login')) continue;
                        if (seen[href]) continue;
                        seen[href] = true;
                        results.push({title: text, url: href, location: '', date: '', department: '', experience: '', salary: '', reqId: ''});
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                seen_keys = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    experience = jdata.get('experience', '').strip()
                    salary = jdata.get('salary', '').strip()
                    req_id = jdata.get('reqId', '').strip()
                    url = jdata.get('url', '').strip()
                    date = jdata.get('date', '').strip()

                    if not title or len(title) < 3:
                        continue

                    # Use reqId as primary key, fallback to title+location
                    dedup_key = req_id if req_id else f"{title}_{location}"
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Build apply URL from reqId if available
                    apply_url = url if url else self.url
                    if req_id and not url:
                        apply_url = f"{self.url.rstrip('/')}/find-your-fit.html?reqId={req_id}"

                    job_id = req_id if req_id else hashlib.md5((url or title).encode()).hexdigest()[:12]
                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': apply_url, 'location': location,
                        'department': department, 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': department, 'experience_level': experience,
                        'salary_range': salary,
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
        # HDFC Life find-your-fit page loads all jobs at once via API, no pagination needed
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
    scraper = HDFCLifeScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

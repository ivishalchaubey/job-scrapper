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

logger = setup_logger('volvo_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class VolvoScraper:
    def __init__(self):
        self.company_name = 'Volvo'
        self.url = 'https://jobs.volvogroup.com/'
        self.base_url = 'https://jobs.volvogroup.com'

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
                cookie_btns = driver.find_elements(By.CSS_SELECTOR,
                    'button[id*="cookie"], button[class*="cookie"], button[id*="accept"], button[class*="accept"], button[id*="consent"]')
                for btn in cookie_btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Accepted cookies")
                        time.sleep(2)
                        break
            except:
                pass

            # Also try JS cookie acceptance
            driver.execute_script("""
                var btns = document.querySelectorAll('button, a');
                for (var i = 0; i < btns.length; i++) {
                    var txt = (btns[i].innerText || '').toLowerCase();
                    if (txt.includes('accept') && (txt.includes('cookie') || txt.includes('all'))) {
                        btns[i].click();
                        break;
                    }
                }
            """)
            time.sleep(2)

            # Try to search for India jobs on Volvo portal
            search_attempted = False

            # Strategy 1: Look for search input and type "India"
            search_selectors = [
                'input[type="search"]', 'input[type="text"]', 'input[placeholder*="search" i]',
                'input[placeholder*="Search" i]', 'input[placeholder*="job" i]', 'input[name*="search" i]',
                'input[name*="keyword" i]', 'input[id*="search" i]', 'input[class*="search" i]',
                'input[aria-label*="search" i]', 'input[aria-label*="Search" i]'
            ]

            for sel in search_selectors:
                try:
                    search_input = driver.find_element(By.CSS_SELECTOR, sel)
                    if search_input.is_displayed():
                        search_input.clear()
                        search_input.send_keys('India')
                        logger.info(f"Typed 'India' into search input: {sel}")
                        time.sleep(1)

                        # Try to submit/click search
                        try:
                            search_input.send_keys(u'\ue007')  # Enter key
                        except:
                            pass

                        # Also try clicking a search button
                        try:
                            search_btn = driver.find_element(By.CSS_SELECTOR,
                                'button[type="submit"], button[class*="search"], button[aria-label*="search" i]')
                            if search_btn.is_displayed():
                                driver.execute_script("arguments[0].click();", search_btn)
                        except:
                            pass

                        search_attempted = True
                        time.sleep(8)
                        break
                except:
                    continue

            # Strategy 2: Try to find country/location filter and select India
            if not search_attempted:
                driver.execute_script("""
                    var selects = document.querySelectorAll('select');
                    for (var i = 0; i < selects.length; i++) {
                        var opts = selects[i].querySelectorAll('option');
                        for (var j = 0; j < opts.length; j++) {
                            if (opts[j].text.toLowerCase().includes('india')) {
                                selects[i].value = opts[j].value;
                                selects[i].dispatchEvent(new Event('change', {bubbles: true}));
                                break;
                            }
                        }
                    }
                """)
                time.sleep(5)

            # Strategy 3: Try clicking location/country links
            if not search_attempted:
                driver.execute_script("""
                    var links = document.querySelectorAll('a, button, span, div');
                    for (var i = 0; i < links.length; i++) {
                        var txt = (links[i].innerText || '').trim().toLowerCase();
                        if (txt === 'india' || txt === 'india jobs' || txt.includes('india')) {
                            links[i].click();
                            break;
                        }
                    }
                """)
                time.sleep(5)

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

                // Strategy 1: Job links with /job/ in href (Volvo pattern)
                var jobLinks = document.querySelectorAll('a[href*="/job/"], a[href*="/jobs/"], a[href*="jobId"], a[href*="job-"], a[href*="/position/"]');
                for (var i = 0; i < jobLinks.length; i++) {
                    var el = jobLinks[i];
                    var href = el.href || '';
                    if (!href || seen[href]) continue;
                    var title = (el.innerText || el.textContent || '').trim().split('\\n')[0].trim();
                    if (!title || title.length < 3 || title.length > 200) continue;

                    // Skip navigation/menu links
                    if (title.toLowerCase() === 'jobs' || title.toLowerCase() === 'careers' ||
                        title.toLowerCase() === 'search' || title.toLowerCase() === 'home') continue;

                    seen[href] = true;

                    var parent = el.closest('div[class*="job"], li[class*="job"], article, tr, div[class*="card"], div[class*="result"], div[class*="listing"], div[class*="item"]');
                    var location = '';
                    var dept = '';
                    var date = '';

                    if (parent) {
                        var locEl = parent.querySelector('[class*="location"], [class*="Location"], [data-field*="location"], span[class*="loc"]');
                        if (locEl && locEl !== el) location = locEl.innerText.trim();

                        var deptEl = parent.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="Category"]');
                        if (deptEl && deptEl !== el) dept = deptEl.innerText.trim();

                        var dateEl = parent.querySelector('[class*="date"], [class*="Date"], [class*="posted"], time');
                        if (dateEl && dateEl !== el) date = dateEl.innerText.trim();

                        // If no location found from class, try data attributes
                        if (!location) {
                            var allSpans = parent.querySelectorAll('span, div, p');
                            for (var s = 0; s < allSpans.length; s++) {
                                var spanText = allSpans[s].innerText.trim();
                                if (spanText.includes('India') || spanText.includes('Bangalore') ||
                                    spanText.includes('Mumbai') || spanText.includes('Pune') ||
                                    spanText.includes('Chennai') || spanText.includes('Delhi') ||
                                    spanText.includes('Hyderabad')) {
                                    location = spanText;
                                    break;
                                }
                            }
                        }
                    }

                    results.push({title: title, url: href, location: location, date: date, department: dept});
                }

                // Strategy 2: Div/article-based job cards
                if (results.length === 0) {
                    var cards = document.querySelectorAll('div[class*="job-card"], div[class*="jobCard"], div[class*="job-listing"],  div[class*="jobListing"], article[class*="job"], li[class*="job"], div[class*="search-result"], div[class*="searchResult"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var linkEl = card.querySelector('a[href]');
                        if (!linkEl) continue;
                        var title = linkEl.innerText.trim().split('\\n')[0].trim();
                        var href = linkEl.href || '';
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

                // Strategy 3: Generic list items with links
                if (results.length === 0) {
                    var items = document.querySelectorAll('ul li a[href], ol li a[href]');
                    for (var i = 0; i < items.length; i++) {
                        var el = items[i];
                        var href = el.href || '';
                        if (!href || seen[href]) continue;
                        // Only consider links that look like job URLs
                        if (!href.includes('job') && !href.includes('position') && !href.includes('career') && !href.includes('opening') && !href.includes('req')) continue;
                        var title = el.innerText.trim().split('\\n')[0].trim();
                        if (!title || title.length < 3 || title.length > 200) continue;
                        seen[href] = true;

                        var parent = el.closest('li');
                        var location = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"]');
                            if (locEl) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: href, location: location, date: '', department: ''});
                    }
                }

                // Strategy 4: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr');
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
                        var dept = tds.length >= 3 ? tds[2].innerText.trim() : '';
                        results.push({title: title, url: href, location: location, date: '', department: dept});
                    }
                }

                // Strategy 5: Any remaining links that look like job postings
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var el = allLinks[i];
                        var href = el.href || '';
                        if (!href || seen[href]) continue;
                        if (!href.includes('job') && !href.includes('position') && !href.includes('req') && !href.includes('opening')) continue;
                        if (href.includes('javascript:') || href.includes('#') || href.includes('login') || href.includes('signup')) continue;
                        var title = el.innerText.trim().split('\\n')[0].trim();
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (title.toLowerCase() === 'jobs' || title.toLowerCase() === 'careers') continue;
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
    scraper = VolvoScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

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

logger = setup_logger('poonawallafincorp_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class PoonawallaFincorpScraper:
    def __init__(self):
        self.company_name = 'Poonawalla Fincorp'
        self.url = 'https://career.poonawallafincorp.com/'
        self.base_url = 'https://career.poonawallafincorp.com'

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
            time.sleep(14)

            # Scroll to load lazy content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Check for iframes (career portals often embed content)
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                logger.info(f"Found {len(iframes)} iframes, checking for job content")
                for iframe in iframes:
                    try:
                        src = iframe.get_attribute('src') or ''
                        iframe_id = iframe.get_attribute('id') or ''
                        logger.info(f"iframe id={iframe_id} src={src[:100]}")
                        if any(kw in src.lower() for kw in ['job', 'career', 'recruit', 'talent', 'apply']):
                            driver.switch_to.frame(iframe)
                            logger.info("Switched to job iframe")
                            time.sleep(5)
                            break
                    except:
                        continue

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

                // Strategy 1: Job-specific div containers
                var jobDivs = document.querySelectorAll('div[class*="job"], div[class*="Job"], div[class*="vacancy"], div[class*="Vacancy"], div[class*="opening"], div[class*="Opening"], div[class*="position"], div[class*="Position"]');
                for (var i = 0; i < jobDivs.length; i++) {
                    var div = jobDivs[i];
                    var titleEl = div.querySelector('h2, h3, h4, h5, [class*="title"], [class*="Title"], [class*="designation"], [class*="name"]');
                    if (!titleEl) {
                        var linkEl = div.querySelector('a[href]');
                        if (linkEl) titleEl = linkEl;
                    }
                    if (!titleEl) continue;

                    var title = (titleEl.innerText || titleEl.textContent || '').trim().split('\\n')[0].trim();
                    var linkEl = div.querySelector('a[href]') || titleEl.closest('a');
                    var href = linkEl ? (linkEl.href || '') : '';
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (href && seen[href]) continue;
                    if (href) seen[href] = true;

                    var locEl = div.querySelector('[class*="location"], [class*="Location"], [class*="loc"], [class*="city"]');
                    var location = locEl ? locEl.innerText.trim() : '';
                    var deptEl = div.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="function"]');
                    var dept = deptEl ? deptEl.innerText.trim() : '';
                    var dateEl = div.querySelector('[class*="date"], [class*="Date"], [class*="posted"], time');
                    var date = dateEl ? dateEl.innerText.trim() : '';
                    var expEl = div.querySelector('[class*="experience"], [class*="Experience"], [class*="exp"]');
                    var exp = expEl ? expEl.innerText.trim() : '';

                    results.push({title: title, location: location, url: href, date: date, department: dept, experience: exp});
                }

                // Strategy 2: Links with job/career in href
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/job"], a[href*="/jobs"], a[href*="/career"], a[href*="/vacancy"], a[href*="/opening"], a[href*="/position"]');
                    for (var i = 0; i < links.length; i++) {
                        var el = links[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var href = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (seen[href]) continue;
                        if (['jobs', 'careers', 'career', 'home', 'search'].indexOf(title.toLowerCase()) >= 0) continue;
                        seen[href] = true;

                        var parent = el.closest('tr, div[class*="row"], div[class*="item"], li, article, div.card');
                        var location = '';
                        var dept = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl && locEl !== el) location = locEl.innerText.trim();
                            var deptEl = parent.querySelector('[class*="department"], [class*="Department"]');
                            if (deptEl && deptEl !== el) dept = deptEl.innerText.trim();
                        }
                        results.push({title: title, url: href, location: location, date: '', department: dept, experience: ''});
                    }
                }

                // Strategy 3: Card-based layout
                if (results.length === 0) {
                    var cards = document.querySelectorAll('div.card, div[class*="card"], div[class*="Card"], article, div[class*="listing"], div[class*="Listing"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="Title"]');
                        var linkEl = card.querySelector('a[href]');
                        if (!titleEl && !linkEl) continue;

                        var title = '';
                        if (titleEl) {
                            title = titleEl.innerText.trim().split('\\n')[0];
                        } else if (linkEl) {
                            title = linkEl.innerText.trim().split('\\n')[0];
                        }

                        var href = linkEl ? (linkEl.href || '') : '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;
                        if (href && (href.includes('javascript:') || href === '#' || href.includes('login'))) href = '';

                        var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                        var dept = deptEl ? deptEl.innerText.trim() : '';
                        var expEl = card.querySelector('[class*="experience"], [class*="exp"]');
                        var exp = expEl ? expEl.innerText.trim() : '';

                        results.push({title: title, url: href, location: location, date: '', department: dept, experience: exp});
                    }
                }

                // Strategy 4: List items with job-related content
                if (results.length === 0) {
                    var items = document.querySelectorAll('li[class*="job"], li[class*="Job"], li[class*="item"], li[class*="result"], ul[class*="job"] li, ul[class*="listing"] li');
                    for (var i = 0; i < items.length; i++) {
                        var li = items[i];
                        var linkEl = li.querySelector('a[href]');
                        var titleEl = li.querySelector('h2, h3, h4, h5, [class*="title"], [class*="Title"]');
                        if (!titleEl && !linkEl) continue;

                        var title = '';
                        if (titleEl) {
                            title = titleEl.innerText.trim().split('\\n')[0];
                        } else {
                            title = linkEl.innerText.trim().split('\\n')[0];
                        }

                        var href = linkEl ? (linkEl.href || '') : '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;
                        if (href && (href.includes('javascript:') || href.includes('login'))) href = '';

                        var locEl = li.querySelector('[class*="location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        results.push({title: title, url: href, location: location, date: '', department: '', experience: ''});
                    }
                }

                // Strategy 5: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        if (row.querySelector('th')) continue;
                        var tds = row.querySelectorAll('td');
                        if (tds.length < 1) continue;

                        var link = row.querySelector('a[href]');
                        var title = '';
                        var href = '';

                        if (link) {
                            title = link.innerText.trim().split('\\n')[0];
                            href = link.href || '';
                        } else {
                            title = tds[0].innerText.trim().split('\\n')[0];
                        }

                        if (!title || title.length < 3 || title.length > 200) continue;
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;
                        if (href && (href.includes('javascript:') || href.includes('#') || href.includes('login'))) href = '';

                        var location = tds.length >= 2 ? tds[1].innerText.trim() : '';
                        var dept = tds.length >= 3 ? tds[2].innerText.trim() : '';

                        results.push({title: title, url: href, location: location, date: '', department: dept, experience: ''});
                    }
                }

                // Strategy 6: Generic anchor fallback - look for job-like links
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var el = allLinks[i];
                        var href = el.href || '';
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        if (!title || title.length < 5 || title.length > 200) continue;
                        if (href.includes('javascript:') || href === '#' || href.includes('login') || href.includes('mailto:')) continue;
                        var lowerHref = href.toLowerCase();
                        if (lowerHref.includes('job') || lowerHref.includes('position') || lowerHref.includes('career') || lowerHref.includes('opening') || lowerHref.includes('apply') || lowerHref.includes('vacancy')) {
                            if (seen[href]) continue;
                            seen[href] = true;
                            var parent = el.closest('tr, li, div[class*="row"], div[class*="item"], article');
                            var location = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"]');
                                if (locEl && locEl !== el) location = locEl.innerText.trim();
                            }
                            results.push({title: title, url: href, location: location, date: '', department: '', experience: ''});
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                seen_keys = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    date = jdata.get('date', '').strip()
                    department = jdata.get('department', '').strip()
                    experience = jdata.get('experience', '').strip()

                    if not title or len(title) < 3:
                        continue
                    key = url or title
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]
                    elif url and '/position/' in url:
                        parts = url.split('/position/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': department, 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': experience,
                        'salary_range': '', 'remote_type': '', 'status': 'active'
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
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a.next'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="next"]'),
                (By.CSS_SELECTOR, 'a[class*="pagination"][class*="next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), ">")]'),
                (By.XPATH, '//a[contains(@title, "Next")]'),
                (By.XPATH, '//a[contains(text(), "Load More")]'),
                (By.XPATH, '//button[contains(text(), "Load More")]'),
                (By.XPATH, '//button[contains(text(), "Show More")]'),
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

            # JS fallback for next page
            next_clicked = driver.execute_script("""
                var els = document.querySelectorAll('a, button');
                for (var i = 0; i < els.length; i++) {
                    var txt = (els[i].innerText || '').trim().toLowerCase();
                    var ariaLabel = (els[i].getAttribute('aria-label') || '').toLowerCase();
                    if (txt === 'next' || txt === 'next page' || txt === '>' || txt === '>>' || txt === 'load more' || txt === 'show more' || ariaLabel === 'next') {
                        if (els[i].offsetParent !== null) {
                            els[i].click();
                            return true;
                        }
                    }
                }
                return false;
            """)
            if next_clicked:
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
    scraper = PoonawallaFincorpScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

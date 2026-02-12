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

logger = setup_logger('glencore_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class GlencoreScraper:
    def __init__(self):
        self.company_name = 'Glencore'
        self.url = 'https://www.glencore.com/careers/jobs'
        self.base_url = 'https://www.glencore.com'

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

            # Handle cookie consent if present
            try:
                cookie_btn = driver.execute_script("""
                    var btns = document.querySelectorAll('button, a');
                    for (var i = 0; i < btns.length; i++) {
                        var txt = (btns[i].innerText || '').toLowerCase();
                        if (txt.includes('accept') || txt.includes('agree') || txt.includes('got it') || txt.includes('allow')) {
                            btns[i].click();
                            return true;
                        }
                    }
                    return false;
                """)
                if cookie_btn:
                    logger.info("Accepted cookie consent")
                    time.sleep(3)
            except:
                pass

            # Try to filter for India if a location/country filter is available
            try:
                filter_clicked = driver.execute_script("""
                    // Look for location/country filter dropdowns or inputs
                    var selects = document.querySelectorAll('select[class*="location"], select[class*="country"], select[name*="location"], select[name*="country"]');
                    for (var i = 0; i < selects.length; i++) {
                        var opts = selects[i].querySelectorAll('option');
                        for (var j = 0; j < opts.length; j++) {
                            if (opts[j].value.toLowerCase().includes('india') || opts[j].text.toLowerCase().includes('india')) {
                                selects[i].value = opts[j].value;
                                selects[i].dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                        }
                    }
                    // Try clicking a filter link for India
                    var links = document.querySelectorAll('a, button, label, span, div[class*="filter"]');
                    for (var i = 0; i < links.length; i++) {
                        var txt = (links[i].innerText || '').trim().toLowerCase();
                        if (txt === 'india' || txt === 'india ') {
                            links[i].click();
                            return true;
                        }
                    }
                    // Try search input
                    var inputs = document.querySelectorAll('input[type="text"], input[type="search"], input[placeholder*="earch"], input[placeholder*="ocation"]');
                    for (var i = 0; i < inputs.length; i++) {
                        if (inputs[i].placeholder && (inputs[i].placeholder.toLowerCase().includes('location') || inputs[i].placeholder.toLowerCase().includes('country'))) {
                            inputs[i].value = 'India';
                            inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
                            inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
                            return true;
                        }
                    }
                    return false;
                """)
                if filter_clicked:
                    logger.info("Applied India location filter")
                    time.sleep(5)
            except:
                pass

            # Scroll to load lazy content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Check for iframes
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                logger.info(f"Found {len(iframes)} iframes, checking for job content")
                for iframe in iframes:
                    try:
                        src = iframe.get_attribute('src') or ''
                        iframe_id = iframe.get_attribute('id') or ''
                        logger.info(f"iframe id={iframe_id} src={src[:100]}")
                        if 'career' in src.lower() or 'job' in src.lower() or 'talent' in src.lower() or 'workday' in src.lower():
                            driver.switch_to.frame(iframe)
                            logger.info("Switched to career iframe")
                            time.sleep(5)
                            # Scroll inside iframe
                            for _ in range(3):
                                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                time.sleep(2)
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

            # If no jobs found in iframe, switch back
            if not all_jobs and iframes:
                try:
                    driver.switch_to.default_content()
                    logger.info("Switched back to default content to retry")
                    page_jobs = self._extract_jobs(driver)
                    if page_jobs:
                        all_jobs.extend(page_jobs)
                except:
                    pass

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

                // Strategy 1: Job-specific divs and links
                var jobLinks = document.querySelectorAll('a[href*="/job"], a[href*="/jobs"], a[href*="/vacancy"], a[href*="/position"]');
                for (var i = 0; i < jobLinks.length; i++) {
                    var el = jobLinks[i];
                    var title = (el.innerText || el.textContent || '').trim().split('\\n')[0].trim();
                    var href = el.href || '';
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (href && seen[href]) continue;
                    // Skip nav links
                    if (title.toLowerCase() === 'jobs' || title.toLowerCase() === 'careers' ||
                        title.toLowerCase() === 'search' || title.toLowerCase() === 'view all jobs') continue;
                    if (href) seen[href] = true;

                    var parent = el.closest('div, li, tr, article, section');
                    var location = '';
                    var dept = '';
                    if (parent) {
                        var locEl = parent.querySelector('[class*="location"], [class*="Location"], [data-location]');
                        if (locEl && locEl !== el) location = locEl.innerText.trim();
                        var deptEl = parent.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="Category"]');
                        if (deptEl && deptEl !== el) dept = deptEl.innerText.trim();
                    }
                    results.push({title: title, url: href, location: location, date: '', department: dept});
                }

                // Strategy 2: div/article cards with job-related classes
                if (results.length === 0) {
                    var cards = document.querySelectorAll('div[class*="job"], article, div.card, li.job-item, tr.job-row, div[class*="vacancy"], div[class*="listing"], div[class*="result"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var linkEl = card.querySelector('a[href]');
                        if (!linkEl) continue;
                        var title = '';
                        var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="Title"]');
                        if (titleEl) {
                            title = titleEl.innerText.trim().split('\\n')[0];
                        } else {
                            title = linkEl.innerText.trim().split('\\n')[0];
                        }
                        var href = linkEl.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (href && seen[href]) continue;
                        if (href) seen[href] = true;

                        var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var deptEl = card.querySelector('[class*="department"], [class*="Department"]');
                        var dept = deptEl ? deptEl.innerText.trim() : '';
                        var dateEl = card.querySelector('[class*="date"], [class*="Date"], time');
                        var date = dateEl ? dateEl.innerText.trim() : '';
                        results.push({title: title, url: href, location: location, date: date, department: dept});
                    }
                }

                // Strategy 3: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        if (row.querySelector('th')) continue;
                        var link = row.querySelector('a[href]');
                        if (!link) continue;
                        var title = link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (href.includes('javascript:') || href.includes('#') || href.includes('login')) continue;
                        if (href && seen[href]) continue;
                        seen[href] = true;
                        var tds = row.querySelectorAll('td');
                        var location = tds.length >= 2 ? tds[1].innerText.trim() : '';
                        var dept = tds.length >= 3 ? tds[2].innerText.trim() : '';
                        results.push({title: title, url: href, location: location, date: '', department: dept});
                    }
                }

                // Strategy 4: Generic list items with links
                if (results.length === 0) {
                    var items = document.querySelectorAll('ul li, ol li');
                    for (var i = 0; i < items.length; i++) {
                        var li = items[i];
                        var linkEl = li.querySelector('a[href]');
                        if (!linkEl) continue;
                        var title = linkEl.innerText.trim().split('\\n')[0];
                        var href = linkEl.href || '';
                        if (!title || title.length < 5 || title.length > 200) continue;
                        if (!href || href.includes('javascript:') || href.includes('#')) continue;
                        if (seen[href]) continue;
                        var lowerHref = href.toLowerCase();
                        if (lowerHref.includes('job') || lowerHref.includes('career') || lowerHref.includes('vacancy') || lowerHref.includes('position')) {
                            seen[href] = true;
                            var locEl = li.querySelector('[class*="location"]');
                            var location = locEl ? locEl.innerText.trim() : '';
                            results.push({title: title, url: href, location: location, date: '', department: ''});
                        }
                    }
                }

                // Strategy 5: Any prominent links with h2/h3/h4 headings
                if (results.length === 0) {
                    var headings = document.querySelectorAll('h2 a[href], h3 a[href], h4 a[href]');
                    for (var i = 0; i < headings.length; i++) {
                        var el = headings[i];
                        var title = el.innerText.trim().split('\\n')[0];
                        var href = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (!href || href.includes('javascript:') || href.includes('#')) continue;
                        if (seen[href]) continue;
                        seen[href] = true;
                        var parent = el.closest('div, li, article, section');
                        var location = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"]');
                            if (locEl) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: href, location: location, date: '', department: ''});
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
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.CSS_SELECTOR, 'a[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="next"]'),
                (By.CSS_SELECTOR, 'a[class*="pagination-next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), ">")]'),
                (By.XPATH, '//a[contains(text(), "\u203a")]'),
                (By.XPATH, '//a[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'nav[aria-label="pagination"] a:last-child'),
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

            # Try JS fallback for next page
            try:
                clicked = driver.execute_script("""
                    var links = document.querySelectorAll('a, button');
                    for (var i = 0; i < links.length; i++) {
                        var txt = (links[i].innerText || '').trim().toLowerCase();
                        var ariaLabel = (links[i].getAttribute('aria-label') || '').toLowerCase();
                        if (txt === 'next' || txt === '>' || txt === '\u203a' || txt === '\u00bb' ||
                            ariaLabel === 'next' || ariaLabel === 'next page') {
                            links[i].click();
                            return true;
                        }
                    }
                    return false;
                """)
                if clicked:
                    logger.info("Navigated to next page via JS fallback")
                    return True
            except:
                pass

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
    scraper = GlencoreScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

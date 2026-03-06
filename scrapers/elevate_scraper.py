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

logger = setup_logger('elevate_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class ElevateScraper:
    def __init__(self):
        self.company_name = 'Elevate'
        self.url = 'https://elevate.law/explore-elevate-global/#opportunities'
        self.base_url = 'https://elevate.law'

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
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception:
            driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(15)

            # Scroll to the opportunities section
            try:
                driver.execute_script("""
                    var el = document.querySelector('#opportunities');
                    if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
                """)
                time.sleep(3)
            except Exception:
                pass

            # Bullhorn OSCP is embedded in an iframe - find and switch to it
            iframe_switched = False
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                logger.info(f"Found {len(iframes)} iframes, looking for Bullhorn iframe")
                for iframe in iframes:
                    try:
                        src = iframe.get_attribute('src') or ''
                        iframe_id = iframe.get_attribute('id') or ''
                        iframe_class = iframe.get_attribute('class') or ''
                        logger.info(f"iframe id={iframe_id} class={iframe_class} src={src[:100]}")
                        if 'bullhorn' in src.lower() or 'oscp' in src.lower() or 'career' in src.lower() or 'job' in src.lower() or 'staffing' in src.lower():
                            driver.switch_to.frame(iframe)
                            logger.info("Switched to Bullhorn iframe")
                            iframe_switched = True
                            time.sleep(8)
                            break
                    except Exception:
                        continue

                # If no specific match, try each iframe
                if not iframe_switched:
                    for idx, iframe in enumerate(iframes):
                        try:
                            driver.switch_to.frame(iframe)
                            # Check if this iframe has job listings
                            has_jobs = driver.execute_script("""
                                return document.querySelectorAll('.list-item, [class*="job"], [class*="listing"], [class*="position"]').length > 0
                                    || document.body.innerText.length > 500;
                            """)
                            if has_jobs:
                                logger.info(f"Switched to iframe #{idx} with potential job content")
                                iframe_switched = True
                                time.sleep(5)
                                break
                            else:
                                driver.switch_to.default_content()
                        except Exception:
                            try:
                                driver.switch_to.default_content()
                            except Exception:
                                pass
                            continue

            # Wait for Angular SPA to render inside iframe
            if iframe_switched:
                time.sleep(8)
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)

            # Scroll parent page too
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

            # If no jobs found in iframe, switch back and try main page
            if not all_jobs and iframe_switched:
                try:
                    driver.switch_to.default_content()
                    logger.info("Switching back to default content to retry")
                    page_jobs = self._extract_jobs(driver)
                    if page_jobs:
                        all_jobs.extend(page_jobs)
                except Exception:
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
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Bullhorn OSCP Angular SPA - .list-item elements
                var listItems = document.querySelectorAll('.list-item, [class*="list-item"], [class*="listItem"], [class*="job-item"], [class*="jobItem"]');
                for (var i = 0; i < listItems.length; i++) {
                    var item = listItems[i];
                    var titleEl = item.querySelector('h2, h3, h4, h5, [class*="title"], [class*="Title"], [class*="name"], [class*="Name"], a');
                    if (!titleEl) continue;
                    var title = titleEl.innerText.trim().split('\\n')[0].trim();
                    if (!title || title.length < 3 || title.length > 200) continue;

                    var linkEl = item.querySelector('a[href]');
                    var href = linkEl ? linkEl.href : '';
                    var key = href || title;
                    if (seen[key]) continue;
                    seen[key] = true;

                    var locEl = item.querySelector('[class*="location"], [class*="Location"], [class*="city"], [class*="place"]');
                    var location = locEl ? locEl.innerText.trim() : '';

                    // Try to parse location from item text
                    if (!location) {
                        var itemText = item.innerText || '';
                        var lines = itemText.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            var line = lines[j].trim();
                            if (line && line !== title && (line.includes('India') || line.includes('Mumbai') || line.includes('Bangalore') || line.includes('Delhi') || line.includes('Hyderabad') || line.includes('Remote') || line.includes('Pune'))) {
                                location = line;
                                break;
                            }
                        }
                    }

                    var deptEl = item.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="Category"]');
                    var dept = deptEl ? deptEl.innerText.trim() : '';

                    var dateEl = item.querySelector('[class*="date"], [class*="Date"], [class*="posted"]');
                    var date = dateEl ? dateEl.innerText.trim() : '';

                    results.push({title: title, location: location, url: href || '', date: date, department: dept});
                }

                // Strategy 2: Angular-rendered job cards
                if (results.length === 0) {
                    var cards = document.querySelectorAll('[class*="job-card"], [class*="jobCard"], [class*="card"], mat-card, [class*="position-card"], [class*="opening"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], a');
                        if (!titleEl) continue;
                        var title = titleEl.innerText.trim().split('\\n')[0].trim();
                        if (!title || title.length < 3 || title.length > 200) continue;

                        var linkEl = card.querySelector('a[href]');
                        var href = linkEl ? linkEl.href : '';
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        var locEl = card.querySelector('[class*="location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                        var dept = deptEl ? deptEl.innerText.trim() : '';

                        results.push({title: title, location: location, url: href || '', date: '', department: dept});
                    }
                }

                // Strategy 3: Table-based listings
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        if (row.querySelector('th')) continue;
                        var cells = row.querySelectorAll('td');
                        if (cells.length < 1) continue;

                        var linkEl = row.querySelector('a[href]');
                        var title = linkEl ? linkEl.innerText.trim().split('\\n')[0] : cells[0].innerText.trim().split('\\n')[0];
                        var href = linkEl ? linkEl.href : '';

                        if (!title || title.length < 3 || title.length > 200) continue;
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        var location = cells.length >= 2 ? cells[1].innerText.trim() : '';
                        var dept = cells.length >= 3 ? cells[2].innerText.trim() : '';

                        results.push({title: title, location: location, url: href || '', date: '', department: dept});
                    }
                }

                // Strategy 4: Direct job links
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="job"], a[href*="career"], a[href*="position"], a[href*="opening"], a[href*="apply"]');
                    for (var i = 0; i < links.length; i++) {
                        var el = links[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var href = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (href.includes('login') || href.includes('sign-in') || href.includes('javascript:')) continue;
                        if (seen[href]) continue;
                        seen[href] = true;

                        var location = '';
                        var parent = el.closest('li, div[class*="job"], div[class*="row"], article, [class*="item"]');
                        if (parent) {
                            var locEl2 = parent.querySelector('[class*="location"]');
                            if (locEl2 && locEl2 !== el) location = locEl2.innerText.trim();
                        }
                        results.push({title: title, url: href, location: location, date: '', department: ''});
                    }
                }

                // Strategy 5: Generic fallback
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var href = allLinks[i].href || '';
                        var text = (allLinks[i].innerText || '').trim();
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            if ((href.includes('/job') || href.includes('/career') || href.includes('/opening') || href.includes('/position')) && !seen[href]) {
                                if (!href.includes('login') && !href.includes('sign-in') && !href.includes('javascript:')) {
                                    seen[href] = true;
                                    results.push({title: text.split('\\n')[0].trim(), url: href, location: '', date: '', department: ''});
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

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'employment_type': '',
                        'department': department,
                        'apply_url': url or self.url,
                        'posted_date': date,
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
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except Exception:
                    pass

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
                (By.CSS_SELECTOR, 'li.next a'),
                (By.CSS_SELECTOR, 'mat-paginator button[aria-label="Next page"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), "Load More")]'),
                (By.XPATH, '//button[contains(text(), "Load More")]'),
                (By.XPATH, '//button[contains(text(), "Show More")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] a[class*="next"]'),
                (By.CSS_SELECTOR, '[class*="pagination"] button[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="load-more"]'),
                (By.CSS_SELECTOR, 'a[class*="load-more"]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False


if __name__ == "__main__":
    scraper = ElevateScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

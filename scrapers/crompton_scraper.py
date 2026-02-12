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

logger = setup_logger('crompton_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class CromptonScraper:
    def __init__(self):
        self.company_name = 'Crompton Greaves'
        self.url = 'https://career10.successfactors.com/portalcareer?company=cromptongr'
        self.base_url = 'https://career10.successfactors.com'

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
            time.sleep(12)

            # SuccessFactors may use iframes - check and switch if needed
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                logger.info(f"Found {len(iframes)} iframes, checking for content iframe")
                for iframe in iframes:
                    try:
                        src = iframe.get_attribute('src') or ''
                        iframe_id = iframe.get_attribute('id') or ''
                        logger.info(f"iframe id={iframe_id} src={src[:80]}")
                        if 'career' in src.lower() or 'job' in src.lower() or 'portal' in iframe_id.lower():
                            driver.switch_to.frame(iframe)
                            logger.info("Switched to career iframe")
                            time.sleep(3)
                            break
                    except:
                        continue

            # SuccessFactors starts with a search form. Click the Search button to load all results.
            search_clicked = False
            search_selectors = [
                (By.CSS_SELECTOR, 'input#searchButton'),
                (By.CSS_SELECTOR, 'button#searchButton'),
                (By.CSS_SELECTOR, 'a#searchButton'),
                (By.CSS_SELECTOR, 'input[value="Search"]'),
                (By.CSS_SELECTOR, 'input[value="Search for Openings"]'),
                (By.CSS_SELECTOR, 'button[value="Search"]'),
                (By.CSS_SELECTOR, 'a.searchButton'),
                (By.CSS_SELECTOR, 'input.searchButton'),
                (By.CSS_SELECTOR, 'input[type="submit"]'),
                (By.CSS_SELECTOR, 'input[type="button"][value*="Search"]'),
                (By.XPATH, '//input[@value="Search"]'),
                (By.XPATH, '//input[@value="Search for Openings"]'),
                (By.XPATH, '//button[contains(text(), "Search")]'),
                (By.XPATH, '//a[contains(text(), "Search")]'),
                (By.XPATH, '//input[contains(@class, "search")]'),
                (By.XPATH, '//input[@type="submit"]'),
            ]
            for sel_type, sel_val in search_selectors:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed():
                        logger.info(f"Found Search button with selector: {sel_val}")
                        driver.execute_script("arguments[0].click();", btn)
                        search_clicked = True
                        break
                except:
                    continue

            # Fallback: try JS click on any search-related element
            if not search_clicked:
                logger.info("Trying JS fallback to find and click Search button")
                search_clicked = driver.execute_script("""
                    // Try input/button with 'Search' value or text
                    var els = document.querySelectorAll('input[type="submit"], input[type="button"], button, a.button');
                    for (var i = 0; i < els.length; i++) {
                        var el = els[i];
                        var val = (el.value || '').toLowerCase();
                        var txt = (el.innerText || '').toLowerCase();
                        if (val.includes('search') || txt.includes('search')) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                """)

            if search_clicked:
                logger.info("Clicked Search button, waiting for results to load...")
                time.sleep(10)
            else:
                logger.warning("Could not find Search button, attempting to extract jobs from current page")

            # Scroll to load results
            for _ in range(3):
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

            # If still in iframe, try switching back and extracting
            if not all_jobs and iframes:
                try:
                    driver.switch_to.default_content()
                    logger.info("Switched back to default content to retry")
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

                // Strategy 1: SuccessFactors table rows (primary pattern)
                // SF uses table-based layouts with data-row class or similar
                var rows = document.querySelectorAll('tr.data-row, tr.dataRow, tr[class*="data-row"], tr[class*="dataRow"]');
                if (rows.length === 0) rows = document.querySelectorAll('table.resultSet tr, table[class*="result"] tr');
                if (rows.length === 0) rows = document.querySelectorAll('table tbody tr');

                for (var i = 0; i < rows.length; i++) {
                    var row = rows[i];
                    // Skip header rows
                    if (row.querySelector('th')) continue;

                    // SF job title selectors
                    var titleEl = row.querySelector('a.jobTitle-link, a.jobTitle, span.titlelink a, a[class*="jobTitle"], a[href*="jobDetail"], a[href*="job_req"]');
                    if (!titleEl) titleEl = row.querySelector('td.colTitle a, td:first-child a, td a[href]');
                    if (!titleEl) titleEl = row.querySelector('a[href]');

                    if (!titleEl) continue;

                    var title = (titleEl.innerText || titleEl.textContent || '').trim().split('\\n')[0].trim();
                    var href = titleEl.href || '';

                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (href && seen[href]) continue;

                    // Location from SF columns
                    var locEl = row.querySelector('td.colLocation, td[class*="location"], td[class*="Location"]');
                    if (!locEl) {
                        // Try second or third column
                        var tds = row.querySelectorAll('td');
                        if (tds.length >= 2) locEl = tds[1];
                    }
                    var location = locEl ? locEl.innerText.trim() : '';

                    // Department
                    var deptEl = row.querySelector('td.colDepartment, td[class*="department"], td[class*="Department"]');
                    var dept = deptEl ? deptEl.innerText.trim() : '';

                    // Date
                    var dateEl = row.querySelector('td.colDate, td[class*="date"], td[class*="Date"]');
                    var date = dateEl ? dateEl.innerText.trim() : '';

                    if (href) seen[href] = true;
                    results.push({title: title, location: location, url: href || '', date: date, department: dept});
                }

                // Strategy 2: SuccessFactors div-based job listing
                if (results.length === 0) {
                    var jobDivs = document.querySelectorAll('div.jobTitle, div[class*="jobTitle"], div.jobResult, div[class*="jobResult"], div[class*="job-result"]');
                    for (var i = 0; i < jobDivs.length; i++) {
                        var div = jobDivs[i];
                        var linkEl = div.querySelector('a[href]') || div.closest('a[href]');
                        var title = '';
                        var href = '';

                        if (linkEl) {
                            title = linkEl.innerText.trim().split('\\n')[0];
                            href = linkEl.href;
                        } else {
                            title = div.innerText.trim().split('\\n')[0];
                        }

                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (href && seen[href]) continue;

                        var parent = div.closest('tr, div[class*="row"], div[class*="result"], li');
                        var location = '';
                        var dept = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl) location = locEl.innerText.trim();
                            var deptEl = parent.querySelector('[class*="department"], [class*="Department"]');
                            if (deptEl) dept = deptEl.innerText.trim();
                        }

                        if (href) seen[href] = true;
                        results.push({title: title, location: location, url: href || '', date: '', department: dept});
                    }
                }

                // Strategy 3: Links with jobDetail in URL (common SF pattern)
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="jobDetail"], a[href*="job_req"], a[href*="jobReq"]');
                    for (var i = 0; i < links.length; i++) {
                        var el = links[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var href = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (seen[href]) continue;
                        seen[href] = true;

                        var location = '';
                        var parent = el.closest('tr, div[class*="row"], li');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl && locEl !== el) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: href, location: location, date: '', department: ''});
                    }
                }

                // Strategy 4: Generic table rows with links
                if (results.length === 0) {
                    var allRows = document.querySelectorAll('table tr');
                    for (var i = 0; i < allRows.length; i++) {
                        var row = allRows[i];
                        if (row.querySelector('th')) continue;
                        var link = row.querySelector('a[href]');
                        if (!link) continue;
                        var title = link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (!title || title.length < 3 || title.length > 200 || !href || seen[href]) continue;
                        // Skip non-job links
                        if (href.includes('javascript:') || href.includes('#') || href.includes('login')) continue;
                        seen[href] = true;
                        var tds = row.querySelectorAll('td');
                        var location = tds.length >= 2 ? tds[1].innerText.trim() : '';
                        var dept = tds.length >= 3 ? tds[2].innerText.trim() : '';
                        results.push({title: title, url: href, location: location, date: '', department: dept});
                    }
                }

                // Strategy 5: SF card/list items
                if (results.length === 0) {
                    var items = document.querySelectorAll('[class*="job-card"], [class*="jobCard"], [class*="job-item"], [class*="jobItem"], li[class*="job"]');
                    for (var i = 0; i < items.length; i++) {
                        var item = items[i];
                        var linkEl = item.querySelector('a[href]');
                        if (!linkEl) continue;
                        var title = linkEl.innerText.trim().split('\\n')[0];
                        var href = linkEl.href || '';
                        if (!title || title.length < 3 || title.length > 200 || seen[href]) continue;
                        if (href.includes('javascript:') || href.includes('login')) continue;
                        seen[href] = true;
                        var locEl = item.querySelector('[class*="location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
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
                    # Extract SF job req ID from URL if available
                    if url and 'jobDetail' in url:
                        import re
                        req_match = re.search(r'job_req_id=(\d+)', url)
                        if req_match:
                            job_id = req_match.group(1)
                    elif url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
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

            # SuccessFactors pagination selectors
            for sel_type, sel_val in [
                # SF-specific next page selectors
                (By.CSS_SELECTOR, 'a.paginationNextLink'),
                (By.CSS_SELECTOR, 'a[class*="paginationNext"]'),
                (By.CSS_SELECTOR, 'a[id*="next"]'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'img[alt="Next"]'),
                (By.XPATH, '//a[contains(@class, "Next")]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), ">")]'),
                (By.XPATH, '//a[contains(@title, "Next")]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except:
                    continue

            # SF also sometimes uses parent element of img for next
            try:
                next_img = driver.find_element(By.XPATH, '//img[contains(@src, "next") or contains(@alt, "Next") or contains(@alt, "next")]')
                parent = next_img.find_element(By.XPATH, '..')
                if parent.tag_name == 'a' and parent.is_displayed():
                    driver.execute_script("arguments[0].click();", parent)
                    logger.info("Navigated to next page via image link")
                    return True
            except:
                pass

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
    scraper = CromptonScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

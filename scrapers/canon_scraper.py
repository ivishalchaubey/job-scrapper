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

logger = setup_logger('canon_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class CanonScraper:
    def __init__(self):
        self.company_name = 'Canon'
        self.url = 'https://career.asia.canon:8086/psc/ps/EMPLOYEE/CIPLCAREER/c/HRS_HRAM.HRS_APP_SCHJOB.GBL?Page=HRS_APP_SCHJOB&Action=U&FOCUS=Applicant&SiteId=2226'
        self.base_url = 'https://career.asia.canon:8086'

    def setup_driver(self):
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        # Allow insecure SSL for non-standard port
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--ignore-ssl-errors')
        chrome_options.add_argument('--allow-insecure-localhost')
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

            # PeopleSoft HCM: check for iframes (PeopleSoft uses iframes extensively)
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                logger.info(f"Found {len(iframes)} iframes")
                for iframe in iframes:
                    try:
                        src = iframe.get_attribute('src') or ''
                        iframe_id = iframe.get_attribute('id') or ''
                        iframe_name = iframe.get_attribute('name') or ''
                        logger.info(f"iframe id={iframe_id} name={iframe_name} src={src[:80]}")
                        # PeopleSoft main content iframe
                        if 'ptifrmtgtframe' in iframe_id.lower() or 'ptifrmtgtframe' in iframe_name.lower() or 'TargetContent' in iframe_id:
                            driver.switch_to.frame(iframe)
                            logger.info("Switched to PeopleSoft target frame")
                            time.sleep(5)
                            break
                        elif 'career' in src.lower() or 'job' in src.lower() or 'hrsapp' in src.lower():
                            driver.switch_to.frame(iframe)
                            logger.info("Switched to career iframe")
                            time.sleep(5)
                            break
                    except Exception:
                        continue

            # PeopleSoft: Click the Search button (ICAction=SEARCHACTIONS#SEARCH)
            search_clicked = False
            search_selectors = [
                (By.CSS_SELECTOR, '#HRS_SCH_WRK2_HRS_SCH_BTN'),
                (By.CSS_SELECTOR, '#HRS_APP_SCHJOB_HRS_SCH_BTN'),
                (By.CSS_SELECTOR, 'input#HRS_SCH_WRK2_HRS_SCH_BTN'),
                (By.CSS_SELECTOR, 'a#HRS_SCH_WRK2_HRS_SCH_BTN'),
                (By.CSS_SELECTOR, 'input[value="Search"]'),
                (By.CSS_SELECTOR, 'a[title="Search"]'),
                (By.CSS_SELECTOR, 'input[id*="SEARCH"]'),
                (By.CSS_SELECTOR, 'input[id*="SCH_BTN"]'),
                (By.XPATH, '//input[@value="Search"]'),
                (By.XPATH, '//a[contains(text(), "Search")]'),
                (By.XPATH, '//input[contains(@id, "SCH_BTN")]'),
                (By.XPATH, '//a[contains(@id, "SCH_BTN")]'),
                (By.XPATH, '//input[@type="button"][contains(@value, "Search")]'),
            ]
            for sel_type, sel_val in search_selectors:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed():
                        logger.info(f"Found PeopleSoft Search button: {sel_val}")
                        driver.execute_script("arguments[0].click();", btn)
                        search_clicked = True
                        break
                except Exception:
                    continue

            # Fallback: Submit via ICAction parameter (PeopleSoft pattern)
            if not search_clicked:
                try:
                    search_clicked = driver.execute_script("""
                        // PeopleSoft ICAction search
                        var icAction = document.getElementById('ICAction');
                        if (icAction) {
                            icAction.value = 'HRS_SCH_WRK2_HRS_SCH_BTN';
                            var form = document.getElementById('win0divHRS_SCH_WRK2_HRS_SCH_BTN');
                            if (!form) form = document.querySelector('form');
                            if (form && form.submit) {
                                form.submit();
                                return true;
                            }
                        }
                        // Try generic search buttons
                        var btns = document.querySelectorAll('input[type="button"], input[type="submit"], a.PSPUSHBUTTON, a.PSHYPERLINK');
                        for (var i = 0; i < btns.length; i++) {
                            var val = (btns[i].value || btns[i].innerText || '').toLowerCase();
                            if (val.includes('search')) {
                                btns[i].click();
                                return true;
                            }
                        }
                        return false;
                    """)
                except Exception:
                    pass

            if search_clicked:
                logger.info("Clicked Search, waiting for PeopleSoft results...")
                time.sleep(12)
            else:
                logger.warning("Could not find PeopleSoft Search button")

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

            # If no jobs found and we were in iframe, switch back and retry
            if not all_jobs and iframes:
                try:
                    driver.switch_to.default_content()
                    logger.info("Switched back to default content for retry")
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

                // Strategy 1: PeopleSoft result table (primary pattern)
                // PS uses table with PSLEVEL* classes or grid/scroll areas
                var rows = document.querySelectorAll('tr[id*="trHRS_AGNT"], tr[id*="HRS_AGNT_RST"], tr[class*="PSLEVEL"]');
                if (rows.length === 0) rows = document.querySelectorAll('table.PSLEVEL1GRID tr, table.PSLEVEL2GRID tr, table[class*="PSLEVEL"] tr');
                if (rows.length === 0) rows = document.querySelectorAll('#HRS_AGNT_RSLT_I\\$scroll\\$0 tr, div[id*="RSLT"] tr');
                if (rows.length === 0) rows = document.querySelectorAll('table tbody tr');

                for (var i = 0; i < rows.length; i++) {
                    var row = rows[i];
                    if (row.querySelector('th')) continue;

                    // PeopleSoft job title link patterns
                    var titleEl = row.querySelector('a[id*="POSTING_TITLE"], a[id*="HRS_JO_PST_SEQ"], span[id*="POSTING_TITLE"], a[class="PSHYPERLINK"], a[class="PSLONGEDITBOX"]');
                    if (!titleEl) titleEl = row.querySelector('a[href*="HRS_CE_JB_DTL"], a[href*="jobDetail"], a[href*="job_req"]');
                    if (!titleEl) titleEl = row.querySelector('td:first-child a[href], td a[href]');
                    if (!titleEl) titleEl = row.querySelector('a[href]');
                    if (!titleEl) continue;

                    var title = (titleEl.innerText || titleEl.textContent || '').trim().split('\\n')[0].trim();
                    var href = titleEl.href || '';

                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (href && seen[href]) continue;

                    // PeopleSoft location column
                    var locEl = row.querySelector('span[id*="LOCATION"], span[id*="HRS_LOCATION"], td[class*="location"]');
                    if (!locEl) {
                        var tds = row.querySelectorAll('td, span.PSLONGEDITBOX, span.PSEDITBOX_DISPONLY');
                        for (var j = 0; j < tds.length; j++) {
                            var text = tds[j].innerText.trim();
                            if (text && text !== title && (text.includes('India') || text.includes('Mumbai') || text.includes('Delhi') || text.includes('Bangalore') || text.includes('Chennai') || text.includes('Hyderabad') || text.includes('Pune') || text.includes('Kolkata'))) {
                                locEl = tds[j];
                                break;
                            }
                        }
                    }
                    var location = locEl ? locEl.innerText.trim() : '';

                    // Department
                    var deptEl = row.querySelector('span[id*="DEPARTMENT"], span[id*="DEPTNAME"]');
                    var dept = deptEl ? deptEl.innerText.trim() : '';

                    // Date
                    var dateEl = row.querySelector('span[id*="OPEN_DT"], span[id*="DATE"]');
                    var date = dateEl ? dateEl.innerText.trim() : '';

                    if (href) seen[href] = true;
                    else seen[title] = true;
                    results.push({title: title, location: location, url: href || '', date: date, department: dept});
                }

                // Strategy 2: PeopleSoft div-based results (newer PS versions)
                if (results.length === 0) {
                    var jobDivs = document.querySelectorAll('div[id*="HRS_AGNT"], div[id*="win0div"], div[class*="ps_box"]');
                    for (var i = 0; i < jobDivs.length; i++) {
                        var div = jobDivs[i];
                        var linkEl = div.querySelector('a[id*="POSTING_TITLE"], a.PSHYPERLINK, a[href]');
                        if (!linkEl) continue;

                        var title = linkEl.innerText.trim().split('\\n')[0].trim();
                        var href = linkEl.href || '';

                        if (!title || title.length < 3 || title.length > 200) continue;
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        var locEl = div.querySelector('span[id*="LOCATION"], [class*="location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var deptEl = div.querySelector('span[id*="DEPARTMENT"]');
                        var dept = deptEl ? deptEl.innerText.trim() : '';

                        results.push({title: title, location: location, url: href || '', date: '', department: dept});
                    }
                }

                // Strategy 3: Generic table rows
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
                        if (href.includes('javascript:void') || href === '#') continue;
                        seen[href] = true;
                        var tds = row.querySelectorAll('td');
                        var location = tds.length >= 2 ? tds[1].innerText.trim() : '';
                        var dept = tds.length >= 3 ? tds[2].innerText.trim() : '';
                        results.push({title: title, url: href, location: location, date: '', department: dept});
                    }
                }

                // Strategy 4: PeopleSoft grid spans
                if (results.length === 0) {
                    var spans = document.querySelectorAll('span[id*="POSTING_TITLE"], span[id*="HRS_JO"]');
                    for (var i = 0; i < spans.length; i++) {
                        var span = spans[i];
                        var title = span.innerText.trim().split('\\n')[0].trim();
                        if (!title || title.length < 3 || title.length > 200 || seen[title]) continue;
                        seen[title] = true;

                        var parent = span.closest('tr, div[id*="win0div"]');
                        var location = '';
                        var dept = '';
                        var href = '';
                        if (parent) {
                            var locEl = parent.querySelector('span[id*="LOCATION"], [class*="location"]');
                            if (locEl) location = locEl.innerText.trim();
                            var deptEl = parent.querySelector('span[id*="DEPARTMENT"]');
                            if (deptEl) dept = deptEl.innerText.trim();
                            var linkEl = parent.querySelector('a[href]');
                            if (linkEl) href = linkEl.href;
                        }

                        results.push({title: title, location: location, url: href || '', date: '', department: dept});
                    }
                }

                // Strategy 5: Generic fallback
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var href = allLinks[i].href || '';
                        var text = (allLinks[i].innerText || '').trim();
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            if ((href.includes('/job') || href.includes('HRS_CE') || href.includes('jobDetail') || href.includes('POSTING')) && !seen[href]) {
                                if (!href.includes('javascript:void') && href !== '#') {
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
                    # Extract PeopleSoft job ID from URL if available
                    if url and 'HRS_CE' in url:
                        import re
                        ps_match = re.search(r'HRS_JO_PST_SEQ=(\d+)', url)
                        if ps_match:
                            job_id = ps_match.group(1)
                        else:
                            ps_match = re.search(r'job_req_id=(\d+)', url)
                            if ps_match:
                                job_id = ps_match.group(1)

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
                    page_url = driver.current_url
                    logger.info(f"Current URL: {page_url}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # PeopleSoft pagination selectors
            for sel_type, sel_val in [
                # PeopleSoft-specific next page
                (By.CSS_SELECTOR, 'a[id*="HRS_PGM_NXT_I"], a[title="Next"]'),
                (By.CSS_SELECTOR, 'a[id*="NEXT"], a[id*="next"]'),
                (By.CSS_SELECTOR, 'a.PSPUSHBUTTON[title="Next"]'),
                (By.CSS_SELECTOR, 'img[alt="Next"]'),
                (By.XPATH, '//a[contains(@id, "NEXT")]'),
                (By.XPATH, '//a[contains(@title, "Next")]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except Exception:
                    continue

            # PeopleSoft next via parent of image
            try:
                next_img = driver.find_element(By.XPATH, '//img[contains(@src, "next") or contains(@alt, "Next")]')
                parent = next_img.find_element(By.XPATH, '..')
                if parent.tag_name == 'a' and parent.is_displayed():
                    driver.execute_script("arguments[0].click();", parent)
                    logger.info("Navigated to next page via image link")
                    return True
            except Exception:
                pass

            return False
        except Exception:
            return False


if __name__ == "__main__":
    scraper = CanonScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

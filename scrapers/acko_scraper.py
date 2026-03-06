from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

try:
    import requests
except ImportError:
    requests = None

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('acko_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class AckoScraper:
    def __init__(self):
        self.company_name = 'Acko'
        self.url = 'https://www.acko.com/careers/jobs/'
        self.kula_url = 'https://careers.kula.ai/acko?jobs=true'

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
            driver = webdriver.Chrome(options=chrome_options)
        except Exception:
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
        """Scrape Acko jobs. Try Kula ATS API via requests first, then Selenium."""
        all_jobs = []

        # Strategy 1: Try requests to Kula ATS URL directly
        if requests is not None:
            try:
                api_jobs = self._scrape_via_kula_api()
                if api_jobs:
                    logger.info(f"Kula API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("Kula API returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.error(f"Kula API method failed: {str(e)}, falling back to Selenium")

        # Strategy 2: Selenium-based scraping (load Kula iframe URL directly)
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_kula_api(self):
        """Fetch job data from Kula ATS by parsing the Next.js RSC payload.

        The Kula career page is a Next.js app that embeds structured job data
        in React Server Components (RSC) script chunks within the HTML. We parse
        the raw HTML to find and extract the JSON job listing data directly.
        """
        import re
        import json

        jobs = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Referer': 'https://www.acko.com/careers/jobs/',
        }

        try:
            response = requests.get(self.kula_url, headers=headers, timeout=30)
            if response.status_code != 200:
                logger.warning(f"Kula page returned status {response.status_code}")
                return jobs

            html = response.text

            # Search the raw HTML for the jobs JSON array in the RSC payload.
            # In the HTML source, the data appears with escaped quotes:
            #   \"jobs\":[{\"id\":12949,\"title\":\"Debt Fund Manager\",...}]
            jobs_marker = '\\"jobs\\":[{\\"id\\"'
            marker_pos = html.find(jobs_marker)
            if marker_pos < 0:
                logger.warning("Could not find jobs marker in HTML")
                return jobs

            # Find the start of the array (the '[' after "jobs":)
            arr_start = html.index('[', marker_pos)

            # Find matching closing bracket by tracking bracket depth
            depth = 0
            arr_end = arr_start
            for ci in range(arr_start, min(arr_start + 200000, len(html))):
                ch = html[ci]
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                if depth == 0:
                    arr_end = ci
                    break

            raw_json = html[arr_start:arr_end + 1]

            # Unescape: the JSON is inside a JS string literal, so quotes
            # and other chars are escaped with backslashes
            unescaped = raw_json.replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')

            # The JSON may contain RSC references like "$18" for lazy-loaded
            # descriptions. Replace them with empty strings for valid JSON.
            unescaped = re.sub(r'"\$[0-9a-fA-F]+"', '""', unescaped)
            unescaped = re.sub(r'"\$L[0-9a-fA-F]+"', '""', unescaped)

            logger.info(f"Extracted jobs JSON array, length={len(unescaped)}")

            try:
                job_list = json.loads(unescaped)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse jobs JSON: {e}")
                return jobs

            if not job_list or not isinstance(job_list, list):
                logger.warning("Jobs JSON parsed but is empty or not a list")
                return jobs

            logger.info(f"Found {len(job_list)} jobs in RSC payload")

            for item in job_list:
                try:
                    title = item.get('title', '').strip()
                    if not title or len(title) < 3:
                        continue

                    job_id = str(item.get('id', ''))
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    ats_job = item.get('ats_job', {}) or {}

                    # Extract location from offices array
                    offices = ats_job.get('offices', []) or []
                    location = ''
                    city = ''
                    state = ''
                    country = 'India'
                    if offices and isinstance(offices, list):
                        office = offices[0]
                        if isinstance(office, dict):
                            location = office.get('location', '')
                            city = office.get('city', '')
                            state = office.get('state', '')
                            country = office.get('country', 'India')

                    # Extract department
                    department = ''
                    ats_dept = ats_job.get('ats_department', {}) or {}
                    if isinstance(ats_dept, dict):
                        department = ats_dept.get('name', '')

                    # Extract employment type and workplace
                    employment_type = ats_job.get('employment_type', '') or ''
                    employment_type = employment_type.replace('_', ' ').title()
                    workplace = ats_job.get('workplace', '') or ''
                    workplace = workplace.replace('_', ' ').title()

                    # Build apply URL
                    apply_url = f"https://careers.kula.ai/acko/job/{job_id}"

                    ext_id = self.generate_external_id(job_id, self.company_name)

                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location or 'India',
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': apply_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': workplace,
                        'status': 'active'
                    })
                    logger.info(f"Extracted: {title} | {location} | {department}")

                except Exception as e:
                    logger.error(f"Error parsing RSC job item: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"RSC parsing failed: {str(e)}")

        return jobs

    def _parse_kula_job(self, item, idx):
        """Parse a single job from Kula ATS API response."""
        if not isinstance(item, dict):
            return None

        title = (item.get('title', '') or item.get('name', '') or
                 item.get('job_title', '') or item.get('position', '') or '').strip()
        if not title or len(title) < 3:
            return None

        location = (item.get('location', '') or item.get('city', '') or '').strip()
        if isinstance(location, list) and location:
            location = location[0] if isinstance(location[0], str) else str(location[0])

        apply_url = item.get('apply_url', '') or item.get('url', '') or item.get('link', '') or ''
        if not apply_url:
            slug = item.get('slug', '') or item.get('id', '')
            if slug:
                apply_url = f"https://careers.kula.ai/acko/job/{slug}"
            else:
                apply_url = self.kula_url

        job_id = str(item.get('id', '') or item.get('job_id', '') or f"acko_api_{idx}")
        department = str(item.get('department', '') or item.get('team', '') or '')
        employment_type = str(item.get('employment_type', '') or item.get('type', '') or '')
        description = str(item.get('description', '') or '')[:3000]

        loc_data = self.parse_location(location)

        return {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': description,
            'location': location or 'India',
            'city': loc_data.get('city', ''),
            'state': loc_data.get('state', ''),
            'country': loc_data.get('country', 'India'),
            'employment_type': employment_type,
            'department': department,
            'apply_url': apply_url,
            'posted_date': str(item.get('posted_date', '') or item.get('created_at', '') or ''),
            'job_function': '',
            'experience_level': str(item.get('experience', '') or ''),
            'salary_range': '',
            'remote_type': str(item.get('remote_type', '') or item.get('work_type', '') or ''),
            'status': 'active'
        }

    def _scrape_via_selenium(self, max_pages):
        """Selenium-based scraping - load Kula iframe URL directly."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from Kula URL: {self.kula_url}")

            # Load the Kula ATS URL directly (skip the parent iframe)
            driver.get(self.kula_url)

            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'div[class*="job"], a[class*="job"], div[class*="opening"], div[class*="position"], div[class*="card"]'
                    ))
                )
                logger.info("Job listings detected on Kula page")
            except Exception as e:
                logger.warning(f"Timeout waiting for Kula jobs: {str(e)}, using fallback wait")
                time.sleep(10)

            # Scroll to load dynamic content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            scraped_ids = set()
            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                page_jobs = self._extract_jobs_from_dom(driver, scraped_ids)
                all_jobs.extend(page_jobs)
                logger.info(f"Page {current_page}: found {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if current_page < max_pages and page_jobs:
                    if not self._go_to_next_page(driver):
                        break
                    time.sleep(3)
                elif not page_jobs:
                    break

                current_page += 1

            # If no jobs found from Kula URL, try the main Acko careers page
            if not all_jobs:
                logger.info("No jobs from Kula URL, trying main Acko careers page")
                driver.get(self.url)
                time.sleep(10)

                # Check for iframe
                try:
                    iframes = driver.find_elements(By.TAG_NAME, 'iframe')
                    for iframe in iframes:
                        src = iframe.get_attribute('src') or ''
                        if 'kula' in src.lower() or 'career' in src.lower() or 'job' in src.lower():
                            logger.info(f"Switching to iframe: {src}")
                            driver.switch_to.frame(iframe)
                            time.sleep(5)
                            break
                except Exception as e:
                    logger.warning(f"Iframe check failed: {str(e)}")

                page_jobs = self._extract_jobs_from_dom(driver, scraped_ids)
                all_jobs.extend(page_jobs)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during Selenium scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _extract_jobs_from_dom(self, driver, scraped_ids):
        """Extract jobs from the current DOM state."""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Kula ATS specific selectors
                var cards = document.querySelectorAll(
                    'div[class*="job-card"], div[class*="jobCard"], a[class*="job-card"], ' +
                    'div[class*="job-listing"], div[class*="opening"], li[class*="job"], ' +
                    'div[class*="position-card"], a[class*="position"], ' +
                    'div[class*="career-card"], div[class*="listing-card"]'
                );

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var title = '';
                    var url = '';
                    var location = '';
                    var department = '';

                    var titleEl = card.querySelector('h2, h3, h4, [class*="title"], [class*="name"], [class*="heading"]');
                    if (titleEl) title = titleEl.innerText.trim().split('\\n')[0];

                    if (card.tagName === 'A') {
                        url = card.href || '';
                        if (!title) title = card.innerText.trim().split('\\n')[0];
                    } else {
                        var link = card.querySelector('a[href]');
                        if (link) {
                            url = link.href || '';
                            if (!title) title = link.innerText.trim().split('\\n')[0];
                        }
                    }

                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (url && seen[url]) continue;

                    var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                    if (locEl) location = locEl.innerText.trim();

                    var deptEl = card.querySelector('[class*="department"], [class*="team"], [class*="category"]');
                    if (deptEl) department = deptEl.innerText.trim();

                    if (url) seen[url] = true;
                    results.push({title: title, url: url || '', location: location, department: department});
                }

                // Strategy 2: Generic link-based extraction
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    var jobKeywords = ['engineer', 'manager', 'developer', 'analyst', 'designer',
                                       'architect', 'lead', 'specialist', 'consultant', 'director',
                                       'associate', 'intern', 'scientist', 'qa', 'product', 'data'];
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var text = link.innerText.trim();
                        var href = link.href || '';
                        if (text.length < 5 || text.length > 200) continue;
                        if (seen[href]) continue;
                        var lower = text.toLowerCase();
                        var isJob = false;
                        for (var j = 0; j < jobKeywords.length; j++) {
                            if (lower.indexOf(jobKeywords[j]) !== -1) { isJob = true; break; }
                        }
                        if (!isJob && href.indexOf('job') === -1 && href.indexOf('position') === -1 &&
                            href.indexOf('opening') === -1 && href.indexOf('apply') === -1) continue;
                        if (href) seen[href] = true;
                        results.push({title: text.split('\\n')[0], url: href, location: '', department: ''});
                    }
                }

                // Strategy 3: Table-based
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tr, tbody tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        if (row.querySelector('th')) continue;
                        var link = row.querySelector('a[href]');
                        if (!link) continue;
                        var title = link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (!title || title.length < 3 || seen[href]) continue;
                        if (href) seen[href] = true;
                        var tds = row.querySelectorAll('td');
                        var loc = tds.length >= 2 ? tds[1].innerText.trim() : '';
                        results.push({title: title, url: href, location: loc, department: ''});
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} potential jobs")
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location or 'India',
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'employment_type': '',
                        'department': department,
                        'apply_url': url or self.kula_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                    scraped_ids.add(ext_id)
            else:
                logger.warning("JS extraction returned no results")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs from DOM: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to the next page."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            next_selectors = [
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Load More")]'),
                (By.XPATH, '//button[contains(text(), "Show More")]'),
                (By.CSS_SELECTOR, 'a.next, button.next'),
                (By.CSS_SELECTOR, '[class*="pagination"] button:last-child'),
            ]

            for sel_type, sel_val in next_selectors:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except Exception:
                    continue

            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
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
            if parts[1] in ['IN', 'IND', 'India']:
                result['country'] = 'India'
            else:
                result['state'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = AckoScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

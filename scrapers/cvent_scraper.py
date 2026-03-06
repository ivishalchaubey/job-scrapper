from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import json
import re

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('cvent_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class CventScraper:
    def __init__(self):
        self.company_name = 'Cvent'
        self.url = 'https://careers.cvent.com/jobs?limit=100&page=1&location=India'
        self.base_url = 'https://careers.cvent.com'

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
        location_str = location_str.strip()
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) == 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        driver = None
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)

            # Wait for the AngularJS SPA to initialize and render
            time.sleep(5)

            # Strategy 1: Try to extract window._jibe.models.jobs pre-rendered data
            jibe_jobs = self._extract_jibe_data(driver)
            if jibe_jobs:
                logger.info(f"Jibe pre-rendered data returned {len(jibe_jobs)} jobs")
                jobs.extend(jibe_jobs)
            else:
                logger.info("No Jibe pre-rendered data, falling back to DOM scraping")

                # Strategy 2: Wait for AngularJS to render and scrape DOM
                try:
                    WebDriverWait(driver, 20).until(
                        lambda d: d.execute_script(
                            "return (typeof angular !== 'undefined') ? "
                            "(angular.element(document.body).injector() !== undefined) : true"
                        )
                    )
                    logger.info("AngularJS app initialized")
                except Exception as e:
                    logger.warning(f"Angular wait timeout: {str(e)}")

                # Wait for job cards to render
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((
                            By.CSS_SELECTOR,
                            'div[class*="job-card"], div[class*="job-result"], '
                            'a[class*="job-card"], div[data-jibe-job], '
                            'div[class*="search-result"], li[class*="job"]'
                        ))
                    )
                    logger.info("Job elements detected in DOM")
                except Exception as e:
                    logger.warning(f"Job element wait timeout: {str(e)}")
                    time.sleep(8)

                # Scroll to load all jobs
                for _ in range(5):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)

                scraped_ids = set()
                page_num = 1

                while page_num <= max_pages:
                    page_jobs = self._extract_jobs_from_dom(driver, scraped_ids)

                    if not page_jobs:
                        break

                    jobs.extend(page_jobs)
                    logger.info(f"Page {page_num}: {len(page_jobs)} jobs (total: {len(jobs)})")

                    if not self._go_to_next_page(driver, page_num):
                        break
                    page_num += 1
                    time.sleep(5)

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return jobs

    def _extract_jibe_data(self, driver):
        """Extract job data from window._jibe.models.jobs (Jibe/iCIMS pre-rendered data)."""
        jobs = []
        try:
            jibe_data = driver.execute_script("""
                // Try to get pre-rendered job data from Jibe's window object
                if (typeof window._jibe !== 'undefined' && window._jibe.models &&
                    window._jibe.models.jobs) {
                    return JSON.stringify(window._jibe.models.jobs);
                }

                // Alternative: Try Jibe search results in window scope
                if (typeof window._jibe !== 'undefined' && window._jibe.initialData &&
                    window._jibe.initialData.jobs) {
                    return JSON.stringify(window._jibe.initialData.jobs);
                }

                // Try searching in the Jibe config
                if (typeof window._jibe !== 'undefined') {
                    return JSON.stringify(window._jibe);
                }

                // Try looking for embedded JSON in script tags
                var scripts = document.querySelectorAll('script[type="application/json"], script:not([src])');
                for (var i = 0; i < scripts.length; i++) {
                    var text = scripts[i].textContent || scripts[i].innerText;
                    if (text && text.includes('"jobs"') && text.includes('"title"')) {
                        return text;
                    }
                }

                return null;
            """)

            if not jibe_data:
                logger.info("No Jibe pre-rendered data found")
                return jobs

            try:
                data = json.loads(jibe_data) if isinstance(jibe_data, str) else jibe_data
            except json.JSONDecodeError:
                logger.warning("Could not parse Jibe data as JSON")
                return jobs

            # Navigate data structure to find job list
            job_list = self._find_jobs_in_jibe_data(data)
            if not job_list:
                logger.info("No job list found in Jibe data structure")
                return jobs

            logger.info(f"Found {len(job_list)} jobs in Jibe pre-rendered data")
            seen_ids = set()

            for idx, job_item in enumerate(job_list):
                try:
                    if not isinstance(job_item, dict):
                        continue

                    title = (job_item.get('title', '') or job_item.get('name', '') or
                             job_item.get('jobTitle', '') or '').strip()
                    if not title or len(title) < 3:
                        continue

                    job_id = str(job_item.get('id', '') or job_item.get('jobId', '') or
                                 job_item.get('requisitionId', '') or '')
                    if not job_id:
                        job_id = f"cvent_jibe_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    location = (job_item.get('location', '') or job_item.get('city', '') or
                                job_item.get('locationName', '') or '').strip()
                    if isinstance(location, dict):
                        city = location.get('city', '')
                        state = location.get('state', '')
                        country = location.get('country', 'India')
                        location = ', '.join(filter(None, [city, state, country]))
                    elif isinstance(location, list):
                        location = ', '.join(str(l) for l in location)

                    department = (job_item.get('department', '') or job_item.get('category', '') or
                                  job_item.get('team', '') or '').strip()
                    if isinstance(department, list) and department:
                        department = department[0]

                    apply_url = (job_item.get('url', '') or job_item.get('applyUrl', '') or
                                 job_item.get('slug', '') or '').strip()
                    if apply_url and not apply_url.startswith('http'):
                        apply_url = f"{self.base_url}{apply_url}" if apply_url.startswith('/') else f"{self.base_url}/{apply_url}"
                    if not apply_url:
                        apply_url = f"{self.base_url}/jobs/{job_id}"

                    employment_type = (job_item.get('type', '') or job_item.get('employmentType', '') or '').strip()
                    posted_date = (job_item.get('postedDate', '') or job_item.get('datePosted', '') or
                                   job_item.get('created_at', '') or '').strip()
                    description = (job_item.get('description', '') or job_item.get('summary', '') or '').strip()
                    if description:
                        description = description[:3000]

                    loc_data = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': description,
                        'location': location,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': str(department),
                        'apply_url': apply_url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error parsing Jibe job item {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Jibe data extraction error: {str(e)}")

        return jobs

    def _find_jobs_in_jibe_data(self, data):
        """Find job list in Jibe data structure."""
        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict):
                sample = data[0]
                if any(k in sample for k in ['title', 'name', 'jobTitle', 'requisitionId']):
                    return data

        if isinstance(data, dict):
            # Check common Jibe paths
            for key in ['jobs', 'results', 'items', 'data', 'models', 'jobsList',
                         'searchResults', 'positions', 'openings']:
                if key in data:
                    result = self._find_jobs_in_jibe_data(data[key])
                    if result:
                        return result

        return None

    def _extract_jobs_from_dom(self, driver, scraped_ids):
        """Extract job listings from Jibe/iCIMS AngularJS rendered DOM."""
        jobs = []
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Jibe-specific job card selectors
                var cardSelectors = [
                    'div[data-jibe-job], div[data-jibe-result]',
                    'div[class*="jibe-search-result"], div[class*="jibe_job"]',
                    'div[class*="job-card"], div[class*="job-result"]',
                    'div[class*="search-result-item"], div[class*="result-card"]',
                    'a[class*="job-card"], a[class*="result-card"]',
                    'div[class*="jobCard"], div[class*="JobCard"]',
                    'li[class*="job-result"], li[class*="search-result"]',
                    'article[class*="job"], div[class*="job-listing"]',
                    'div[ng-repeat*="job"], div[ng-repeat*="result"]'
                ];

                var jobCards = [];
                for (var s = 0; s < cardSelectors.length; s++) {
                    try {
                        var els = document.querySelectorAll(cardSelectors[s]);
                        if (els.length > 0) {
                            jobCards = els;
                            break;
                        }
                    } catch(e) {}
                }

                if (jobCards.length > 0) {
                    for (var i = 0; i < jobCards.length; i++) {
                        var card = jobCards[i];
                        var text = (card.innerText || '').trim();
                        if (text.length < 5) continue;

                        var titleEl = card.querySelector(
                            'h1, h2, h3, h4, [class*="title"], [class*="Title"], ' +
                            '[class*="job-name"], [class*="jobName"], ' +
                            '[class*="job-title"], [class*="jobTitle"]'
                        );
                        var title = titleEl ? titleEl.innerText.trim() : '';
                        if (!title) title = text.split('\\n')[0].trim();
                        if (!title || title.length < 3 || title.length > 200) continue;

                        var linkEl = card.tagName === 'A' ? card : card.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';

                        var location = '';
                        var department = '';
                        var employment_type = '';
                        var posted_date = '';

                        // Location
                        var locEl = card.querySelector(
                            '[class*="location"], [class*="Location"], [class*="city"]'
                        );
                        if (locEl) location = locEl.innerText.trim();

                        // Department
                        var deptEl = card.querySelector(
                            '[class*="department"], [class*="Department"], ' +
                            '[class*="category"], [class*="team"]'
                        );
                        if (deptEl) department = deptEl.innerText.trim();

                        // Employment type
                        var typeEl = card.querySelector('[class*="type"], [class*="employment"]');
                        if (typeEl) {
                            var typeText = typeEl.innerText.trim();
                            if (typeText.match(/full|part|contract|intern/i)) {
                                employment_type = typeText;
                            }
                        }

                        // Date
                        var dateEl = card.querySelector('[class*="date"], [class*="posted"], time');
                        if (dateEl) posted_date = dateEl.getAttribute('datetime') || dateEl.innerText.trim();

                        // Fallback location
                        if (!location) {
                            var lines = text.split('\\n');
                            for (var j = 0; j < lines.length; j++) {
                                var line = lines[j].trim();
                                if (line.match(/India|Gurgaon|Gurugram|Pune|Bangalore|Delhi|Mumbai|Noida|Hyderabad/i)) {
                                    location = line;
                                    break;
                                }
                            }
                        }

                        // Job ID from data attributes
                        var jobId = card.getAttribute('data-jibe-job-id') ||
                                    card.getAttribute('data-job-id') ||
                                    card.getAttribute('data-id') || '';

                        var key = url || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        results.push({
                            title: title, url: url, location: location,
                            department: department, employment_type: employment_type,
                            posted_date: posted_date, jobId: jobId
                        });
                    }
                }

                // Strategy 2: Links to job detail pages
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll(
                        'a[href*="/jobs/"], a[href*="/job/"], a[href*="requisition"], a[href*="/careers/"]'
                    );
                    for (var i = 0; i < jobLinks.length; i++) {
                        var link = jobLinks[i];
                        var href = link.href;
                        var linkText = link.innerText.trim();
                        if (linkText.length < 5 || linkText.length > 200) continue;
                        var lower = linkText.toLowerCase();
                        if (lower === 'apply' || lower === 'view' || lower === 'more' ||
                            lower === 'search' || lower === 'home' || lower === 'back') continue;
                        if (seen[href]) continue;
                        seen[href] = true;

                        var parent = link.closest('div, li, article');
                        var parentText = parent ? parent.innerText : linkText;
                        var loc = '';
                        var dept = '';
                        var pLines = parentText.split('\\n');
                        for (var j = 0; j < pLines.length; j++) {
                            var pLine = pLines[j].trim();
                            if (pLine.match(/India|Gurgaon|Gurugram|Pune|Bangalore|Delhi|Mumbai/i)) {
                                if (!loc) loc = pLine;
                            }
                        }

                        results.push({
                            title: linkText.split('\\n')[0].trim(),
                            url: href, location: loc,
                            department: dept, employment_type: '',
                            posted_date: '', jobId: ''
                        });
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"DOM extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    employment_type = jdata.get('employment_type', '').strip()
                    posted_date = jdata.get('posted_date', '').strip()
                    job_id_raw = jdata.get('jobId', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    job_id = job_id_raw if job_id_raw else f"cvent_dom_{idx}"
                    if not job_id_raw and url:
                        id_match = re.search(r'(?:jobs?|requisition|position)[/=]([a-zA-Z0-9_-]+)', url)
                        if id_match:
                            job_id = id_match.group(1)
                        else:
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue
                    scraped_ids.add(ext_id)

                    loc_data = self.parse_location(location)

                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("DOM extraction found no jobs")
                try:
                    body_preview = driver.execute_script(
                        "return document.body ? document.body.innerText.substring(0, 500) : ''"
                    )
                    logger.info(f"Page preview: {body_preview}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"DOM extraction error: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver, current_page):
        """Navigate to next page in Jibe/iCIMS AngularJS SPA."""
        try:
            # Method 1: Click next button
            clicked = driver.execute_script("""
                var nextSelectors = [
                    'a[aria-label="Next"]', 'button[aria-label="Next"]',
                    '[class*="pagination"] [class*="next"] a',
                    '[class*="pagination"] [class*="next"] button',
                    'a[class*="next-page"]', 'button[class*="next"]',
                    'a[rel="next"]', 'li.next a',
                    '[class*="pagination"] li:last-child a'
                ];

                for (var i = 0; i < nextSelectors.length; i++) {
                    try {
                        var btn = document.querySelector(nextSelectors[i]);
                        if (btn && btn.offsetParent !== null) {
                            btn.click();
                            return true;
                        }
                    } catch(e) {}
                }

                // Try numbered page
                var nextPage = """ + str(current_page + 1) + """;
                var pageLinks = document.querySelectorAll('[class*="pagination"] a, [class*="pager"] a');
                for (var i = 0; i < pageLinks.length; i++) {
                    if (pageLinks[i].innerText.trim() === String(nextPage)) {
                        pageLinks[i].click();
                        return true;
                    }
                }

                return false;
            """)

            if clicked:
                logger.info(f"Clicked next page button for page {current_page + 1}")
                time.sleep(5)
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                return True

            # Method 2: URL-based pagination
            next_page = current_page + 1
            next_url = f"{self.base_url}/jobs?limit=100&page={next_page}&location=India"
            logger.info(f"Navigating to page {next_page} via URL")
            driver.get(next_url)
            time.sleep(8)

            # Check if page has jobs
            has_content = driver.execute_script("""
                return document.body && document.body.innerText.trim().length > 200;
            """)

            if has_content:
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                return True

            return False
        except Exception as e:
            logger.error(f"Pagination error: {str(e)}")
            return False


if __name__ == "__main__":
    scraper = CventScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

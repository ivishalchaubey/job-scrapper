from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('cars24_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class CARS24Scraper:
    def __init__(self):
        self.company_name = "CARS24"
        self.url = "https://careers.cars24.com/"
        self.base_url = 'https://careers.cars24.com'

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
        """Scrape CARS24 jobs from Next.js SPA."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Wait for job cards to appear in the grid
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'div[class*="job"], div[class*="card"], div[class*="opening"], '
                        'div[class*="position"], div[class*="listing"], div[class*="career"]'
                    ))
                )
                logger.info("Job cards detected on CARS24 page")
            except Exception as e:
                logger.warning(f"Timeout waiting for job cards: {str(e)}, using fallback wait")
                time.sleep(10)

            # Additional wait for Next.js hydration and API calls
            time.sleep(5)

            # Scroll to trigger lazy loading
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try to extract from __NEXT_DATA__ first
            next_data_jobs = driver.execute_script("""
                try {
                    var nextData = document.getElementById('__NEXT_DATA__');
                    if (nextData) {
                        var data = JSON.parse(nextData.textContent);
                        var props = data.props || {};
                        var pageProps = props.pageProps || {};

                        var possibleKeys = ['jobs', 'openings', 'positions', 'careers',
                                            'allJobs', 'jobListings', 'jobList'];
                        for (var i = 0; i < possibleKeys.length; i++) {
                            var key = possibleKeys[i];
                            if (pageProps[key] && Array.isArray(pageProps[key])) {
                                return pageProps[key];
                            }
                        }

                        // Deep search for job arrays
                        function findJobsArray(obj, depth) {
                            if (depth > 4 || !obj) return null;
                            if (Array.isArray(obj) && obj.length > 0 && typeof obj[0] === 'object') {
                                var first = obj[0];
                                if (first.title || first.name || first.job_title || first.position ||
                                    first.designation) {
                                    return obj;
                                }
                            }
                            if (typeof obj === 'object' && !Array.isArray(obj)) {
                                var keys = Object.keys(obj);
                                for (var j = 0; j < keys.length; j++) {
                                    var result = findJobsArray(obj[keys[j]], depth + 1);
                                    if (result) return result;
                                }
                            }
                            return null;
                        }
                        return findJobsArray(pageProps, 0);
                    }
                } catch(e) {}
                return null;
            """)

            if next_data_jobs and len(next_data_jobs) > 0:
                logger.info(f"Found {len(next_data_jobs)} jobs from __NEXT_DATA__")
                for idx, item in enumerate(next_data_jobs):
                    job = self._parse_next_data_job(item, idx)
                    if job:
                        all_jobs.append(job)
                if all_jobs:
                    logger.info(f"Extracted {len(all_jobs)} jobs from __NEXT_DATA__")
                    return all_jobs

            # DOM-based extraction with pagination
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

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _parse_next_data_job(self, item, idx):
        """Parse a single job from __NEXT_DATA__."""
        if not isinstance(item, dict):
            return None

        title = (item.get('title', '') or item.get('name', '') or
                 item.get('job_title', '') or item.get('designation', '') or
                 item.get('position', '') or '').strip()
        if isinstance(title, dict):
            title = title.get('rendered', '') or str(title)
        if not title or len(title) < 3:
            return None

        location = (item.get('location', '') or item.get('city', '') or
                     item.get('office', '') or '').strip()
        if isinstance(location, list) and location:
            location = ', '.join(location) if all(isinstance(l, str) for l in location) else str(location[0])

        apply_url = item.get('apply_url', '') or item.get('url', '') or item.get('link', '') or ''
        if not apply_url:
            slug = item.get('slug', '') or item.get('id', '')
            if slug:
                apply_url = f"{self.base_url}/job/{slug}"
            else:
                apply_url = self.url
        if apply_url and apply_url.startswith('/'):
            apply_url = f"{self.base_url}{apply_url}"

        job_id = str(item.get('id', '') or item.get('job_id', '') or
                      item.get('requisitionId', '') or f"cars24_{idx}")
        department = str(item.get('department', '') or item.get('team', '') or
                         item.get('function', '') or '')
        employment_type = str(item.get('employment_type', '') or item.get('type', '') or '')
        description = str(item.get('description', '') or item.get('content', '') or '')[:3000]
        experience = str(item.get('experience', '') or item.get('experience_level', '') or '')

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
            'posted_date': str(item.get('posted_date', '') or item.get('date', '') or
                              item.get('created_at', '') or ''),
            'job_function': str(item.get('job_function', '') or ''),
            'experience_level': experience,
            'salary_range': '',
            'remote_type': str(item.get('remote_type', '') or item.get('work_mode', '') or ''),
            'status': 'active'
        }

    def _extract_jobs_from_dom(self, driver, scraped_ids):
        """Extract jobs from CARS24 DOM using JavaScript."""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Job cards in a grid layout
                var cards = document.querySelectorAll(
                    'div[class*="job-card"], div[class*="jobCard"], a[class*="job-card"], ' +
                    'div[class*="career-card"], div[class*="opening-card"], ' +
                    'div[class*="position-card"], div[class*="listing-card"], ' +
                    'div[class*="card"][class*="job"], li[class*="job"], ' +
                    'div[class*="grid"] > div, div[class*="Grid"] > div'
                );

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var title = '';
                    var url = '';
                    var location = '';
                    var department = '';

                    var titleEl = card.querySelector(
                        'h2, h3, h4, [class*="title"], [class*="Title"], ' +
                        '[class*="name"], [class*="heading"], [class*="designation"]'
                    );
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

                    var locEl = card.querySelector(
                        '[class*="location"], [class*="Location"], [class*="city"], [class*="place"]'
                    );
                    if (locEl) location = locEl.innerText.trim();
                    if (!location) {
                        var text = card.innerText || '';
                        var cities = ['Gurgaon', 'Gurugram', 'Bangalore', 'Bengaluru', 'Mumbai',
                                      'Delhi', 'Hyderabad', 'Chennai', 'Pune', 'Noida', 'India'];
                        var lines = text.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            for (var k = 0; k < cities.length; k++) {
                                if (lines[j].indexOf(cities[k]) !== -1) {
                                    location = lines[j].trim();
                                    break;
                                }
                            }
                            if (location) break;
                        }
                    }

                    var deptEl = card.querySelector(
                        '[class*="department"], [class*="team"], [class*="category"], [class*="function"]'
                    );
                    if (deptEl) department = deptEl.innerText.trim();

                    if (url) seen[url] = true;
                    results.push({title: title, url: url || '', location: location, department: department});
                }

                // Strategy 2: Links with job-related href patterns
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll(
                        'a[href*="/job"], a[href*="/career"], a[href*="/opening"], ' +
                        'a[href*="/position"], a[href*="/role"]'
                    );
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var text = link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (text.length < 5 || text.length > 200 || seen[href]) continue;
                        if (href) seen[href] = true;

                        var parent = link.closest('div, li, tr');
                        var loc = '';
                        var dept = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"]');
                            if (locEl && locEl !== link) loc = locEl.innerText.trim();
                            var deptEl = parent.querySelector('[class*="department"], [class*="team"]');
                            if (deptEl && deptEl !== link) dept = deptEl.innerText.trim();
                        }

                        results.push({title: text, url: href, location: loc, department: dept});
                    }
                }

                // Strategy 3: Generic link detection with job title keywords
                if (results.length === 0) {
                    var genLinks = document.querySelectorAll('a[href]');
                    var jobKeywords = ['engineer', 'manager', 'developer', 'analyst', 'designer',
                                       'architect', 'lead', 'specialist', 'consultant', 'director',
                                       'associate', 'executive', 'intern', 'product', 'data',
                                       'operations', 'marketing', 'sales', 'finance'];
                    for (var i = 0; i < genLinks.length; i++) {
                        var link = genLinks[i];
                        var text = link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (text.length < 5 || text.length > 200 || seen[href]) continue;
                        var lower = text.toLowerCase();
                        var isJob = false;
                        for (var j = 0; j < jobKeywords.length; j++) {
                            if (lower.indexOf(jobKeywords[j]) !== -1) { isJob = true; break; }
                        }
                        if (!isJob) continue;
                        if (href) seen[href] = true;
                        results.push({title: text, url: href, location: '', department: ''});
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

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

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
                        'apply_url': url or self.url,
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
                (By.XPATH, '//button[contains(text(), "View More")]'),
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
    scraper = CARS24Scraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('rippling_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class RipplingScraper:
    def __init__(self):
        self.company_name = 'Rippling'
        self.url = 'https://www.rippling.com/en-GB/careers/open-roles'

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
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'

    def _is_india_job(self, location, title=''):
        """Check if a job is India-based."""
        india_keywords = [
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi', 'hyderabad',
            'chennai', 'pune', 'kolkata', 'gurgaon', 'gurugram', 'noida',
            'ahmedabad', 'jaipur', 'lucknow', 'kochi', 'indore'
        ]
        text = (location + ' ' + title).lower()
        return any(kw in text for kw in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape India jobs from Rippling's Next.js SPA careers page."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            driver.get(self.url)
            time.sleep(10)

            # Wait for Next.js SPA to render role cards
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        '[class*="role"], [class*="Role"], [class*="job"], [class*="Job"], [class*="position"], a[href*="/open-roles/"]'))
                )
            except Exception:
                logger.warning("Timeout waiting for role cards, proceeding with extraction")

            # Try to filter by India location if filter UI is available
            try:
                location_filters = driver.find_elements(By.XPATH,
                    '//button[contains(text(),"Location") or contains(text(),"location")]'
                    ' | //select[contains(@name,"location") or contains(@id,"location")]'
                    ' | //div[contains(@class,"filter") and contains(text(),"Location")]')
                if location_filters:
                    driver.execute_script("arguments[0].click();", location_filters[0])
                    time.sleep(2)
                    india_option = driver.find_elements(By.XPATH,
                        '//option[contains(text(),"India") or contains(text(),"Bangalore") or contains(text(),"Bengaluru")]'
                        ' | //li[contains(text(),"India") or contains(text(),"Bangalore") or contains(text(),"Bengaluru")]'
                        ' | //label[contains(text(),"India") or contains(text(),"Bangalore")]'
                        ' | //div[contains(text(),"India") or contains(text(),"Bangalore")]//input')
                    if india_option:
                        driver.execute_script("arguments[0].click();", india_option[0])
                        logger.info("Applied India location filter")
                        time.sleep(3)
            except Exception:
                logger.info("Could not apply location filter, will filter results manually")

            # Scroll to load all roles
            for i in range(10):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try clicking "Show More" buttons
            for _ in range(max_pages):
                try:
                    load_more = driver.find_elements(By.XPATH,
                        '//button[contains(text(),"Show More") or contains(text(),"Load More") or contains(text(),"View More") or contains(text(),"See All")]')
                    if load_more:
                        driver.execute_script("arguments[0].click();", load_more[0])
                        logger.info("Clicked show more button")
                        time.sleep(3)
                    else:
                        break
                except Exception:
                    break

            # Extract all jobs, then filter for India
            jobs = self._extract_jobs_js(driver)

            logger.info(f"Successfully scraped {len(jobs)} India jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs_js(self, driver):
        """Extract jobs from Rippling's Next.js SPA using JavaScript."""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Role cards on Rippling careers page
                var selectors = [
                    'a[href*="/open-roles/"]', 'a[href*="/careers/"]',
                    'div[class*="role-card"]', 'div[class*="RoleCard"]', 'div[class*="roleCard"]',
                    'div[class*="job-card"]', 'div[class*="JobCard"]',
                    'div[class*="position-card"]', 'div[class*="PositionCard"]',
                    'tr[class*="role"]', 'li[class*="role"]'
                ];

                for (var s = 0; s < selectors.length; s++) {
                    var cards = document.querySelectorAll(selectors[s]);
                    if (cards.length > 0) {
                        for (var i = 0; i < cards.length; i++) {
                            var card = cards[i];
                            var title = '';
                            var href = '';
                            var location = '';
                            var department = '';

                            if (card.tagName === 'A') {
                                href = card.href;
                                var titleEl = card.querySelector('h2, h3, h4, [class*="title"], [class*="Title"], [class*="name"], [class*="Name"]');
                                title = titleEl ? titleEl.innerText.trim().split('\\n')[0].trim() : card.innerText.trim().split('\\n')[0].trim();
                            } else {
                                var heading = card.querySelector('h2, h3, h4, [class*="title"], [class*="Title"]');
                                if (heading) title = heading.innerText.trim().split('\\n')[0].trim();
                                var link = card.querySelector('a[href]');
                                if (link) {
                                    href = link.href;
                                    if (!title) title = link.innerText.trim().split('\\n')[0].trim();
                                }
                            }

                            // Get location from card
                            var locEl = card.querySelector('[class*="location"], [class*="Location"], [class*="city"], [class*="City"]');
                            if (locEl) location = locEl.innerText.trim();
                            if (!location) {
                                // Check for location in card text
                                var cardText = card.innerText;
                                var lines = cardText.split('\\n');
                                for (var l = 0; l < lines.length; l++) {
                                    var line = lines[l].trim();
                                    if (line.includes('India') || line.includes('Bangalore') || line.includes('Bengaluru') ||
                                        line.includes('Mumbai') || line.includes('Delhi') || line.includes('Hyderabad') ||
                                        line.includes('Chennai') || line.includes('Pune')) {
                                        location = line;
                                        break;
                                    }
                                }
                            }

                            // Get department
                            var deptEl = card.querySelector('[class*="department"], [class*="Department"], [class*="team"], [class*="Team"], [class*="category"]');
                            if (deptEl) department = deptEl.innerText.trim();

                            if (title && title.length > 2 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({title: title, href: href, location: location, department: department});
                            }
                        }
                        if (results.length > 0) break;
                    }
                }

                // Strategy 2: Check __NEXT_DATA__ for Next.js server data
                if (results.length === 0) {
                    var nextData = document.querySelector('#__NEXT_DATA__');
                    if (nextData) {
                        try {
                            var data = JSON.parse(nextData.textContent);
                            var findJobs = function(obj) {
                                if (!obj || typeof obj !== 'object') return [];
                                if (Array.isArray(obj)) {
                                    var result = [];
                                    for (var i = 0; i < obj.length; i++) {
                                        if (obj[i] && obj[i].title && (obj[i].location || obj[i].city)) {
                                            result.push(obj[i]);
                                        }
                                        result = result.concat(findJobs(obj[i]));
                                    }
                                    return result;
                                }
                                var result = [];
                                for (var key in obj) {
                                    if (key === 'jobs' || key === 'roles' || key === 'positions' || key === 'openings') {
                                        if (Array.isArray(obj[key])) {
                                            result = result.concat(obj[key]);
                                        }
                                    }
                                    result = result.concat(findJobs(obj[key]));
                                }
                                return result;
                            };
                            var jobList = findJobs(data);
                            for (var j = 0; j < jobList.length; j++) {
                                var job = jobList[j];
                                var title = job.title || job.name || '';
                                var loc = job.location || job.city || '';
                                var dept = job.department || job.team || '';
                                var id = job.id || job.slug || j;
                                if (title && !seen[title + id]) {
                                    seen[title + id] = true;
                                    results.push({
                                        title: title,
                                        href: job.url || job.apply_url || (window.location.origin + '/en-GB/careers/open-roles/' + (job.slug || id)),
                                        location: loc,
                                        department: dept
                                    });
                                }
                            }
                        } catch(e) {}
                    }
                }

                // Strategy 3: Table rows or list items with role data
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tr, [role="row"]');
                    for (var i = 1; i < rows.length; i++) {
                        var cells = rows[i].querySelectorAll('td, [role="cell"]');
                        if (cells.length >= 2) {
                            var link = cells[0].querySelector('a');
                            var title = cells[0].innerText.trim().split('\\n')[0].trim();
                            var href = link ? link.href : '';
                            var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                            var dept = cells.length > 2 ? cells[2].innerText.trim() : '';
                            if (title.length > 3 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({title: title, href: href, location: location, department: dept});
                            }
                        }
                    }
                }

                // Strategy 4: Generic link extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/job"], a[href*="/role"], a[href*="/position"], a[href*="/career"]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim().split('\\n')[0].trim();
                        var href = links[i].href;
                        if (text.length > 3 && text.length < 200 && !seen[href]) {
                            if (href.includes('login') || href.includes('sign-in')) continue;
                            seen[href] = true;
                            var parent = links[i].closest('div, li, tr');
                            var loc = '';
                            var dept = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl) loc = locEl.innerText.trim();
                                var deptEl = parent.querySelector('[class*="department"], [class*="Department"]');
                                if (deptEl) dept = deptEl.innerText.trim();
                            }
                            results.push({title: text, href: href, location: loc, department: dept});
                        }
                    }
                }

                return results;
            """)

            if job_data:
                logger.info(f"JS extraction found {len(job_data)} total jobs")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '').strip()
                    href = jd.get('href', '').strip()
                    location = jd.get('location', '').strip()
                    department = jd.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue

                    # Filter for India jobs only
                    if not self._is_india_job(location, title):
                        continue

                    job_id = hashlib.md5((href or f"{title}_{idx}").encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location if location else 'India',
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': department,
                        'apply_url': href if href else self.url,
                        'posted_date': '',
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
        except Exception as e:
            logger.error(f"JS extraction failed: {e}")

        return jobs


if __name__ == "__main__":
    scraper = RipplingScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

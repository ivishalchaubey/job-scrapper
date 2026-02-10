from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import sys
from pathlib import Path
import os

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('starhealth_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class StarHealthScraper:
    def __init__(self):
        self.company_name = 'Star Health Insurance'
        self.url = 'https://starhealthcareers.peoplestrong.com/job/joblist'

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
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Star Health Insurance PeopleStrong careers page."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            driver.get(self.url)
            time.sleep(12)

            # Scroll to load all content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try to load more jobs if there's a "Load More" or "Show More" button
            for _ in range(max_pages):
                try:
                    load_more = driver.find_elements(By.XPATH,
                        '//button[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View More")]'
                        ' | //a[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View More")]')
                    if load_more:
                        driver.execute_script("arguments[0].click();", load_more[0])
                        logger.info("Clicked 'Load More' button")
                        time.sleep(3)
                    else:
                        break
                except Exception:
                    break

            # Extract jobs using JavaScript
            jobs = self._extract_jobs_js(driver)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs_js(self, driver):
        """Extract jobs from PeopleStrong page using JavaScript"""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Job cards with class containing 'job'
                var selectors = [
                    'div.job-card', 'div[class*="job-card"]', 'div[class*="jobCard"]',
                    'div[class*="job-list"]', 'div[class*="jobList"]',
                    'li[class*="job"]', 'div.card[class*="job"]',
                    'div[class*="position"]', 'div[class*="opening"]',
                    'div[class*="vacancy"]'
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

                            var heading = card.querySelector('h1, h2, h3, h4, h5, a[href*="/job/"]');
                            if (heading) {
                                title = heading.innerText.trim().split('\\n')[0].trim();
                                if (heading.tagName === 'A') href = heading.href;
                            }
                            if (!title) {
                                var firstLink = card.querySelector('a');
                                if (firstLink) {
                                    title = firstLink.innerText.trim().split('\\n')[0].trim();
                                    href = firstLink.href;
                                }
                            }
                            if (!href) {
                                var jobLink = card.querySelector('a[href*="/job/"], a[href*="jobdetail"], a[href*="job-detail"]');
                                if (jobLink) href = jobLink.href;
                            }

                            var locEl = card.querySelector('[class*="location"], [class*="Location"], [data-field="location"]');
                            if (locEl) location = locEl.innerText.trim();

                            var deptEl = card.querySelector('[class*="department"], [class*="Department"], [class*="category"], [data-field="department"]');
                            if (deptEl) department = deptEl.innerText.trim();

                            if (title && title.length > 2 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({title: title, href: href, location: location, department: department});
                            }
                        }
                        if (results.length > 0) break;
                    }
                }

                // Strategy 2: Links with job-related hrefs
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/job/"], a[href*="jobdetail"], a[href*="job-detail"]');
                    for (var i = 0; i < links.length; i++) {
                        var link = links[i];
                        var text = link.innerText.trim().split('\\n')[0].trim();
                        var href = link.href;
                        if (text.length > 3 && text.length < 200 && !seen[text + href]) {
                            seen[text + href] = true;
                            var parent = link.closest('div, li, tr');
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

                // Strategy 3: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tr, div[role="row"]');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        var cells = row.querySelectorAll('td, div[role="cell"]');
                        if (cells.length >= 2) {
                            var titleCell = cells[0];
                            var link = titleCell.querySelector('a');
                            var title = titleCell.innerText.trim().split('\\n')[0].trim();
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

                return results;
            """)

            if job_data:
                logger.info(f"JS extraction found {len(job_data)} jobs")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '')
                    href = jd.get('href', '')
                    location = jd.get('location', '')
                    department = jd.get('department', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5((href or f"{title}_{idx}").encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
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
    scraper = StarHealthScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

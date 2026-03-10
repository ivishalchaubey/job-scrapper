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

logger = setup_logger('lucastvs_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class LucasTVSScraper:
    def __init__(self):
        self.company_name = "Lucas TVS"
        self.url = "https://chroma.tcsapps.com/webhcm/LTVS/careers?jobLevelSearch=experienced"

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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Lucas TVS TCS Chroma careers page."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Try both experienced and fresher listings
            urls_to_scrape = [
                self.url,
                f"{self.url}?jobLevelSearch=experienced",
                f"{self.url}?jobLevelSearch=fresher"
            ]

            seen_ids = set()

            for scrape_url in urls_to_scrape:
                logger.info(f"Navigating to: {scrape_url}")
                driver.get(scrape_url)

                # TCS Chroma is an AngularJS SPA — wait for JS render
                logger.info("Waiting 10s for TCS Chroma SPA to render...")
                time.sleep(10)

                # Scroll to trigger lazy-loaded content
                for i in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)

                # Extract jobs from this page
                page_jobs = self._extract_jobs_js(driver)
                for job in page_jobs:
                    if job['external_id'] not in seen_ids:
                        seen_ids.add(job['external_id'])
                        jobs.append(job)

                logger.info(f"Extracted {len(page_jobs)} jobs from {scrape_url} (total unique: {len(jobs)})")

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs_js(self, driver):
        """Extract jobs from TCS Chroma page using JavaScript."""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: DataTable rows (TCS Chroma often uses DataTables)
                var rows = document.querySelectorAll('table tbody tr, table tr');
                for (var i = 0; i < rows.length; i++) {
                    var row = rows[i];
                    var cells = row.querySelectorAll('td');
                    if (cells.length >= 2) {
                        var title = '';
                        var location = '';
                        var experience = '';
                        var department = '';
                        var href = '';

                        // First cell is typically title
                        var link = cells[0].querySelector('a');
                        if (link) {
                            title = link.innerText.trim();
                            href = link.href;
                        } else {
                            title = cells[0].innerText.trim().split('\\n')[0].trim();
                        }

                        // Remaining cells: location, experience, department
                        if (cells.length > 1) location = cells[1].innerText.trim();
                        if (cells.length > 2) experience = cells[2].innerText.trim();
                        if (cells.length > 3) department = cells[3].innerText.trim();

                        // Find any link in the row if not found
                        if (!href) {
                            var anyLink = row.querySelector('a[href]');
                            if (anyLink) href = anyLink.href;
                        }

                        if (title && title.length > 2 && !seen[title + href]) {
                            seen[title + href] = true;
                            results.push({
                                title: title, href: href, location: location,
                                experience: experience, department: department
                            });
                        }
                    }
                }

                // Strategy 2: Job cards / list items
                if (results.length === 0) {
                    var selectors = [
                        '.job-list', '.job-card', '.card', '.opening',
                        'div[class*="job"]', 'div[class*="career"]',
                        'div[class*="opening"]', 'div[class*="position"]',
                        '.ng-scope'
                    ];
                    for (var s = 0; s < selectors.length; s++) {
                        var cards = document.querySelectorAll(selectors[s]);
                        if (cards.length > 0) {
                            for (var j = 0; j < cards.length; j++) {
                                var card = cards[j];
                                var title = '';
                                var href = '';
                                var location = '';
                                var department = '';
                                var experience = '';

                                var heading = card.querySelector('h1, h2, h3, h4, h5, a');
                                if (heading) {
                                    title = heading.innerText.trim().split('\\n')[0].trim();
                                    if (heading.tagName === 'A') href = heading.href;
                                }
                                if (!href) {
                                    var aTag = card.querySelector('a[href]');
                                    if (aTag) href = aTag.href;
                                }

                                var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl) location = locEl.innerText.trim();

                                var deptEl = card.querySelector('[class*="department"], [class*="Department"]');
                                if (deptEl) department = deptEl.innerText.trim();

                                var expEl = card.querySelector('[class*="experience"], [class*="Experience"]');
                                if (expEl) experience = expEl.innerText.trim();

                                if (title && title.length > 2 && !seen[title + href]) {
                                    seen[title + href] = true;
                                    results.push({
                                        title: title, href: href, location: location,
                                        experience: experience, department: department
                                    });
                                }
                            }
                            if (results.length > 0) break;
                        }
                    }
                }

                // Strategy 3: Links with job/career-related hrefs (fallback)
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var k = 0; k < links.length; k++) {
                        var l = links[k];
                        var text = l.innerText.trim().split('\\n')[0].trim();
                        var lhref = l.href || '';
                        if (text.length > 3 && text.length < 200 &&
                            (lhref.includes('job') || lhref.includes('career') || lhref.includes('opening') || lhref.includes('position')) &&
                            !seen[text + lhref]) {
                            seen[text + lhref] = true;
                            var parent = l.closest('div, li, tr, td');
                            var loc = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl) loc = locEl.innerText.trim();
                            }
                            results.push({
                                title: text, href: lhref, location: loc,
                                experience: '', department: ''
                            });
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
                    experience = jd.get('experience', '')

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
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found on TCS Chroma page")

        except Exception as e:
            logger.error(f"JS extraction failed: {e}")

        return jobs


if __name__ == "__main__":
    scraper = LucasTVSScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['experience_level']}")

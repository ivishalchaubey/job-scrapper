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

logger = setup_logger('waaree_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class WaareeScraper:
    def __init__(self):
        self.company_name = 'Waaree Energies'
        self.url = 'https://waaree.zohorecruit.com/jobs/careers'

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
        """Scrape jobs from Waaree Energies Zoho Recruit careers page."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)

            # Zoho Recruit uses Lyte framework with dynamic loading
            logger.info("Waiting 12s for Zoho Recruit SPA to render...")
            time.sleep(12)

            # Scroll to load all content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Handle pagination — Zoho Recruit may have page navigation
            page = 1
            while page <= max_pages:
                page_jobs = self._extract_jobs_js(driver)
                if page_jobs:
                    jobs.extend(page_jobs)
                    logger.info(f"Page {page}: extracted {len(page_jobs)} jobs (total: {len(jobs)})")

                # Try to go to the next page
                has_next = self._go_to_next_page(driver)
                if not has_next:
                    break
                page += 1
                time.sleep(3)

            # Deduplicate by external_id
            seen_ids = set()
            unique_jobs = []
            for job in jobs:
                if job['external_id'] not in seen_ids:
                    seen_ids.add(job['external_id'])
                    unique_jobs.append(job)
            jobs = unique_jobs

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _go_to_next_page(self, driver):
        """Try to navigate to the next page."""
        try:
            next_btn = driver.find_elements(By.XPATH,
                '//a[contains(@class,"next") or contains(text(),"Next") or contains(text(),">>")]'
                ' | //button[contains(@class,"next") or contains(text(),"Next")]'
                ' | //li[contains(@class,"next")]/a')
            if next_btn:
                driver.execute_script("arguments[0].click();", next_btn[0])
                logger.info("Clicked 'Next' pagination button")
                return True

            # Try "Load More" / "Show More"
            load_more = driver.find_elements(By.XPATH,
                '//button[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View More")]'
                ' | //a[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View More")]')
            if load_more:
                driver.execute_script("arguments[0].click();", load_more[0])
                logger.info("Clicked 'Load More' button")
                return True

            return False
        except Exception:
            return False

    def _extract_jobs_js(self, driver):
        """Extract jobs from Zoho Recruit page using JavaScript."""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Zoho Recruit-specific selectors
                var selectors = [
                    '.crmJobItem', '.crmJobTitle', '.job-item',
                    '[class*="crmJobItem"]', '[class*="crmJobList"] > div',
                    '[class*="crmJobList"] > li',
                    'div[class*="job-card"]', 'div[class*="jobCard"]',
                    'div[class*="job-item"]', 'div[class*="jobItem"]',
                    'div[class*="careers-job"]', 'div[class*="position-card"]',
                    'div[class*="opening"]', 'div[class*="vacancy"]'
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
                            var experience = '';

                            // Title: look for heading, .crmJobTitle, or first link
                            var titleEl = card.querySelector('.crmJobTitle, h1, h2, h3, h4, h5, a[href*="job"]');
                            if (titleEl) {
                                title = titleEl.innerText.trim().split('\\n')[0].trim();
                                if (titleEl.tagName === 'A') href = titleEl.href;
                            }
                            if (!title) {
                                var firstLink = card.querySelector('a');
                                if (firstLink) {
                                    title = firstLink.innerText.trim().split('\\n')[0].trim();
                                    href = firstLink.href;
                                }
                            }
                            if (!href) {
                                var jobLink = card.querySelector('a[href*="job"], a[href*="career"], a[href*="opening"]');
                                if (jobLink) href = jobLink.href;
                                else {
                                    var anyLink = card.querySelector('a[href]');
                                    if (anyLink) href = anyLink.href;
                                }
                            }

                            // Location
                            var locEl = card.querySelector('[class*="location"], [class*="Location"], [class*="city"], [class*="place"]');
                            if (locEl) location = locEl.innerText.trim();

                            // Department
                            var deptEl = card.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="team"]');
                            if (deptEl) department = deptEl.innerText.trim();

                            // Experience
                            var expEl = card.querySelector('[class*="experience"], [class*="Experience"], [class*="exp"]');
                            if (expEl) experience = expEl.innerText.trim();

                            if (title && title.length > 2 && title.length < 300 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({
                                    title: title, href: href, location: location,
                                    department: department, experience: experience
                                });
                            }
                        }
                        if (results.length > 0) break;
                    }
                }

                // Strategy 2: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        var cells = row.querySelectorAll('td');
                        if (cells.length >= 2) {
                            var titleCell = cells[0];
                            var link = titleCell.querySelector('a');
                            var title = titleCell.innerText.trim().split('\\n')[0].trim();
                            var href = link ? link.href : '';
                            var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                            var department = cells.length > 2 ? cells[2].innerText.trim() : '';
                            var experience = cells.length > 3 ? cells[3].innerText.trim() : '';
                            if (title.length > 3 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({
                                    title: title, href: href, location: location,
                                    department: department, experience: experience
                                });
                            }
                        }
                    }
                }

                // Strategy 3: Links with job-related hrefs
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/job"], a[href*="career"], a[href*="opening"]');
                    for (var i = 0; i < links.length; i++) {
                        var l = links[i];
                        var text = l.innerText.trim().split('\\n')[0].trim();
                        var lhref = l.href;
                        if (text.length > 3 && text.length < 200 && !seen[text + lhref]) {
                            seen[text + lhref] = true;
                            var parent = l.closest('div, li, tr');
                            var loc = '';
                            var dept = '';
                            var exp = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl && locEl !== l) loc = locEl.innerText.trim();
                                var deptEl = parent.querySelector('[class*="department"], [class*="Department"]');
                                if (deptEl && deptEl !== l) dept = deptEl.innerText.trim();
                                var expEl = parent.querySelector('[class*="experience"], [class*="Experience"]');
                                if (expEl && expEl !== l) exp = expEl.innerText.trim();
                            }
                            results.push({
                                title: text, href: lhref, location: loc,
                                department: dept, experience: exp
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
                logger.warning("No jobs found on Zoho Recruit page")

        except Exception as e:
            logger.error(f"JS extraction failed: {e}")

        return jobs


if __name__ == "__main__":
    scraper = WaareeScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['experience_level']}")

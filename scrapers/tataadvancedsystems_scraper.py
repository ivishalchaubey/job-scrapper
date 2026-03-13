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
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('tataadvancedsystems_scraper')

class TataAdvancedSystemsScraper:
    def __init__(self):
        self.company_name = "Tata Advanced Systems"
        self.url = "https://chroma.tcsapps.com/webhcm/tslt/careers"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

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
        """Scrape jobs from Tata Advanced Systems TCS Chroma careers page."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)

            # TCS Chroma is an AngularJS SPA — wait for JS render
            logger.info("Waiting 10s for AngularJS SPA to render...")
            time.sleep(10)

            # Scroll to trigger any lazy-loaded content
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Extract jobs from the rendered DOM
            jobs = self._extract_jobs_js(driver)

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

                        // Find any link in the row if not found in first cell
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

                // Strategy 3: Parse body text for job-like entries (fallback)
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var k = 0; k < links.length; k++) {
                        var l = links[k];
                        var text = l.innerText.trim().split('\\n')[0].trim();
                        var href = l.href || '';
                        if (text.length > 3 && text.length < 200 &&
                            (href.includes('job') || href.includes('career') || href.includes('opening') || href.includes('position')) &&
                            !seen[text + href]) {
                            seen[text + href] = true;
                            var parent = l.closest('div, li, tr, td');
                            var loc = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl) loc = locEl.innerText.trim();
                            }
                            results.push({
                                title: text, href: href, location: loc,
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
    scraper = TataAdvancedSystemsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['experience_level']}")

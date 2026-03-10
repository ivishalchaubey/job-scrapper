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

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('xiaomi_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class XiaomiScraper:
    def __init__(self):
        self.company_name = "Xiaomi"
        self.url = "https://www.linkedin.com/company/xiaomi-india/jobs/?viewAsMember=true"

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
        """Scrape jobs from Xiaomi Param.ai careers page (Nuxt.js SPA)."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)

            # Param.ai is a Nuxt.js SPA — wait for full render
            logger.info("Waiting 15s for Nuxt.js SPA to render...")
            time.sleep(15)

            # Scroll to load all content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try to click Load More / Show More buttons
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

            # Strategy 1: Try to extract from Nuxt.js __NUXT__ state
            nuxt_jobs = self._extract_from_nuxt(driver)
            if nuxt_jobs:
                jobs.extend(nuxt_jobs)
                logger.info(f"Extracted {len(nuxt_jobs)} jobs from __NUXT__ state")
            else:
                # Strategy 2: DOM extraction
                dom_jobs = self._extract_jobs_dom(driver)
                jobs.extend(dom_jobs)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_from_nuxt(self, driver):
        """Try to extract job data from Nuxt.js __NUXT__ state."""
        jobs = []

        try:
            nuxt_data = driver.execute_script("return window.__NUXT__")
            if not nuxt_data:
                logger.info("No __NUXT__ data found")
                return jobs

            logger.info("Found __NUXT__ data, parsing for job listings...")

            # Recursively search for job-like data in the NUXT state
            job_entries = self._find_jobs_in_nuxt(nuxt_data)

            for idx, entry in enumerate(job_entries):
                title = entry.get('title', '') or entry.get('job_title', '') or entry.get('name', '')
                location = entry.get('location', '') or entry.get('city', '') or entry.get('job_location', '')
                department = entry.get('department', '') or entry.get('category', '') or entry.get('team', '')
                href = entry.get('url', '') or entry.get('apply_url', '') or entry.get('link', '')
                job_id_raw = entry.get('id', '') or entry.get('job_id', '') or entry.get('slug', '')

                if not title or len(title) < 3:
                    continue

                if isinstance(location, dict):
                    location = location.get('name', '') or location.get('city', '')
                if isinstance(department, dict):
                    department = department.get('name', '')

                job_id = str(job_id_raw) if job_id_raw else hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
                city, state, country = self.parse_location(str(location))

                if href and not href.startswith('http'):
                    href = f"https://xiaomi.app.param.ai{href}" if href.startswith('/') else href

                jobs.append({
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': str(title),
                    'description': '',
                    'location': str(location),
                    'city': city,
                    'state': state,
                    'country': country,
                    'employment_type': '',
                    'department': str(department),
                    'apply_url': href if href else self.url,
                    'posted_date': '',
                    'job_function': str(department),
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                })

        except Exception as e:
            logger.warning(f"__NUXT__ extraction failed: {e}")

        return jobs

    def _find_jobs_in_nuxt(self, data, depth=0):
        """Recursively search NUXT state for arrays of job-like objects."""
        results = []
        if depth > 10:
            return results

        if isinstance(data, list):
            # Check if this looks like a list of job objects
            if len(data) > 0 and isinstance(data[0], dict):
                sample = data[0]
                job_keys = {'title', 'job_title', 'name', 'position', 'designation'}
                if any(k in sample for k in job_keys):
                    return data
            for item in data:
                found = self._find_jobs_in_nuxt(item, depth + 1)
                if found:
                    results.extend(found)

        elif isinstance(data, dict):
            for key, value in data.items():
                found = self._find_jobs_in_nuxt(value, depth + 1)
                if found:
                    results.extend(found)

        return results

    def _extract_jobs_dom(self, driver):
        """Extract jobs from DOM elements."""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Job card elements
                var selectors = [
                    '.job-card', '.job-listing', '[class*="job-card"]', '[class*="jobCard"]',
                    '[class*="job-list"]', '[class*="position-card"]',
                    'div[class*="opening"]', 'div[class*="vacancy"]',
                    'a[href*="job"]'
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
                                title = card.innerText.trim().split('\\n')[0].trim();
                                href = card.href;
                            } else {
                                var heading = card.querySelector('h1, h2, h3, h4, h5, a');
                                if (heading) {
                                    title = heading.innerText.trim().split('\\n')[0].trim();
                                    if (heading.tagName === 'A') href = heading.href;
                                }
                            }
                            if (!href) {
                                var aTag = card.querySelector('a[href]');
                                if (aTag) href = aTag.href;
                            }

                            var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl) location = locEl.innerText.trim();

                            var deptEl = card.querySelector('[class*="department"], [class*="Department"], [class*="category"]');
                            if (deptEl) department = deptEl.innerText.trim();

                            if (title && title.length > 2 && title.length < 200 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({title: title, href: href, location: location, department: department});
                            }
                        }
                        if (results.length > 0) break;
                    }
                }

                // Strategy 2: Links with job-related hrefs
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/job"], a[href*="/jobs/"], a[href*="position"]');
                    for (var i = 0; i < links.length; i++) {
                        var link = links[i];
                        var text = link.innerText.trim().split('\\n')[0].trim();
                        var lhref = link.href;
                        if (text.length > 3 && text.length < 200 && !seen[text + lhref]) {
                            seen[text + lhref] = true;
                            var parent = link.closest('div, li, tr');
                            var loc = '';
                            var dept = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl) loc = locEl.innerText.trim();
                                var deptEl = parent.querySelector('[class*="department"], [class*="Department"]');
                                if (deptEl) dept = deptEl.innerText.trim();
                            }
                            results.push({title: text, href: lhref, location: loc, department: dept});
                        }
                    }
                }

                // Strategy 3: Table rows
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
                logger.info(f"DOM extraction found {len(job_data)} jobs")
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
            else:
                logger.warning("No jobs found on Param.ai page via DOM extraction")

        except Exception as e:
            logger.error(f"DOM extraction failed: {e}")

        return jobs


if __name__ == "__main__":
    scraper = XiaomiScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

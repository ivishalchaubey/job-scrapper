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

logger = setup_logger('vedantu_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class VedantuScraper:
    def __init__(self):
        self.company_name = 'Vedantu'
        self.url = 'https://vedantu.zohorecruit.in/jobs/Careers'
        self.base_url = 'https://vedantu.zohorecruit.in'

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

            # Zoho Recruit Lyte UI needs time to render
            # Wait for Zoho-specific elements
            try:
                WebDriverWait(driver, 20).until(
                    lambda d: d.execute_script("""
                        return document.querySelectorAll('.ziabot-joblisting, .ziabot-job-listing-row, [class*="job-listing"], [class*="career-item"], a[href*="/jobs/Careers/"]').length > 0
                            || document.body.innerText.length > 500;
                    """)
                )
            except Exception:
                logger.info("Timeout waiting for Zoho Recruit elements, continuing anyway")

            # Scroll to load all listings
            for _ in range(5):
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

                // Strategy 1: Zoho Recruit Lyte UI - specific selectors
                var listings = document.querySelectorAll('.ziabot-joblisting, .ziabot-job-listing-row, [class*="ziabot-job"]');
                if (listings.length === 0) listings = document.querySelectorAll('[class*="job-listing-row"], [class*="jobListingRow"], [class*="career-listing"]');
                if (listings.length === 0) listings = document.querySelectorAll('[class*="cJobListing"], [class*="cjoblisting"], [class*="recruitJobListing"]');

                for (var i = 0; i < listings.length; i++) {
                    var listing = listings[i];
                    var titleEl = listing.querySelector('a[class*="job-title"], a[class*="jobTitle"], h2, h3, h4, [class*="title"], [class*="Title"], a');
                    if (!titleEl) continue;

                    var title = titleEl.innerText.trim().split('\\n')[0].trim();
                    if (!title || title.length < 3 || title.length > 200) continue;

                    var linkEl = listing.querySelector('a[href]');
                    var href = linkEl ? linkEl.href : '';
                    var key = href || title;
                    if (seen[key]) continue;
                    seen[key] = true;

                    var locEl = listing.querySelector('[class*="location"], [class*="Location"], [class*="city"], [class*="place"]');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var deptEl = listing.querySelector('[class*="department"], [class*="Department"], [class*="category"]');
                    var dept = deptEl ? deptEl.innerText.trim() : '';

                    var dateEl = listing.querySelector('[class*="date"], [class*="Date"], [class*="posted"]');
                    var date = dateEl ? dateEl.innerText.trim() : '';

                    // Parse location and department from listing text if not found
                    if (!location || !dept) {
                        var listingText = listing.innerText || '';
                        var lines = listingText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        for (var j = 0; j < lines.length; j++) {
                            var line = lines[j];
                            if (!location && line !== title && (line.includes('India') || line.includes('Bangalore') || line.includes('Mumbai') || line.includes('Delhi') || line.includes('Hyderabad') || line.includes('Chennai') || line.includes('Pune') || line.includes('Remote'))) {
                                location = line;
                            }
                        }
                    }

                    results.push({title: title, location: location, url: href || '', date: date, department: dept});
                }

                // Strategy 2: Zoho Recruit job title links
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="/jobs/Careers/"], a[href*="/jobs/"], a[href*="jobdetails"], a[class*="job-title"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var el = jobLinks[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var href = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (href.includes('login') || href.includes('sign-in') || href.includes('javascript:')) continue;
                        if (seen[href]) continue;
                        seen[href] = true;

                        var location = '';
                        var dept = '';
                        var parent = el.closest('li, div[class*="job"], div[class*="row"], article, tr, [class*="listing"]');
                        if (parent) {
                            var locEl2 = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl2 && locEl2 !== el) location = locEl2.innerText.trim();
                            var deptEl2 = parent.querySelector('[class*="department"], [class*="Department"]');
                            if (deptEl2 && deptEl2 !== el) dept = deptEl2.innerText.trim();
                        }
                        results.push({title: title, url: href, location: location, date: '', department: dept});
                    }
                }

                // Strategy 3: Card/list item based extraction
                if (results.length === 0) {
                    var cards = document.querySelectorAll('[class*="job-card"], [class*="jobCard"], [class*="career-card"], li[class*="job"], div[class*="job-item"], [class*="opening"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], a');
                        if (!titleEl) continue;
                        var title = titleEl.innerText.trim().split('\\n')[0].trim();
                        if (!title || title.length < 3 || title.length > 200) continue;

                        var linkEl = card.querySelector('a[href]');
                        var href = linkEl ? linkEl.href : '';
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        var locEl = card.querySelector('[class*="location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                        var dept = deptEl ? deptEl.innerText.trim() : '';

                        results.push({title: title, location: location, url: href || '', date: '', department: dept});
                    }
                }

                // Strategy 4: Table-based listings
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        if (row.querySelector('th')) continue;
                        var cells = row.querySelectorAll('td');
                        if (cells.length < 1) continue;

                        var linkEl = row.querySelector('a[href]');
                        var title = linkEl ? linkEl.innerText.trim().split('\\n')[0] : cells[0].innerText.trim().split('\\n')[0];
                        var href = linkEl ? linkEl.href : '';

                        if (!title || title.length < 3 || title.length > 200) continue;
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        var location = cells.length >= 2 ? cells[1].innerText.trim() : '';
                        var dept = cells.length >= 3 ? cells[2].innerText.trim() : '';

                        results.push({title: title, location: location, url: href || '', date: '', department: dept});
                    }
                }

                // Strategy 5: Generic link fallback
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var href = allLinks[i].href || '';
                        var text = (allLinks[i].innerText || '').trim();
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            if ((href.includes('/job') || href.includes('/career') || href.includes('/opening') || href.includes('/position') || href.includes('/Careers/')) && !seen[href]) {
                                if (!href.includes('login') && !href.includes('sign-in') && !href.includes('javascript:')) {
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
                    # Extract Zoho job ID from URL
                    if url and '/Careers/' in url:
                        import re
                        zoho_match = re.search(r'/Careers/(\d+)', url)
                        if zoho_match:
                            job_id = zoho_match.group(1)
                    elif url and '/jobs/' in url:
                        import re
                        zoho_match = re.search(r'/jobs/.*?/(\d+)', url)
                        if zoho_match:
                            job_id = zoho_match.group(1)

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
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Zoho Recruit pagination
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.CSS_SELECTOR, 'li.next a'),
                (By.CSS_SELECTOR, '[class*="pager"] a[class*="next"]'),
                (By.CSS_SELECTOR, '[class*="pagination"] a[class*="next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), "Load More")]'),
                (By.XPATH, '//button[contains(text(), "Load More")]'),
                (By.XPATH, '//button[contains(text(), "Show More")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] button[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="load-more"]'),
                (By.CSS_SELECTOR, 'a[class*="load-more"]'),
                (By.XPATH, '//a[contains(@class, "next")]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False


if __name__ == "__main__":
    scraper = VedantuScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

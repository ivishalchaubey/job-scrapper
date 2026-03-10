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

logger = setup_logger('tatatechnologies_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class TataTechnologiesScraper:
    def __init__(self):
        self.company_name = "Tata Technologies"
        self.url = "https://tatatechnologies.ripplehire.com/candidate/?token=pUMIYomQw46RCgLl0Cyq&lang=en&source=CAREERSITE#list/bu=INDIA"

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
        jobs = []
        driver = None
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)

            # RippleHire is a jQuery-based SPA. Wait for initial page shell to load,
            # then wait for AJAX calls to populate job listings.
            time.sleep(8)

            # Wait for jQuery to finish loading and AJAX to complete
            try:
                WebDriverWait(driver, 20).until(
                    lambda d: d.execute_script(
                        "return (typeof jQuery !== 'undefined') ? jQuery.active === 0 : true"
                    )
                )
                logger.info("jQuery AJAX calls completed")
            except Exception as e:
                logger.warning(f"jQuery wait timeout: {str(e)}")

            # Additional wait for DOM rendering after AJAX
            time.sleep(5)

            # Scroll to trigger any lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try to extract jobs from the RippleHire DOM
            scraped_ids = set()
            page_num = 1

            while page_num <= max_pages:
                logger.info(f"Extracting jobs from page {page_num}")
                page_jobs = self._extract_jobs(driver, scraped_ids)

                if not page_jobs and page_num == 1:
                    # Retry with longer wait on first page
                    logger.warning("No jobs found on first attempt, retrying with longer wait...")
                    time.sleep(10)
                    # Try clicking any "View Openings" or "Search" button
                    self._click_search_or_view(driver)
                    time.sleep(8)
                    page_jobs = self._extract_jobs(driver, scraped_ids)

                if not page_jobs:
                    logger.info(f"No jobs found on page {page_num}, stopping pagination")
                    break

                jobs.extend(page_jobs)
                logger.info(f"Page {page_num}: {len(page_jobs)} jobs (total: {len(jobs)})")

                if not self._go_to_next_page(driver):
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

    def _click_search_or_view(self, driver):
        """Click any search/view openings button on RippleHire portal."""
        try:
            driver.execute_script("""
                var buttons = document.querySelectorAll('button, a.btn, input[type="submit"], a[class*="btn"]');
                for (var i = 0; i < buttons.length; i++) {
                    var txt = (buttons[i].innerText || buttons[i].value || '').toLowerCase().trim();
                    if (txt.includes('search') || txt.includes('view') || txt.includes('opening') ||
                        txt.includes('find') || txt.includes('browse') || txt.includes('job')) {
                        buttons[i].click();
                        return true;
                    }
                }
                // Also try hash-based navigation for RippleHire
                if (window.location.hash === '' || window.location.hash === '#') {
                    window.location.hash = '#openings';
                }
                return false;
            """)
            logger.info("Clicked search/view button or navigated to openings hash")
        except Exception as e:
            logger.warning(f"Could not click search button: {str(e)}")

    def _extract_jobs(self, driver, scraped_ids):
        """Extract job listings from RippleHire SPA DOM."""
        jobs = []
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: RippleHire specific selectors - job cards/tiles
                var jobCards = document.querySelectorAll(
                    '.opening-card, .job-card, .job-item, .job-listing, ' +
                    'div[class*="opening"], div[class*="job-card"], div[class*="jobCard"], ' +
                    'div[class*="vacancy"], div[class*="position-card"], ' +
                    'tr[class*="opening"], tr[class*="job"], ' +
                    'li[class*="opening"], li[class*="job"]'
                );

                if (jobCards.length > 0) {
                    for (var i = 0; i < jobCards.length; i++) {
                        var card = jobCards[i];
                        var text = (card.innerText || '').trim();
                        if (text.length < 5) continue;

                        var titleEl = card.querySelector(
                            'h2, h3, h4, .title, .job-title, [class*="title"], ' +
                            '[class*="designation"], [class*="position-name"], a[class*="title"]'
                        );
                        var title = titleEl ? titleEl.innerText.trim() : '';
                        if (!title) {
                            title = text.split('\\n')[0].trim();
                        }
                        if (!title || title.length < 3 || title.length > 200) continue;

                        var linkEl = card.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';

                        var location = '';
                        var department = '';
                        var experience = '';
                        var employment_type = '';
                        var posted_date = '';

                        // Parse text lines for metadata
                        var lines = text.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            var line = lines[j].trim();
                            if (!line) continue;

                            // Location detection
                            if (line.match(/Mumbai|Pune|Bangalore|Bengaluru|Jamshedpur|Chennai|Hyderabad|Delhi|Noida|Gurgaon|Gurugram|India|Kolkata/i)) {
                                if (!location) location = line;
                            }
                            // Experience detection
                            if (line.match(/\\d+\\s*(\\+|-)\\s*(years?|yrs?)/i) || line.match(/experience/i)) {
                                if (!experience) experience = line;
                            }
                            // Employment type
                            if (line.match(/^(Full[\\s-]?Time|Part[\\s-]?Time|Contract|Permanent|Intern|Temporary)$/i)) {
                                employment_type = line;
                            }
                            // Date detection
                            if (line.match(/\\d{1,2}\\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/i) ||
                                line.match(/\\d{4}-\\d{2}-\\d{2}/)) {
                                if (!posted_date) posted_date = line;
                            }
                        }

                        // Try to extract department from specific elements
                        var deptEl = card.querySelector(
                            '[class*="department"], [class*="dept"], [class*="function"], ' +
                            '[class*="category"], [class*="team"]'
                        );
                        if (deptEl) department = deptEl.innerText.trim();

                        // Try location-specific element
                        var locEl = card.querySelector(
                            '[class*="location"], [class*="city"], [class*="place"]'
                        );
                        if (locEl && !location) location = locEl.innerText.trim();

                        var key = url || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        results.push({
                            title: title,
                            url: url,
                            location: location,
                            department: department,
                            experience: experience,
                            employment_type: employment_type,
                            posted_date: posted_date
                        });
                    }
                }

                // Strategy 2: Table-based layout (common in RippleHire)
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, .table tbody tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        var cells = row.querySelectorAll('td');
                        if (cells.length < 2) continue;

                        var title = cells[0].innerText.trim();
                        if (!title || title.length < 3) continue;

                        var linkEl = row.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';

                        var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                        var department = cells.length > 2 ? cells[2].innerText.trim() : '';
                        var experience = cells.length > 3 ? cells[3].innerText.trim() : '';

                        var key = url || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        results.push({
                            title: title,
                            url: url,
                            location: location,
                            department: department,
                            experience: experience,
                            employment_type: '',
                            posted_date: ''
                        });
                    }
                }

                // Strategy 3: Any links with job-related hrefs
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll(
                        'a[href*="opening"], a[href*="job"], a[href*="position"], ' +
                        'a[href*="apply"], a[href*="vacancy"], a[href*="career"]'
                    );
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var text = link.innerText.trim();
                        if (text.length < 5 || text.length > 200) continue;
                        // Skip navigation links
                        var lower = text.toLowerCase();
                        if (lower === 'apply' || lower === 'view' || lower === 'home' ||
                            lower === 'login' || lower === 'register' || lower === 'sign in') continue;

                        var href = link.href;
                        if (seen[href]) continue;
                        seen[href] = true;

                        var parent = link.closest('div, tr, li');
                        var parentText = parent ? parent.innerText : text;
                        var location = '';
                        var pLines = parentText.split('\\n');
                        for (var j = 0; j < pLines.length; j++) {
                            if (pLines[j].match(/Mumbai|Pune|Bangalore|Bengaluru|Jamshedpur|Chennai|India/i)) {
                                location = pLines[j].trim();
                                break;
                            }
                        }

                        results.push({
                            title: text.split('\\n')[0].trim(),
                            url: href,
                            location: location,
                            department: '',
                            experience: '',
                            employment_type: '',
                            posted_date: ''
                        });
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    experience = jdata.get('experience', '').strip()
                    employment_type = jdata.get('employment_type', '').strip()
                    posted_date = jdata.get('posted_date', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    # Generate job ID
                    job_id = f"tatatech_{idx}"
                    if url:
                        # Try to extract ID from URL
                        id_match = re.search(r'(?:opening|job|position)[/=](\w+)', url)
                        if id_match:
                            job_id = id_match.group(1)
                        else:
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue
                    scraped_ids.add(ext_id)

                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found in DOM extraction")
                # Debug: log page state
                try:
                    body_preview = driver.execute_script(
                        "return document.body ? document.body.innerText.substring(0, 500) : ''"
                    )
                    logger.info(f"Page body preview: {body_preview}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to the next page of results in RippleHire."""
        try:
            clicked = driver.execute_script("""
                // RippleHire pagination - look for next/pagination buttons
                var nextBtn = document.querySelector(
                    'a[class*="next"], button[class*="next"], ' +
                    'li.next a, .pagination .next a, ' +
                    'a[aria-label="Next"], button[aria-label="Next"], ' +
                    '[class*="pagination"] a:last-child'
                );
                if (nextBtn && nextBtn.offsetParent !== null) {
                    nextBtn.click();
                    return true;
                }

                // Try numbered pagination - find current active and click next
                var activePages = document.querySelectorAll(
                    '.pagination .active, [class*="pagination"] .active, ' +
                    '[class*="page-item"].active'
                );
                if (activePages.length > 0) {
                    var active = activePages[0];
                    var nextSibling = active.nextElementSibling;
                    if (nextSibling) {
                        var link = nextSibling.querySelector('a') || nextSibling;
                        link.click();
                        return true;
                    }
                }

                // Load more button
                var loadMoreBtn = document.querySelector(
                    'button[class*="load-more"], a[class*="load-more"], ' +
                    'button[class*="show-more"], a[class*="show-more"]'
                );
                if (loadMoreBtn && loadMoreBtn.offsetParent !== null) {
                    loadMoreBtn.click();
                    return true;
                }

                return false;
            """)

            if clicked:
                logger.info("Navigated to next page")
                time.sleep(5)
                return True

            logger.info("No next page button found")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False


if __name__ == "__main__":
    scraper = TataTechnologiesScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

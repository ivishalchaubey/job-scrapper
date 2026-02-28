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

logger = setup_logger('schaeffler_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class SchaefflerScraper:
    def __init__(self):
        self.company_name = 'Schaeffler India'
        self.url = 'https://jobs.schaeffler.com/?locale=en_US'
        self.base_url = 'https://jobs.schaeffler.com'

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
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Auto-detect failed: {str(e)}, trying explicit path")
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
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(5)

            # Accept cookies - Schaeffler has an "Accept All Cookies" button
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var i = 0; i < btns.length; i++) {
                        var txt = (btns[i].innerText || '').trim().toLowerCase();
                        if (txt.includes('accept all')) {
                            btns[i].click();
                            break;
                        }
                    }
                """)
                time.sleep(2)
            except:
                pass

            # Wait for web components to hydrate (schaeffler-search, schaeffler-search-list, schaeffler-job-item)
            # These are Stencil.js web components with shadow DOM
            logger.info("Waiting for web components to load...")
            time.sleep(15)

            # Schaeffler uses deeply nested shadow DOM:
            # document -> schaeffler-search.shadowRoot -> schaeffler-search-list.shadowRoot -> schaeffler-job-item[].shadowRoot
            # Each page loads 30 items; pagination is via "Load more" button

            seen_urls = set()
            for page in range(max_pages):
                page_jobs = self._extract_jobs(driver)
                # Deduplicate: Load More appends to DOM, so filter already-seen jobs
                new_jobs = []
                for job in page_jobs:
                    url = job.get('apply_url', '')
                    if url not in seen_urls:
                        seen_urls.add(url)
                        new_jobs.append(job)

                if not new_jobs:
                    break
                all_jobs.extend(new_jobs)
                logger.info(f"Page {page + 1}: {len(new_jobs)} new jobs (total: {len(all_jobs)})")

                if page < max_pages - 1:
                    if not self._load_more(driver):
                        break

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver):
        """Extract jobs from deeply nested shadow DOM web components."""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Navigate shadow DOM: schaeffler-search -> schaeffler-search-list -> schaeffler-job-item[]
                var search = document.querySelector('schaeffler-search');
                if (!search || !search.shadowRoot) return results;

                var searchList = search.shadowRoot.querySelector('schaeffler-search-list');
                if (!searchList || !searchList.shadowRoot) return results;

                var jobItems = searchList.shadowRoot.querySelectorAll('schaeffler-job-item');

                for (var i = 0; i < jobItems.length; i++) {
                    var item = jobItems[i];
                    if (!item.shadowRoot) continue;

                    var sr = item.shadowRoot;

                    // Each job item has an <a class="search"> link wrapping a card
                    var link = sr.querySelector('a.search, a[href*="job-invite"], a[href*="job/"]');
                    if (!link) continue;

                    var href = link.getAttribute('href') || '';
                    if (!href || seen[href]) continue;
                    seen[href] = true;

                    // Extract title from the title element or link text
                    var titleEl = sr.querySelector('[class*="title"], h2, h3, h4, .name');
                    var title = titleEl ? titleEl.innerText.trim() : '';
                    if (!title) {
                        // Parse from link text - format: "NEW\\nTitle\\nDEPARTMENT\\n..."
                        var linkText = link.innerText.trim();
                        var lines = linkText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        // Skip "New" label if present
                        var startIdx = 0;
                        if (lines.length > 0 && lines[0].toLowerCase() === 'new') startIdx = 1;
                        if (lines.length > startIdx) title = lines[startIdx];
                    }

                    if (!title || title.length < 3) continue;

                    // Extract other fields from the card text
                    var fullText = (link.innerText || '').trim();
                    var lines = fullText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                    // Typical format: [New, Title, Department, Level, Type, Location(s)]
                    var department = '';
                    var jobType = '';
                    var location = '';

                    // Find location - usually last non-empty lines, contains city/country names
                    // Department usually comes right after title
                    var startIdx = 0;
                    if (lines.length > 0 && lines[0].toLowerCase() === 'new') startIdx = 1;

                    if (lines.length > startIdx + 1) department = lines[startIdx + 1];
                    // Remove "+1" or "+2" suffixes from department
                    department = department.replace(/\\s*\\+\\d+$/, '');

                    // Location is typically the last meaningful line
                    for (var j = lines.length - 1; j >= 0; j--) {
                        var line = lines[j];
                        // Skip common non-location labels
                        if (line.toLowerCase() === 'new' || line === title ||
                            line === department || line.toLowerCase().includes('full-time') ||
                            line.toLowerCase().includes('part-time') || line.toLowerCase().includes('professional') ||
                            line.toLowerCase().includes('engineer') || line.toLowerCase().includes('others') ||
                            line.toLowerCase().includes('intern') || line.toLowerCase().includes('student')) continue;
                        // If it looks like a location (has comma or known city patterns)
                        if (line.length > 1) {
                            location = line;
                            break;
                        }
                    }

                    results.push({
                        title: title,
                        url: href,
                        location: location,
                        department: department
                    });
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Shadow DOM extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Extract job ID from URL like /job-invite/40424/?locale=en_US
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if 'job-invite/' in url:
                        parts = url.split('job-invite/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url or self.url,
                        'location': location,
                        'department': department,
                        'employment_type': '',
                        'description': '',
                        'posted_date': '',
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            if not jobs:
                logger.warning("No jobs found on this page")

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _load_more(self, driver):
        """Click the Load More button inside the shadow DOM to get more jobs."""
        try:
            # Get current job count before clicking
            old_count = driver.execute_script("""
                var search = document.querySelector('schaeffler-search');
                if (!search || !search.shadowRoot) return 0;
                var searchList = search.shadowRoot.querySelector('schaeffler-search-list');
                if (!searchList || !searchList.shadowRoot) return 0;
                return searchList.shadowRoot.querySelectorAll('schaeffler-job-item').length;
            """)

            # Click the Load More button (schaeffler-button inside search-list shadow)
            clicked = driver.execute_script("""
                var search = document.querySelector('schaeffler-search');
                if (!search || !search.shadowRoot) return false;
                var searchList = search.shadowRoot.querySelector('schaeffler-search-list');
                if (!searchList || !searchList.shadowRoot) return false;

                // The Load More button is a schaeffler-button in the footer
                var loadMoreBtn = searchList.shadowRoot.querySelector('schaeffler-button, button[class*="load-more"]');
                if (loadMoreBtn) {
                    // schaeffler-button may need to be clicked via shadow DOM
                    if (loadMoreBtn.shadowRoot) {
                        var btn = loadMoreBtn.shadowRoot.querySelector('button');
                        if (btn) { btn.click(); return true; }
                    }
                    loadMoreBtn.click();
                    return true;
                }
                return false;
            """)

            if not clicked:
                logger.info("No Load More button found")
                return False

            # Wait for new items to load
            for _ in range(30):  # max 6s wait
                time.sleep(0.2)
                new_count = driver.execute_script("""
                    var search = document.querySelector('schaeffler-search');
                    if (!search || !search.shadowRoot) return 0;
                    var searchList = search.shadowRoot.querySelector('schaeffler-search-list');
                    if (!searchList || !searchList.shadowRoot) return 0;
                    return searchList.shadowRoot.querySelectorAll('schaeffler-job-item').length;
                """)
                if new_count > old_count:
                    logger.info(f"Load More: {old_count} -> {new_count} items")
                    time.sleep(1)  # Brief settle
                    return True

            return False
        except Exception as e:
            logger.error(f"Error loading more: {str(e)}")
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
            result['country'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = SchaefflerScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

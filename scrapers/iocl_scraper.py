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

logger = setup_logger('iocl_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class IOCLScraper:
    def __init__(self):
        self.company_name = 'Indian Oil Corporation'
        self.url = 'https://iocl.com/latest-job-opening'
        self.base_url = 'https://iocl.com'

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

            # IOCL uses Sucuri WAF which requires JS execution for cookie challenge.
            # Selenium handles this automatically. We load the page and wait for
            # the redirect/challenge to complete.
            driver.get(self.url)
            time.sleep(15)

            # Verify we got past the Sucuri challenge by checking for actual page content
            page_title = driver.title or ''
            if 'redirected' in page_title.lower() or 'sucuri' in page_title.lower():
                logger.info("Sucuri challenge detected, waiting for redirect...")
                time.sleep(10)

            # Check if we need to reload after cookie is set
            current_url = driver.current_url
            if 'iocl.com' not in current_url:
                logger.info("Reloading page after Sucuri challenge...")
                driver.get(self.url)
                time.sleep(10)

            # Scroll to load all content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Extract all recruitment notices from the page
            page_jobs = self._extract_jobs(driver)
            if page_jobs:
                all_jobs.extend(page_jobs)
                logger.info(f"Found {len(page_jobs)} recruitment notices")

            # Also check the apprenticeships page for more listings
            try:
                apprentice_url = 'https://iocl.com/apprenticeships'
                logger.info(f"Also checking apprenticeships page: {apprentice_url}")
                driver.get(apprentice_url)
                time.sleep(10)
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
                apprentice_jobs = self._extract_jobs(driver)
                if apprentice_jobs:
                    all_jobs.extend(apprentice_jobs)
                    logger.info(f"Found {len(apprentice_jobs)} apprenticeship notices")
            except Exception as e:
                logger.warning(f"Could not load apprenticeships page: {str(e)}")

            # Deduplicate by external_id
            seen_ids = set()
            unique_jobs = []
            for job in all_jobs:
                if job['external_id'] not in seen_ids:
                    seen_ids.add(job['external_id'])
                    unique_jobs.append(job)
            all_jobs = unique_jobs

            logger.info(f"Total unique jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver):
        jobs = []

        try:
            # Scroll page to ensure all content is loaded
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // IOCL page structure (from Wayback Machine analysis):
                // div.divscreeen1 > div.download > ul.job-list > li.liscreen > span > a[href] > strong
                // Each notice is a recruitment notification with a PDF link

                // Strategy 1: IOCL specific - job-list items
                var jobListItems = document.querySelectorAll('ul.job-list li.liscreen');
                if (jobListItems.length === 0) {
                    jobListItems = document.querySelectorAll('ul.job-list li');
                }
                for (var i = 0; i < jobListItems.length; i++) {
                    var li = jobListItems[i];
                    var link = li.querySelector('a[href]');
                    if (!link) continue;

                    var titleEl = link.querySelector('strong') || link;
                    var title = (titleEl.innerText || titleEl.textContent || '').trim();
                    // Clean up title - remove extra whitespace
                    title = title.replace(/\\s+/g, ' ').trim();
                    var href = link.href || '';

                    if (!title || title.length < 5) continue;
                    if (seen[title]) continue;
                    seen[title] = true;

                    results.push({title: title, url: href, date: ''});
                }

                // Strategy 2: divscreeen1 containers (alternate selector)
                if (results.length === 0) {
                    var divContainers = document.querySelectorAll('.divscreeen1');
                    for (var i = 0; i < divContainers.length; i++) {
                        var container = divContainers[i];
                        var links = container.querySelectorAll('a[href]');
                        for (var j = 0; j < links.length; j++) {
                            var link = links[j];
                            var titleEl = link.querySelector('strong') || link;
                            var title = (titleEl.innerText || titleEl.textContent || '').trim();
                            title = title.replace(/\\s+/g, ' ').trim();
                            var href = link.href || '';
                            if (!title || title.length < 5) continue;
                            if (seen[title]) continue;
                            seen[title] = true;
                            results.push({title: title, url: href, date: ''});
                        }
                    }
                }

                // Strategy 3: Look for PDF links and recruitment-related links anywhere
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href*=".pdf"], a[href*="LatestJobOpening"], a[href*="recruitment"], a[href*="notification"]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var title = (link.innerText || link.textContent || '').trim();
                        title = title.replace(/\\s+/g, ' ').trim();
                        var href = link.href || '';

                        // Skip navigation/header/footer PDFs - only want job-related ones
                        if (href.includes('LatestJobOpening') ||
                            title.toLowerCase().includes('recruit') ||
                            title.toLowerCase().includes('requirement') ||
                            title.toLowerCase().includes('apprentice') ||
                            title.toLowerCase().includes('vacancy') ||
                            title.toLowerCase().includes('selection') ||
                            title.toLowerCase().includes('personnel') ||
                            title.toLowerCase().includes('engagement') ||
                            title.toLowerCase().includes('empanelment') ||
                            title.toLowerCase().includes('non-executive') ||
                            title.toLowerCase().includes('executive') ||
                            title.toLowerCase().includes('candidate')) {

                            if (!title || title.length < 5) continue;
                            if (seen[title]) continue;
                            seen[title] = true;
                            results.push({title: title, url: href, date: ''});
                        }
                    }
                }

                // Strategy 4: Broader fallback - any inner-main content links
                if (results.length === 0) {
                    var innerMain = document.querySelector('.inner-main');
                    if (innerMain) {
                        var links = innerMain.querySelectorAll('a[href]');
                        for (var i = 0; i < links.length; i++) {
                            var link = links[i];
                            var title = (link.innerText || link.textContent || '').trim();
                            title = title.replace(/\\s+/g, ' ').trim();
                            var href = link.href || '';
                            if (!title || title.length < 10) continue;
                            if (href.includes('javascript:') || href === '#') continue;
                            if (seen[title]) continue;
                            seen[title] = true;
                            results.push({title: title, url: href, date: ''});
                        }
                    }
                }

                // Strategy 5: Last resort - find any strong/b tags with recruitment text
                if (results.length === 0) {
                    var strongs = document.querySelectorAll('strong, b');
                    for (var i = 0; i < strongs.length; i++) {
                        var el = strongs[i];
                        var title = (el.innerText || el.textContent || '').trim();
                        title = title.replace(/\\s+/g, ' ').trim();
                        if (!title || title.length < 15) continue;
                        if (title.toLowerCase().includes('recruit') ||
                            title.toLowerCase().includes('requirement') ||
                            title.toLowerCase().includes('apprentice') ||
                            title.toLowerCase().includes('vacancy') ||
                            title.toLowerCase().includes('personnel')) {

                            if (seen[title]) continue;
                            seen[title] = true;

                            // Try to find parent link
                            var parentLink = el.closest('a');
                            var href = parentLink ? parentLink.href : '';
                            results.push({title: title, url: href, date: ''});
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} recruitment notices")
                seen_titles = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    date = jdata.get('date', '').strip()

                    if not title or len(title) < 5:
                        continue

                    # Deduplicate by title (recruitment notices have unique titles)
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    # Try to extract location from title (e.g. "at Haldia Refinery", "at Gujarat Refinery")
                    location = ''
                    title_lower = title.lower()
                    if ' at ' in title_lower:
                        loc_part = title.split(' at ')[-1].split(' vide ')[0].split(' against ')[0].strip()
                        if len(loc_part) < 100:
                            location = loc_part

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': '', 'employment_type': 'Government/PSU',
                        'description': f'IOCL Recruitment Notice: {title}',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        # IOCL lists all recruitment notices on a single page, no pagination needed
        return False

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str: return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1: result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str: result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = IOCLScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

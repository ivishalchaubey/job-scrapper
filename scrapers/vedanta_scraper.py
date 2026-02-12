from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('vedanta_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class VedantaScraper:
    def __init__(self):
        self.company_name = 'Vedanta Limited'
        self.url = 'https://vhr.darwinbox.in/ms/candidate/careers'

    def setup_driver(self):
        """Set up Chrome driver with anti-detection options"""
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
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Vedanta Limited DarwinBox careers page"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Load the careers page
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(12)

            # This is a /candidate/careers URL - look for allJobs link
            current_url = driver.current_url
            logger.info(f"Current URL after load: {current_url}")

            all_jobs_url = self._find_all_jobs_link(driver)
            if all_jobs_url:
                logger.info(f"Navigating to all jobs page: {all_jobs_url}")
                driver.get(all_jobs_url)
                time.sleep(12)
            else:
                logger.info("No allJobs link found, scraping current page")

            # Scroll to load all job tiles
            for i in range(5):
                driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                time.sleep(2)
            driver.execute_script('window.scrollTo(0, 0);')
            time.sleep(2)

            # Extract jobs
            page_jobs = self._scrape_darwinbox_jobs(driver)
            jobs.extend(page_jobs)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _find_all_jobs_link(self, driver):
        """Find the allJobs or Open Jobs link on a DarwinBox careers page"""
        try:
            all_jobs_url = driver.execute_script("""
                var links = document.querySelectorAll('a[href]');
                for (var i = 0; i < links.length; i++) {
                    var href = links[i].href || '';
                    if (href.includes('allJobs') || href.includes('all-jobs') || href.includes('openJobs')) {
                        return href;
                    }
                }
                // Also try clicking buttons/links with text like "Open Jobs", "View All"
                var allElements = document.querySelectorAll('a, button, span');
                for (var i = 0; i < allElements.length; i++) {
                    var text = (allElements[i].innerText || '').trim().toLowerCase();
                    if (text === 'open jobs' || text === 'view all jobs' || text === 'all jobs' || text === 'view all') {
                        if (allElements[i].href) return allElements[i].href;
                    }
                }
                return null;
            """)
            return all_jobs_url
        except Exception as e:
            logger.warning(f"Error finding allJobs link: {str(e)}")
            return None

    def _scrape_darwinbox_jobs(self, driver):
        """Extract jobs from the DarwinBox page using JavaScript"""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // DarwinBox v1 (/ms/candidate/careers) uses links like /ms/candidate/careers/{hash}
                var jobLinks = document.querySelectorAll('a[href]');
                for (var i = 0; i < jobLinks.length; i++) {
                    var link = jobLinks[i];
                    var href = link.href || '';
                    // Match /ms/candidate/careers/{hash} but exclude /careers itself, /careers/others
                    var match = href.match(/\\/ms\\/candidate\\/careers\\/([a-f0-9]{10,})/);
                    if (!match) {
                        // Also try /jobDetails/ pattern for v2
                        if (!href.includes('jobDetails')) continue;
                    }
                    // Skip non-job links
                    if (href.includes('/others')) continue;

                    var title = (link.innerText || '').trim().split('\\n')[0].trim();
                    if (title.length < 3 || title === 'View and Apply' || title === 'Apply' || title === 'apply here') continue;
                    if (seen[href]) continue;
                    seen[href] = true;

                    // Try to get location from sibling/parent elements
                    var location = '';
                    var row = link.closest('tr, div.job-row, div[class*="result"]');
                    if (row) {
                        var cells = row.querySelectorAll('td');
                        if (cells.length >= 2) {
                            // Table layout: title | department | location
                            for (var c = 1; c < cells.length; c++) {
                                var cellText = (cells[c].innerText || '').trim();
                                if (cellText.match(/India|Haryana|Gujarat|Maharashtra|Karnataka|Delhi|Tamil Nadu|Rajasthan|Odisha|Jharkhand|Chhattisgarh|Andhra Pradesh|Telangana|Kerala|Punjab|West Bengal|Uttar Pradesh|Bengaluru|Bangalore|Mumbai|Chennai|Hyderabad|Pune|Gurgaon|Noida/i)) {
                                    location = cellText;
                                }
                            }
                        }
                    }

                    results.push({
                        title: title,
                        url: href,
                        location: location,
                        experience: '',
                        employment_type: ''
                    });
                }

                // Fallback: try div.job-tile selectors for DarwinBox v2
                if (results.length === 0) {
                    var tiles = document.querySelectorAll('div.job-tile, div[class*="job-card"], div[class*="job-item"]');
                    for (var i = 0; i < tiles.length; i++) {
                        var tile = tiles[i];
                        var text = (tile.innerText || '').trim();
                        if (text.length < 5) continue;
                        var titleEl = tile.querySelector('span.job-title, .title-section, h3, h4, [class*="title"]');
                        var title = titleEl ? titleEl.innerText.trim() : text.split('\\n')[0].trim();
                        var linkEl = tile.querySelector('a[href*="jobDetails"], a[href*="/careers/"]');
                        var url = linkEl ? linkEl.href : '';
                        if (title.length >= 3 && title !== 'View and Apply' && !seen[url || title]) {
                            seen[url || title] = true;
                            results.push({title: title, url: url, location: '', experience: '', employment_type: ''});
                        }
                    }
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"DarwinBox extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    url = job_data.get('url', '')
                    location = job_data.get('location', '')
                    experience = job_data.get('experience', '')
                    employment_type = job_data.get('employment_type', '')

                    if not title:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    city, state, _ = self.parse_location(location)

                    job_id = f"vedanta_{idx}"
                    if url and 'jobDetails/' in url:
                        job_id = url.split('jobDetails/')[-1].split('?')[0]
                    elif url:
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': '',
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No job tiles found on DarwinBox page")

        except Exception as e:
            logger.error(f"DarwinBox extraction error: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]

        city = ''
        state = ''
        for part in parts:
            part_clean = part.strip()
            if part_clean == 'India':
                continue
            if '#' in part_clean or '_' in part_clean:
                if '(' in part_clean and ')' in part_clean:
                    state = part_clean.split('(')[-1].split(')')[0].strip()
                continue
            if '..+' in part_clean:
                continue
            if not city:
                city = part_clean
            elif not state:
                state = part_clean

        return city, state, 'India'


if __name__ == '__main__':
    scraper = VedantaScraper()
    results = scraper.scrape()
    print(f"Scraped {len(results)} jobs from {scraper.company_name}")
    for job in results[:5]:
        print(f"  - {job['title']} | {job['location']} | {job['apply_url']}")

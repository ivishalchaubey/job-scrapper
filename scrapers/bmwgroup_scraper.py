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

logger = setup_logger('bmwgroup_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class BMWGroupScraper:
    def __init__(self):
        self.company_name = 'BMW Group'
        self.url = 'https://www.bmwgroup.jobs/in/en/jobs.html'
        self.base_url = 'https://www.bmwgroup.jobs'
        # BMW AEM jobfinder API endpoint - fetches HTML fragments with job data
        self.api_path = '/in/en/jobs/_jcr_content/main/layoutcontainer_5337_1987237933/jobfinder30.jobfinder_table.content.html'

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

            # Wait for the page to load enough for XHR to work
            time.sleep(8)

            # BMW uses AEM jobfinder API that returns HTML fragments
            # Fetch jobs via XHR with India location filter
            # blockCount controls how many jobs per page (max ~50)
            jobs_per_page = 50

            for page in range(max_pages):
                row_index = page * jobs_per_page
                api_url = f"{self.api_path}?filterSearch=location_IN&rowIndex={row_index}&blockCount={jobs_per_page}"

                page_jobs = self._extract_jobs_from_api(driver, api_url)

                if not page_jobs:
                    # If India filter returns 0, try without filter for first page only
                    if page == 0:
                        logger.info("No India jobs with filter, trying without location filter")
                        api_url_no_filter = f"{self.api_path}?rowIndex=0&blockCount={jobs_per_page}"
                        page_jobs = self._extract_jobs_from_api(driver, api_url_no_filter)
                        if page_jobs:
                            logger.info(f"Found {len(page_jobs)} jobs without India filter (global results)")
                    if not page_jobs:
                        break

                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                # If we got fewer than requested, we've reached the end
                if len(page_jobs) < jobs_per_page:
                    break

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs_from_api(self, driver, api_url):
        """Fetch jobs from BMW AEM jobfinder API and parse the HTML response."""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var xhr = new XMLHttpRequest();
                xhr.open('GET', arguments[0], false);
                xhr.send();

                if (xhr.status !== 200) return [];

                var parser = new DOMParser();
                var doc = parser.parseFromString(xhr.responseText, 'text/html');

                var results = [];
                var wrappers = doc.querySelectorAll('.grp-jobfinder__wrapper[data-job-id]');

                for (var i = 0; i < wrappers.length; i++) {
                    var wrapper = wrappers[i];
                    var jobId = wrapper.getAttribute('data-job-id') || '';

                    // The refno div has all the data attributes
                    var refno = wrapper.querySelector('.grp-jobfinder-cell-refno');
                    var title = refno ? (refno.getAttribute('data-job-title') || '') : '';
                    var location = refno ? (refno.getAttribute('data-job-location') || '') : '';
                    var entity = refno ? (refno.getAttribute('data-job-legal-entity') || '') : '';
                    var field = refno ? (refno.getAttribute('data-job-field') || '') : '';
                    var jobType = refno ? (refno.getAttribute('data-job-type') || '') : '';
                    var postingDate = refno ? (refno.getAttribute('data-posting-date') || '') : '';

                    // Get the job URL
                    var linkEl = wrapper.querySelector('a.grp-jobfinder__link-jobdescription, a[href*="job-description"]');
                    var href = linkEl ? linkEl.getAttribute('href') : '';

                    if (title && title.length > 2) {
                        results.push({
                            jobId: jobId,
                            title: title,
                            location: location,
                            entity: entity,
                            field: field,
                            jobType: jobType,
                            postingDate: postingDate,
                            url: href
                        });
                    }
                }

                return results;
            """, api_url)

            if js_jobs:
                logger.info(f"API extraction found {len(js_jobs)} jobs")
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    location = jdata.get('location', '').strip()
                    job_id = jdata.get('jobId', '').strip()
                    url = jdata.get('url', '').strip()
                    field = jdata.get('field', '').strip()
                    job_type = jdata.get('jobType', '').strip()
                    posting_date = jdata.get('postingDate', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Format posting date from YYYYMMDD to YYYY-MM-DD
                    formatted_date = ''
                    if posting_date and len(posting_date) == 8:
                        formatted_date = f"{posting_date[:4]}-{posting_date[4:6]}-{posting_date[6:8]}"

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id or title, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url or self.url,
                        'location': location,
                        'department': field,
                        'employment_type': job_type,
                        'description': '',
                        'posted_date': formatted_date,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': field,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

        except Exception as e:
            logger.error(f"Error extracting jobs from API: {str(e)}")

        return jobs

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
    scraper = BMWGroupScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

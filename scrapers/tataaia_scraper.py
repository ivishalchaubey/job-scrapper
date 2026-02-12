from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import re
import os
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('tataaia_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class TataAIAScraper:
    def __init__(self):
        self.company_name = 'Tata AIA Life Insurance'
        self.url = 'https://tataaia.ripplehire.com/candidate/?token=sHL2jO0rtOvpftwOGDCp&source=CAREERSITE#list'

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
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _is_garbage_title(self, title):
        if not title or len(title) < 3:
            return True
        t = title.lower().strip()
        garbage = ['powered by', 'ripplehire', 'www.', '.com', 'privacy', 'terms',
                   'cookie', 'all rights', 'apply share', 'apply', 'share on',
                   'email your friends', 'post on x', 'view more', 'sign in',
                   'login', 'register', 'home', 'about', 'contact', 'filter',
                   'search', 'sort', 'job(s) found', 'loading', 'share']
        for pat in garbage:
            if t == pat or t.startswith(pat):
                return True
        if re.match(r'^\d+\s*[-\u2013]\s*\d+\s*(years?|yrs?)$', t, re.IGNORECASE):
            return True
        if re.match(r'^\d+$', t):
            return True
        if re.match(r'^\d+\s+opening', t, re.IGNORECASE):
            return True
        return False

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(15)

            logger.info(f"Current URL after load: {driver.current_url}")

            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            scraped_ids = set()
            page = 1
            while page <= max_pages:
                jobs = self._scrape_ripplehire_jobs(driver, scraped_ids)
                if jobs:
                    all_jobs.extend(jobs)
                    logger.info(f"Batch {page}: found {len(jobs)} new jobs, total: {len(all_jobs)}")

                clicked = self._click_view_more(driver)
                if not clicked:
                    break
                page += 1
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()

    def _click_view_more(self, driver):
        try:
            clicked = driver.execute_script("""
                var btn = document.querySelector('a.js-joblist-viewmore');
                if (btn && btn.offsetParent !== null) { btn.click(); return true; }
                var links = document.querySelectorAll('a, button');
                for (var i = 0; i < links.length; i++) {
                    var text = (links[i].innerText || '').trim().toLowerCase();
                    if (text === 'view more' || text === 'load more' || text === 'show more') {
                        if (links[i].offsetParent !== null) { links[i].click(); return true; }
                    }
                }
                return false;
            """)
            if clicked:
                time.sleep(3)
                return True
            return False
        except:
            return False

    def _scrape_ripplehire_jobs(self, driver, scraped_ids):
        jobs = []
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seenTitles = new Set();
                var jobTitleLinks = document.querySelectorAll('a.job-title');
                for (var i = 0; i < jobTitleLinks.length; i++) {
                    var link = jobTitleLinks[i];
                    var title = (link.innerText || '').trim();
                    if (!title || title.length < 3 || seenTitles.has(title)) continue;
                    seenTitles.add(title);
                    var href = link.getAttribute('href') || '';
                    var jobId = '';
                    var match = href.match(/job\\/([0-9]+)/);
                    if (match) jobId = match[1];
                    var card = link.closest('li');
                    var location = '';
                    var experience = '';
                    if (card) {
                        var locEl = card.querySelector('li.location-text');
                        if (locEl) location = (locEl.innerText || '').trim();
                        var listJobDiv = card.querySelector('div.row.list-job');
                        if (listJobDiv) {
                            var items = listJobDiv.querySelectorAll('ul > li');
                            if (items.length > 0) experience = (items[0].innerText || '').trim();
                        }
                    }
                    var fullUrl = '';
                    if (href && href.indexOf('#') === 0) {
                        fullUrl = window.location.origin + window.location.pathname + window.location.search + href;
                    } else if (href) { fullUrl = href; }
                    results.push({title: title, url: fullUrl, location: location, experience: experience, jobId: jobId});
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"RippleHire extraction found {len(js_jobs)} jobs")
                for jdx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    experience = jdata.get('experience', '').strip()
                    rh_job_id = jdata.get('jobId', '')

                    if self._is_garbage_title(title):
                        continue

                    job_id = f"tataaia_rh_{rh_job_id}" if rh_job_id else f"tataaia_{jdx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    location_parts = self.parse_location(location)
                    job_data = {
                        'external_id': ext_id,
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': '', 'employment_type': '', 'description': '',
                        'posted_date': '', 'city': location_parts.get('city', ''),
                        'state': location_parts.get('state', ''),
                        'country': location_parts.get('country', 'India'),
                        'job_function': '', 'experience_level': experience,
                        'salary_range': '', 'remote_type': '', 'status': 'active'
                    }
                    jobs.append(job_data)
                    scraped_ids.add(ext_id)

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")
        return jobs

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) == 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = TataAIAScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

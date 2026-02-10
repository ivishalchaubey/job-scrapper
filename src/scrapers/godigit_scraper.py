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
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('godigit_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class GoDigitScraper:
    def __init__(self):
        self.company_name = 'Go Digit Insurance'
        self.url = 'https://godigit.darwinbox.in/ms/candidatev2/main/careers/allJobs'

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
        """Scrape jobs from Go Digit Insurance DarwinBox careers page"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Load the allJobs page directly
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(12)

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

    def _scrape_darwinbox_jobs(self, driver):
        """Extract jobs from the DarwinBox allJobs page using JavaScript"""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var tiles = document.querySelectorAll('div.job-tile, div.jobs-section, div[class*="job-card"], div[class*="job-item"], div[class*="job-listing"]');
                if (tiles.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="jobDetails"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var link = jobLinks[i];
                        var container = link.closest('div[class]') || link.parentElement;
                        var text = (container.innerText || '').trim();
                        var title = text.split('\\n')[0].trim();
                        if (title.length >= 3 && title !== 'View and Apply' && title !== 'Apply') {
                            results.push({
                                title: title,
                                url: link.href,
                                location: '',
                                experience: '',
                                employment_type: ''
                            });
                        }
                    }
                    return results;
                }

                for (var i = 0; i < tiles.length; i++) {
                    var tile = tiles[i];
                    var text = (tile.innerText || '').trim();
                    if (text.length < 5) continue;

                    var titleEl = tile.querySelector('span.job-title, .title-section, h3, h4, [class*="title"]');
                    var title = titleEl ? titleEl.innerText.trim() : text.split('\\n')[0].trim();

                    var linkEl = tile.querySelector('a[href*="jobDetails"]');
                    var url = linkEl ? linkEl.href : '';

                    var lines = text.split('\\n');
                    var location = '';
                    var experience = '';
                    var employment_type = '';
                    for (var j = 0; j < lines.length; j++) {
                        var line = lines[j].trim();
                        if (line.includes('India') || line.includes('Haryana') || line.includes('Gujarat') ||
                            line.includes('Maharashtra') || line.includes('Karnataka') || line.includes('Goa') ||
                            line.includes('Delhi') || line.includes('Tamil Nadu') || line.includes('Rajasthan') ||
                            line.includes('Odisha') || line.includes('Jharkhand') || line.includes('Chhattisgarh') ||
                            line.includes('Andhra Pradesh') || line.includes('Telangana') || line.includes('Kerala') ||
                            line.includes('Punjab') || line.includes('West Bengal') || line.includes('Uttar Pradesh') ||
                            line.includes('Bengaluru') || line.includes('Bangalore') || line.includes('Mumbai') ||
                            line.includes('Chennai') || line.includes('Hyderabad') || line.includes('Pune')) {
                            location = line;
                        }
                        if (line.includes('Years') || line.includes('years')) {
                            experience = line;
                        }
                        if (line === 'Permanent' || line === 'Contract' || line === 'Probation' || line === 'Intern' || line === 'Full Time' || line === 'Part Time') {
                            employment_type = line;
                        }
                    }

                    if (title.length >= 3 && title !== 'View and Apply') {
                        results.push({
                            title: title,
                            url: url,
                            location: location,
                            experience: experience,
                            employment_type: employment_type
                        });
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

                    job_id = f"godigit_{idx}"
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
    scraper = GoDigitScraper()
    results = scraper.scrape()
    print(f"Scraped {len(results)} jobs from {scraper.company_name}")
    for job in results[:5]:
        print(f"  - {job['title']} | {job['location']} | {job['apply_url']}")

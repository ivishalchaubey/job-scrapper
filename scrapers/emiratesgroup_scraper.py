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

logger = setup_logger('emiratesgroup_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class EmiratesGroupScraper:
    def __init__(self):
        self.company_name = 'Emirates Group'
        self.url = 'https://www.emiratesgroupcareers.com/search-and-apply/'
        self.base_url = 'https://www.emiratesgroupcareers.com'

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
        """Scrape jobs from Emirates Group careers site.

        Emirates Group uses a custom jQuery + Avature platform. All jobs load on
        a single page with section.job-card elements. Each card has an id attribute
        that forms the job detail URL: /search-and-apply/{id}

        Cards have no <a> links - navigation uses JS click handlers.
        We extract all card data and construct URLs from the card id.
        """
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Wait for job cards to load
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'section.job-card'))
                )
                logger.info("Job cards loaded")
            except Exception:
                logger.warning("Timeout waiting for job cards, continuing...")

            time.sleep(5)

            # Scroll to ensure all cards are rendered (site loads all on one page)
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Extract all jobs using the Avature/custom platform selectors
            all_jobs = self._extract_jobs(driver)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver):
        """Extract jobs from Emirates Group custom Avature-based platform.

        DOM structure:
        - section.job-card (with id="NNNNN" for each job)
          - div.job-card__logo > img (brand logo, alt = brand name)
          - div.job-card__info
            - div.job-card__tags (featured pills etc.)
            - div.job-card__title > div (job title text)
            - div.job-card__subcategory (job category)
            - div.job-card__location_container
              - div.job-card__location (city, country)
            - div.job-card__date (closing date)
        """
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var cards = document.querySelectorAll('section.job-card');

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var id = card.id || '';

                    var titleEl = card.querySelector('.job-card__title');
                    var title = titleEl ? titleEl.innerText.trim() : '';

                    var locEl = card.querySelector('.job-card__location');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var dateEl = card.querySelector('.job-card__date');
                    var date = dateEl ? dateEl.innerText.trim() : '';

                    var subcatEl = card.querySelector('.job-card__subcategory');
                    var subcategory = subcatEl ? subcatEl.innerText.trim() : '';

                    var logoEl = card.querySelector('.job-card__logo img');
                    var brand = logoEl ? (logoEl.alt || '') : '';

                    if (title && title.length > 2 && id) {
                        results.push({
                            id: id,
                            title: title,
                            location: location,
                            date: date,
                            subcategory: subcategory,
                            brand: brand
                        });
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Extracted {len(js_jobs)} job cards from page")
                for jdata in js_jobs:
                    card_id = jdata.get('id', '')
                    title = jdata.get('title', '').strip()
                    location = jdata.get('location', '').strip()
                    date_str = jdata.get('date', '').strip()
                    subcategory = jdata.get('subcategory', '').strip()
                    brand = jdata.get('brand', '').strip()

                    if not title or not card_id:
                        continue

                    # Build apply URL from card ID
                    apply_url = f"{self.base_url}/search-and-apply/{card_id}"

                    # Parse closing date (format: "Closing date: DD Mon YYYY")
                    posted_date = ''
                    if date_str:
                        posted_date = date_str.replace('Closing date:', '').strip()

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(card_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': apply_url,
                        'location': location,
                        'department': subcategory,
                        'employment_type': '',
                        'description': f"Brand: {brand}" if brand else '',
                        'posted_date': posted_date,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', ''),
                        'job_function': subcategory,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        """Parse location string for Emirates Group jobs.

        Typical formats: 'Dubai, United Arab Emirates', 'Chennai, India', 'London, United Kingdom'
        """
        result = {'city': '', 'state': '', 'country': ''}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 2:
            result['country'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = EmiratesGroupScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

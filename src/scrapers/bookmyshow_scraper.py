from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import sys
from pathlib import Path
import os
import stat

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('bookmyshow_scraper')


class BookMyShowScraper:
    def __init__(self):
        self.company_name = 'BookMyShow'
        # Trakstar Hire platform
        self.url = 'https://bookmyshow.hire.trakstar.com/'

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

        driver_path = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

        try:
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"Service driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
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

            # Wait for Trakstar page to fully render
            time.sleep(12)

            # Wait for the openings list container
            wait = WebDriverWait(driver, 5)
            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "div.js-openings-list"
                )))
                logger.info("Found openings list container")
            except:
                logger.warning("Timeout waiting for div.js-openings-list, will try selectors anyway")

            jobs = self._scrape_page(driver)
            all_jobs.extend(jobs)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()

    def _scrape_page(self, driver):
        jobs = []
        scraped_ids = set()

        try:
            # Scroll down to ensure all cards are loaded
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

            # Trakstar platform selectors in priority order
            job_elements = []
            selectors = [
                "div.js-careers-page-job-list-item",
                "div.js-card.list-item",
                "div.js-card",
                "div.list-item-clickable",
            ]

            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Found {len(elements)} listings using: {selector}")
                        break
                except:
                    continue

            # Fallback: use JavaScript to extract directly from the Trakstar DOM
            if not job_elements:
                logger.info("No elements found with CSS selectors, trying JS extraction from Trakstar DOM")
                js_jobs = driver.execute_script("""
                    var results = [];
                    var cards = document.querySelectorAll('div.js-openings-list .js-card, div.opening-list .list-item');
                    if (cards.length === 0) {
                        cards = document.querySelectorAll('a[href*="/jobs/"]');
                    }
                    cards.forEach(function(card) {
                        var titleEl = card.querySelector('h3.js-job-list-opening-name, h3.rb-h3, h3');
                        var title = titleEl ? titleEl.innerText.trim() : '';
                        var linkEl = card.tagName === 'A' ? card : card.querySelector('a[href*="/jobs/"]');
                        var url = linkEl ? linkEl.href : '';
                        var cityEl = card.querySelector('span.meta-job-location-city');
                        var stateEl = card.querySelector('span.meta-job-location-state');
                        var countryEl = card.querySelector('span.meta-job-location-country');
                        var city = cityEl ? cityEl.innerText.trim() : '';
                        var state = stateEl ? stateEl.innerText.trim() : '';
                        var country = countryEl ? countryEl.innerText.trim() : '';
                        var deptEl = card.querySelector('div.js-job-list-opening-meta, div.rb-text-4');
                        var dept = deptEl ? deptEl.innerText.trim() : '';
                        if (title && url) {
                            results.push({
                                title: title,
                                url: url,
                                city: city,
                                state: state,
                                country: country,
                                department: dept
                            });
                        }
                    });
                    return results;
                """)

                if js_jobs:
                    logger.info(f"JS extraction found {len(js_jobs)} jobs")
                    for jl in js_jobs:
                        title = jl.get('title', '').strip()
                        url = jl.get('url', '').strip()
                        city = jl.get('city', '').strip()
                        state = jl.get('state', '').strip()
                        country = jl.get('country', '').strip() or 'India'
                        department = jl.get('department', '').strip()

                        if not title or not url:
                            continue

                        # Extract job ID from URL like /jobs/12345/
                        job_id = self._extract_job_id_from_url(url)

                        location_parts = [p for p in [city, state, country] if p]
                        location = ', '.join(location_parts)

                        job_data = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'apply_url': url,
                            'location': location,
                            'department': department,
                            'employment_type': '',
                            'description': '',
                            'posted_date': '',
                            'city': city,
                            'state': state,
                            'country': country if country else 'India',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': 'Remote' if 'remote' in location.lower() else '',
                            'status': 'active'
                        }
                        if job_data['external_id'] not in scraped_ids:
                            jobs.append(job_data)
                            scraped_ids.add(job_data['external_id'])
                            logger.info(f"JS Extracted: {title} | {location}")
                    return jobs

            # Process Selenium elements
            for idx, elem in enumerate(job_elements, 1):
                try:
                    job = self._extract_job(elem, driver, idx)
                    if job and job['external_id'] not in scraped_ids:
                        jobs.append(job)
                        scraped_ids.add(job['external_id'])
                        logger.info(f"Extracted: {job.get('title', 'N/A')} | {job.get('location', '')}")
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
        except Exception as e:
            logger.error(f"Error in _scrape_page: {str(e)}")
        return jobs

    def _extract_job_id_from_url(self, url):
        """Extract numeric job ID from Trakstar URL like /jobs/12345/"""
        try:
            parts = url.rstrip('/').split('/')
            for part in reversed(parts):
                if part.isdigit():
                    return part
            # Fallback: hash the URL
            return f"bms_{hashlib.md5(url.encode()).hexdigest()[:8]}"
        except:
            return f"bms_{hashlib.md5(url.encode()).hexdigest()[:8]}"

    def _extract_job(self, job_elem, driver, idx):
        try:
            title = ""
            job_url = ""
            city = ""
            state = ""
            country = ""
            department = ""

            # Extract title from h3.js-job-list-opening-name
            title_selectors = [
                "h3.js-job-list-opening-name",
                "h3.rb-h3",
                "h3",
            ]
            for sel in title_selectors:
                try:
                    elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                    title = elem.text.strip()
                    if title:
                        break
                except:
                    continue

            # Extract URL from anchor tag
            url_selectors = [
                "a[href*='/jobs/']",
                "a",
            ]
            for sel in url_selectors:
                try:
                    elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                    href = elem.get_attribute('href')
                    if href and '/jobs/' in href:
                        job_url = href
                        break
                    elif href and not job_url:
                        job_url = href
                except:
                    continue

            # If the card itself is wrapped in a link or is a link
            if not job_url:
                try:
                    parent_a = job_elem.find_element(By.XPATH, "./ancestor::a[@href]")
                    href = parent_a.get_attribute('href')
                    if href:
                        job_url = href
                except:
                    pass

            if not title:
                title = job_elem.text.strip().split('\n')[0]
            if not title:
                return None
            if not job_url:
                job_url = self.url

            # Extract location from specific Trakstar span elements
            try:
                city_elem = job_elem.find_element(By.CSS_SELECTOR, "span.meta-job-location-city")
                city = city_elem.text.strip()
            except:
                pass

            try:
                state_elem = job_elem.find_element(By.CSS_SELECTOR, "span.meta-job-location-state")
                state = state_elem.text.strip()
            except:
                pass

            try:
                country_elem = job_elem.find_element(By.CSS_SELECTOR, "span.meta-job-location-country")
                country = country_elem.text.strip()
            except:
                pass

            # Extract department
            try:
                dept_elem = job_elem.find_element(By.CSS_SELECTOR, "div.js-job-list-opening-meta")
                department = dept_elem.text.strip()
            except:
                try:
                    dept_elem = job_elem.find_element(By.CSS_SELECTOR, "div.rb-text-4")
                    department = dept_elem.text.strip()
                except:
                    pass

            location_parts = [p for p in [city, state, country] if p]
            location = ', '.join(location_parts)

            # Get job ID from URL
            job_id = self._extract_job_id_from_url(job_url)

            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': location,
                'department': department,
                'employment_type': '',
                'description': '',
                'posted_date': '',
                'city': city,
                'state': state,
                'country': country if country else 'India',
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': 'Remote' if 'remote' in location.lower() else '',
                'status': 'active'
            }

            if FETCH_FULL_JOB_DETAILS and job_url and job_url != self.url:
                try:
                    details = self._fetch_details(driver, job_url)
                    if details:
                        job_data.update(details)
                except:
                    pass

            return job_data
        except Exception as e:
            logger.error(f"Error in _extract_job: {str(e)}")
            return None

    def _fetch_details(self, driver, job_url):
        details = {}
        try:
            original = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(job_url)
            time.sleep(3)

            for sel in [".job-description", "[class*='description']", "[class*='detail']", "main"]:
                try:
                    elem = driver.find_element(By.CSS_SELECTOR, sel)
                    text = elem.text.strip()
                    if text and len(text) > 50:
                        details['description'] = text[:3000]
                        break
                except:
                    continue

            driver.close()
            driver.switch_to.window(original)
        except Exception as e:
            logger.error(f"Error fetching details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass
        return details


if __name__ == "__main__":
    scraper = BookMyShowScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

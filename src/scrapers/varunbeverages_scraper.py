from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import hashlib
import time
import sys
from pathlib import Path
import os
import stat

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('varunbeverages_scraper')


class VarunBeveragesScraper:
    def __init__(self):
        self.company_name = 'Varun Beverages'
        # Oracle HCM Cloud platform
        self.url = 'https://rjcorphcm-iacbiz.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs?location=India&locationId=300000000489931&locationLevel=country&mode=location'

    def setup_driver(self):
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')

        driver_path = ChromeDriverManager().install()
        driver_path_obj = Path(driver_path)
        if driver_path_obj.name != 'chromedriver':
            parent = driver_path_obj.parent
            actual_driver = parent / 'chromedriver'
            if actual_driver.exists():
                driver_path = str(actual_driver)
            else:
                for file in parent.rglob('chromedriver'):
                    if file.is_file() and not file.name.endswith('.zip'):
                        driver_path = str(file)
                        break

        try:
            current_permissions = os.stat(driver_path).st_mode
            os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            logger.warning(f"Could not set permissions: {str(e)}")

        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(60)  # Oracle Cloud pages can be slow
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
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(8)  # Oracle Cloud is slow to render

            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "[class*='job'], a[href*='/jobs/'], [class*='search-result']"
                )))
            except:
                logger.warning("Timeout waiting for listings")

            jobs = self._scrape_page(driver, wait)
            all_jobs.extend(jobs)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()

    def _scrape_page(self, driver, wait):
        jobs = []
        scraped_ids = set()

        try:
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

            job_elements = []
            selectors = [
                "[class*='job-card']",
                "[class*='search-result']",
                "a[href*='/jobs/']",
                "[role='listitem']",
                ".card",
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

            if not job_elements:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                job_links = [l for l in all_links if '/jobs/' in (l.get_attribute('href') or '') and l.text.strip() and len(l.text.strip()) > 5]
                if job_links:
                    job_elements = job_links

            for idx, elem in enumerate(job_elements, 1):
                try:
                    job = self._extract_job(elem, driver, wait, idx)
                    if job and job['external_id'] not in scraped_ids:
                        jobs.append(job)
                        scraped_ids.add(job['external_id'])
                        logger.info(f"Extracted: {job.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"Error {idx}: {str(e)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        return jobs

    def _extract_job(self, job_elem, driver, wait, idx):
        try:
            title = ""
            job_url = ""

            if job_elem.tag_name == 'a':
                title = job_elem.text.strip().split('\n')[0]
                job_url = job_elem.get_attribute('href')
            else:
                for sel in ["h2 a", "h3 a", "a[href*='/jobs/']", "a"]:
                    try:
                        elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                        title = elem.text.strip()
                        job_url = elem.get_attribute('href')
                        if title:
                            break
                    except:
                        continue

            if not title:
                title = job_elem.text.strip().split('\n')[0]
            if not title or not job_url:
                return None

            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

            location = ""
            for line in job_elem.text.split('\n')[1:]:
                line_s = line.strip()
                if any(c in line_s for c in ['India', 'Mumbai', 'Delhi', 'Noida', 'Gurgaon', 'Bangalore']):
                    location = line_s
                    break

            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': location,
                'department': '',
                'employment_type': '',
                'description': '',
                'posted_date': '',
                'city': '',
                'state': '',
                'country': 'India',
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            if FETCH_FULL_JOB_DETAILS and job_url:
                try:
                    details = self._fetch_details(driver, job_url)
                    if details:
                        job_data.update(details)
                except:
                    pass

            job_data.update(self.parse_location(job_data.get('location', '')))
            return job_data
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return None

    def _fetch_details(self, driver, job_url):
        details = {}
        try:
            original = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(job_url)
            time.sleep(5)

            for sel in [".job-description", "[class*='description']", "main"]:
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
            logger.error(f"Error: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass
        return details

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
    scraper = VarunBeveragesScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

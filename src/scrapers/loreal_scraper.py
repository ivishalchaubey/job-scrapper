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

logger = setup_logger('loreal_scraper')


class LorealScraper:
    def __init__(self):
        self.company_name = "L'Oreal"
        # India filter: 3_110_3=18031
        self.url = 'https://careers.loreal.com/en_US/jobs/SearchJobs/?3_110_3=18031'

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
            logger.warning(f"Could not set permissions on chromedriver: {str(e)}")

        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(SCRAPE_TIMEOUT)
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
            time.sleep(5)

            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, ".article, .article__header, [class*='job'], a[href*='JobDetail']"
                )))
                logger.info("Job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for job listings: {str(e)}")

            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                jobs = self._scrape_page(driver, wait)
                all_jobs.extend(jobs)
                logger.info(f"Page {current_page}: found {len(jobs)} jobs")

                if current_page < max_pages:
                    if not self._load_more(driver):
                        break
                    time.sleep(3)
                current_page += 1

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _load_more(self, driver):
        """Click 'View more results' button if available"""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            load_more_selectors = [
                (By.CSS_SELECTOR, "a[class*='viewMoreResults']"),
                (By.XPATH, "//a[contains(text(), 'View more')]"),
                (By.XPATH, "//button[contains(text(), 'View more')]"),
                (By.CSS_SELECTOR, ".pagination .next a"),
                (By.CSS_SELECTOR, "a.next"),
            ]

            for selector_type, selector_value in load_more_selectors:
                try:
                    btn = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info("Clicked 'View more results'")
                    return True
                except:
                    continue

            logger.info("No more results to load")
            return False
        except Exception as e:
            logger.error(f"Error loading more results: {str(e)}")
            return False

    def _scrape_page(self, driver, wait):
        jobs = []
        scraped_ids = set()

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            job_elements = []
            selectors = [
                ".article",
                "article",
                "[class*='article__header']",
                "a[href*='JobDetail']",
                ".job-listing",
                "[class*='job-result']",
            ]

            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Found {len(job_elements)} listings using selector: {selector}")
                        break
                except:
                    continue

            # Fallback: find all JobDetail links
            if not job_elements:
                all_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='JobDetail']")
                if all_links:
                    job_elements = all_links
                    logger.info(f"Fallback found {len(all_links)} job links")

            if not job_elements:
                logger.warning("Could not find job listings")
                return jobs

            for idx, job_elem in enumerate(job_elements, 1):
                try:
                    job_data = self._extract_job_from_element(job_elem, driver, wait, idx)
                    if job_data and job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job {len(jobs)}: {job_data.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        return jobs

    def _extract_job_from_element(self, job_elem, driver, wait, idx):
        try:
            title = ""
            job_url = ""

            tag_name = job_elem.tag_name
            if tag_name == 'a':
                title = job_elem.text.strip()
                job_url = job_elem.get_attribute('href')
            else:
                title_selectors = [
                    ".article__header__text__title a",
                    "h3 a", "h2 a", "h4 a",
                    "a[href*='JobDetail']",
                    ".job-title a",
                    "a"
                ]
                for selector in title_selectors:
                    try:
                        title_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip()
                        job_url = title_elem.get_attribute('href')
                        if title and job_url:
                            break
                    except:
                        continue

            if not title:
                text = job_elem.text.strip()
                if text:
                    title = text.split('\n')[0].strip()

            if not title or not job_url:
                return None

            # Extract job ID from URL (e.g., /JobDetail/232009)
            job_id = ""
            if 'JobDetail' in job_url:
                parts = job_url.split('/')
                for i, part in enumerate(parts):
                    if part == 'JobDetail' and i + 1 < len(parts):
                        # The job ID might be after the title slug
                        job_id = parts[-1].split('?')[0]
                        break
            if not job_id:
                job_id = f"loreal_{idx}_{hashlib.md5(job_url.encode()).hexdigest()[:8]}"

            # Extract location from element text
            location = ""
            try:
                all_text = job_elem.text
                lines = all_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if any(city in line for city in ['Mumbai', 'Delhi', 'Bangalore', 'Bengaluru', 'Chennai', 'Hyderabad', 'Pune', 'India', 'Gurugram', 'Noida']):
                        location = line
                        break
            except:
                pass

            # Extract posted date
            posted_date = ""
            try:
                all_text = job_elem.text
                lines = all_text.split('\n')
                for line in lines:
                    if 'Posted' in line:
                        posted_date = line.replace('Posted', '').strip()
                        break
            except:
                pass

            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': location,
                'department': '',
                'employment_type': '',
                'description': '',
                'posted_date': posted_date,
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
                    details = self._fetch_job_details(driver, job_url)
                    if details:
                        job_data.update(details)
                except Exception as e:
                    logger.warning(f"Could not fetch details for {title}: {str(e)}")

            location_parts = self.parse_location(job_data.get('location', ''))
            job_data.update(location_parts)

            return job_data

        except Exception as e:
            logger.error(f"Error extracting job data: {str(e)}")
            return None

    def _fetch_job_details(self, driver, job_url):
        details = {}
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(3)

            desc_selectors = [
                ".job-description",
                "[class*='job-description']",
                "[class*='jobDescription']",
                ".article__content",
                "[class*='description']",
                "main"
            ]
            for selector in desc_selectors:
                try:
                    desc_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = desc_elem.text.strip()
                    if text and len(text) > 50:
                        details['description'] = text[:3000]
                        break
                except:
                    continue

            # Department
            dept_selectors = ["[class*='department']", "[class*='category']", "[class*='expertise']"]
            for selector in dept_selectors:
                try:
                    dept_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = dept_elem.text.strip()
                    if text:
                        details['department'] = text
                        break
                except:
                    continue

            # Employment type
            type_selectors = ["[class*='contract']", "[class*='employment']", "[class*='job-type']"]
            for selector in type_selectors:
                try:
                    type_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = type_elem.text.strip()
                    if text:
                        details['employment_type'] = text
                        break
                except:
                    continue

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details from {job_url}: {str(e)}")
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

        location_str = location_str.strip()
        # Remove "Posted" date info if present
        if 'Posted' in location_str:
            location_str = location_str.split('Posted')[0].strip()

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
    scraper = LorealScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

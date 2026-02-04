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

logger = setup_logger('samsung_scraper')


class SamsungScraper:
    def __init__(self):
        self.company_name = 'Samsung'
        # Workday platform - India locations
        self.url = 'https://sec.wd3.myworkdayjobs.com/Samsung_Careers?locations=0c974e8c1228010867596ab21b3c3469&locations=189767dd6c9201004b83aa89a5295a80'

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
            time.sleep(8)  # Workday takes longer

            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, 'a[data-automation-id="jobTitle"]'
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
                    if not self._go_to_next_page(driver, current_page):
                        break
                    time.sleep(5)
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

    def _go_to_next_page(self, driver, current_page):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            next_selectors = [
                (By.XPATH, f'//button[@aria-label="{current_page + 1}"]'),
                (By.XPATH, f'//button[text()="{current_page + 1}"]'),
                (By.CSS_SELECTOR, f'button[data-uxi-widget-type="page"][aria-label="{current_page + 1}"]'),
                (By.XPATH, '//button[@aria-label="next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="next"]'),
            ]

            for selector_type, selector_value in next_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Navigated to page {current_page + 1}")
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver, wait):
        jobs = []
        scraped_ids = set()

        try:
            time.sleep(5)

            # Use stable data-automation-id selectors for Workday
            job_elements = []
            selectors = [
                'section[data-automation-id="jobResults"] ul[role="list"] > li',
                'section[data-automation-id="jobResults"] ul[aria-label] > li',
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
            # Extract title and URL from the stable jobTitle link
            title = ""
            job_url = ""
            try:
                title_link = job_elem.find_element(By.CSS_SELECTOR, 'a[data-automation-id="jobTitle"]')
                title = title_link.text.strip()
                job_url = title_link.get_attribute('href')
            except:
                pass

            if not title or len(title) < 3:
                return None

            # Extract job ID from subtitle (e.g. R54639)
            job_id = ""
            try:
                subtitle = job_elem.find_element(By.CSS_SELECTOR, 'ul[data-automation-id="subtitle"] li')
                job_id = subtitle.text.strip()
            except:
                pass

            if not job_id:
                if job_url and '/job/' in job_url:
                    job_id = job_url.split('/job/')[-1].split('/')[0]
                else:
                    job_id = f"samsung_{idx}_{hashlib.md5(title.encode()).hexdigest()[:12]}"

            # Extract location from data-automation-id="locations"
            location = ""
            try:
                loc_elem = job_elem.find_element(By.CSS_SELECTOR, 'div[data-automation-id="locations"] dd')
                location = loc_elem.text.strip()
            except:
                pass

            # Extract posted date from data-automation-id="postedOn"
            posted_date = ""
            try:
                date_elem = job_elem.find_element(By.CSS_SELECTOR, 'div[data-automation-id="postedOn"] dd')
                posted_date = date_elem.text.strip()
            except:
                pass

            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'description': '',
                'location': location,
                'city': '',
                'state': '',
                'country': 'India',
                'employment_type': '',
                'department': '',
                'apply_url': job_url if job_url else self.url,
                'posted_date': posted_date,
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            if FETCH_FULL_JOB_DETAILS and job_url and job_url != self.url:
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
            time.sleep(5)

            desc_selectors = [
                'div[data-automation-id="jobPostingDescription"]',
                "[class*='job-description']",
                "[class*='description']",
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

            # Employment type
            try:
                emp_elem = driver.find_element(By.XPATH, '//dd[contains(text(), "Full time") or contains(text(), "Part time") or contains(text(), "Contract")]')
                if emp_elem.text.strip():
                    details['employment_type'] = emp_elem.text.strip()
            except:
                pass

            # Location
            try:
                loc_elem = driver.find_element(By.CSS_SELECTOR, 'dd[data-automation-id="locations"]')
                if loc_elem.text.strip():
                    details['location'] = loc_elem.text.strip()
            except:
                pass

            # Posted date
            try:
                date_elem = driver.find_element(By.CSS_SELECTOR, 'dd[data-automation-id="postedOn"]')
                if date_elem.text.strip():
                    details['posted_date'] = date_elem.text.strip()
            except:
                pass

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
    scraper = SamsungScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

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

logger = setup_logger('meta_scraper')


class MetaScraper:
    def __init__(self):
        self.company_name = 'Meta'
        self.url = 'https://www.metacareers.com/jobs?offices[0]=Mumbai%2C%20India&offices[1]=Gurgaon%2C%20India&offices[2]=Bangalore%2C%20India&offices[3]=Hyderabad%2C%20India&offices[4]=New%20Delhi%2C%20India'

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
                    By.CSS_SELECTOR, "a[href*='/jobs/'], [class*='job'], [role='listitem']"
                )))
                logger.info("Job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for job listings: {str(e)}")

            # Meta uses infinite scroll - scroll to load more
            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page/scroll {current_page}")

                jobs = self._scrape_page(driver, wait)
                new_jobs = [j for j in jobs if j['external_id'] not in {x['external_id'] for x in all_jobs}]
                all_jobs.extend(new_jobs)
                logger.info(f"Scroll {current_page}: found {len(new_jobs)} new jobs")

                if current_page < max_pages:
                    # Scroll down for more results
                    prev_count = len(driver.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/']"))
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(3)
                    new_count = len(driver.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/']"))
                    if new_count == prev_count:
                        logger.info("No more jobs to load")
                        break

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

    def _scrape_page(self, driver, wait):
        jobs = []
        scraped_ids = set()

        try:
            job_elements = []
            selectors = [
                "a[href*='/jobs/'][role='link']",
                "[class*='job'] a[href*='/jobs/']",
                "div[role='listitem']",
                "a[href*='/jobs/']",
            ]

            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    # Filter out non-job links
                    filtered = []
                    for elem in elements:
                        href = elem.get_attribute('href') or ''
                        text = elem.text.strip()
                        if '/jobs/' in href and text and len(text) > 3:
                            filtered.append(elem)
                    if filtered:
                        job_elements = filtered
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
            title = ""
            job_url = ""

            tag_name = job_elem.tag_name
            if tag_name == 'a':
                all_text = job_elem.text.strip()
                title = all_text.split('\n')[0].strip() if all_text else ""
                job_url = job_elem.get_attribute('href')
            else:
                title_selectors = [
                    "a[href*='/jobs/']",
                    "[class*='title']",
                    "h3", "h2", "h4",
                    "a"
                ]
                for selector in title_selectors:
                    try:
                        title_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip().split('\n')[0]
                        job_url = title_elem.get_attribute('href') or ''
                        if title:
                            break
                    except:
                        continue

            if not title or not job_url:
                return None

            # Extract job ID from URL (e.g., /jobs/123456789/)
            job_id = ""
            if '/jobs/' in job_url:
                parts = job_url.split('/jobs/')[-1].split('/')
                for part in parts:
                    if part.isdigit():
                        job_id = part
                        break
            if not job_id:
                job_id = f"meta_{idx}_{hashlib.md5(job_url.encode()).hexdigest()[:8]}"

            # Extract location from element text
            location = ""
            all_text = job_elem.text.strip()
            lines = all_text.split('\n')
            for line in lines[1:]:  # Skip title line
                line_s = line.strip()
                if any(city in line_s for city in ['Mumbai', 'Gurgaon', 'Bangalore', 'Hyderabad', 'New Delhi', 'India', 'Remote']):
                    location = line_s
                    break

            # Extract other fields from text
            department = ""
            for line in lines[1:]:
                line_s = line.strip()
                if line_s and line_s != location and not any(c in line_s for c in ['Mumbai', 'Delhi', 'India']):
                    # Likely department or category
                    if len(line_s) < 80 and not line_s.startswith('http'):
                        department = line_s
                        break

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
                'city': '',
                'state': '',
                'country': 'India',
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': 'Remote' if 'Remote' in all_text else '',
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
                "[class*='job-description']",
                "[class*='jobDescription']",
                "[class*='description']",
                "[class*='detail']",
                "[role='main']",
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

            # Location from detail page
            loc_selectors = ["[class*='location']", "[class*='office']"]
            for selector in loc_selectors:
                try:
                    loc_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = loc_elem.text.strip()
                    if text and ('India' in text or any(c in text for c in ['Mumbai', 'Delhi', 'Bangalore'])):
                        details['location'] = text
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

        # Handle "+" notation like "Mumbai, India + 2 more"
        if '+' in location_str:
            location_str = location_str.split('+')[0].strip()

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
    scraper = MetaScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

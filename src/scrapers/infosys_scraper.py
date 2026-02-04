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

logger = setup_logger('infosys_scraper')


class InfosysScraper:
    def __init__(self):
        self.company_name = 'Infosys'
        self.url = 'https://career.infosys.com/jobs?companyhiringtype=IL&countrycode=IN'

    def setup_driver(self):
        """Set up Chrome driver with options"""
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
        """Generate stable external_id using MD5 hash"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Main scraping method"""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            driver.get(self.url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)

            # Angular SPA - wait for dynamic content to load
            time.sleep(10)

            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "mat-card.custom-card, mat-card"
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

    def _go_to_next_page(self, driver, current_page):
        """Navigate to next page"""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            next_selectors = [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'li.next a'),
                (By.XPATH, f'//a[text()="{current_page + 1}"]'),
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
        """Scrape all jobs from current page"""
        jobs = []
        scraped_ids = set()

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Infosys uses Angular mat-card components
            job_elements = []
            selectors = [
                "mat-card.custom-card",
                "mat-card",
            ]

            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Found {len(job_elements)} job listings using selector: {selector}")
                        break
                except:
                    continue

            if not job_elements:
                logger.warning("Could not find job listings with any selector")
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
        """Extract job data from an Infosys mat-card element"""
        try:
            card_text = job_elem.text.strip()
            if not card_text or len(card_text) < 10:
                return None

            # Infosys mat-card structure:
            # Line 1: "LOCATION , ORGANIZATION"
            # Line 2: "Job Title"
            # Line 3: "Work Experience of X Years to Y Years"
            # Line 4: "Skills: ..."
            # Line 5: "Responsibilities: ..."

            title = ""
            location = ""
            experience_level = ""
            description = ""

            # Extract title from .job-titleTxt
            try:
                title_elem = job_elem.find_element(By.CSS_SELECTOR, ".job-titleTxt")
                title = title_elem.text.strip()
            except:
                pass

            # Extract location from .job-locationTxt
            try:
                loc_elem = job_elem.find_element(By.CSS_SELECTOR, ".job-locationTxt")
                location = loc_elem.text.strip()
                # Remove org name (e.g., ", Infosys Limited")
                if ',' in location:
                    parts = location.split(',')
                    city = parts[0].strip()
                    org = parts[1].strip() if len(parts) > 1 else ''
                    if 'Infosys' in org or 'BPM' in org:
                        location = city
            except:
                pass

            # Fallback: parse from card text
            if not title:
                lines = card_text.split('\n')
                for line in lines:
                    line_s = line.strip()
                    if not line_s:
                        continue
                    # Skip location lines, experience lines, skill lines
                    if any(kw in line_s for kw in ['Work Experience', 'Skills:', 'Responsibilities:', 'INFOSYS']):
                        continue
                    if line_s.isupper() and len(line_s) < 30:
                        continue  # Likely location
                    if not title and len(line_s) > 5:
                        title = line_s
                        break

            if not title:
                return None

            # Extract experience from text
            lines = card_text.split('\n')
            for line in lines:
                if 'Work Experience' in line:
                    experience_level = line.strip()
                    break

            # Build description from skills + responsibilities
            desc_parts = []
            for line in lines:
                line_s = line.strip()
                if line_s.startswith('Skills:') or line_s.startswith('Responsibilities:'):
                    desc_parts.append(line_s)
            description = '\n'.join(desc_parts)

            job_id = f"infosys_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

            # Try to click on the card to get the job URL
            job_url = self.url
            try:
                job_elem.click()
                time.sleep(1)
                current_url = driver.current_url
                if current_url != self.url:
                    job_url = current_url
                    # Extract job ID from URL if available
                    if '/jobdesc' in job_url:
                        job_id = job_url.split('/jobdesc/')[-1].split('/')[0].split('?')[0]
                    driver.back()
                    time.sleep(2)
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
                'description': description[:3000],
                'posted_date': '',
                'city': '',
                'state': '',
                'country': 'India',
                'job_function': '',
                'experience_level': experience_level,
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            location_parts = self.parse_location(job_data.get('location', ''))
            job_data.update(location_parts)

            return job_data

        except Exception as e:
            logger.error(f"Error extracting job data: {str(e)}")
            return None

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(3)

            # Description
            desc_selectors = [
                ".job-description",
                "[class*='job-description']",
                "[class*='jobDescription']",
                "[class*='description']",
                ".jd-content",
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
            loc_selectors = [
                "[class*='location']",
                "[class*='Location']",
            ]
            for selector in loc_selectors:
                try:
                    loc_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = loc_elem.text.strip()
                    if text:
                        details['location'] = text
                        break
                except:
                    continue

            # Experience level
            exp_selectors = ["[class*='experience']", "[class*='Experience']"]
            for selector in exp_selectors:
                try:
                    exp_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = exp_elem.text.strip()
                    if text:
                        details['experience_level'] = text
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
        """Parse location string into city, state, country"""
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result

        location_str = location_str.strip()
        # Remove "Infosys Limited" or "Infosys BPM" from location
        for org in ['INFOSYS LIMITED', 'Infosys Limited', 'INFOSYS BPM', 'Infosys BPM']:
            location_str = location_str.replace(org, '').strip().rstrip(',').strip()

        parts = [p.strip() for p in location_str.split(',') if p.strip()]

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
    scraper = InfosysScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

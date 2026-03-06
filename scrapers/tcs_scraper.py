from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import re
import time
from pathlib import Path
import os
import stat


from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('tcs_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class TCSScraper:
    def __init__(self):
        self.company_name = 'TCS'
        self.url = 'https://ibegin.tcsapps.com/candidate/'
        self.alt_url = 'https://www.tcs.com/careers/india'

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
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        driver_path = CHROMEDRIVER_PATH
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

        try:
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"Service driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)
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
            logger.info(f"Starting {self.company_name} scraping")

            driver.get(self.url)
            time.sleep(8)

            # Dismiss cookie banner and click Search Jobs (AngularJS SPA)
            driver.execute_script("var cb = document.querySelector('.cookie-banner'); if(cb) cb.remove();")
            time.sleep(1)
            driver.execute_script("var btn = document.querySelector('button.btn-color'); if(btn) btn.click();")
            logger.info("Clicked Search Jobs button")
            time.sleep(10)

            # Verify jobs loaded
            body_text = driver.find_element(By.TAG_NAME, 'body').text
            if 'Jobs Found' not in body_text:
                logger.warning("Jobs page did not load after clicking Search Jobs")
                # Try alt URL
                driver.get(self.alt_url)
                time.sleep(10)

            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                jobs = self._scrape_page(driver)
                all_jobs.extend(jobs)
                logger.info(f"Page {current_page}: found {len(jobs)} jobs")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
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

    def _go_to_next_page(self, driver, current_page):
        try:
            # Get first job title before pagination for change detection
            old_body = driver.find_element(By.TAG_NAME, 'body').text[:200]

            # Click the next page link in pagination (›)
            next_page = current_page + 1
            clicked = False
            # Try clicking specific page number first, then › arrow
            for selector in [
                f'//ul[contains(@class,"pagination")]//a[text()="{next_page}"]',
                '//ul[contains(@class,"pagination")]//a[text()="›"]',
            ]:
                try:
                    btn = driver.find_element(By.XPATH, selector)
                    driver.execute_script("arguments[0].scrollIntoView();", btn)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    break
                except:
                    continue

            if not clicked:
                return False

            # Wait for content to change
            for _ in range(30):
                time.sleep(0.3)
                new_body = driver.find_element(By.TAG_NAME, 'body').text[:200]
                if new_body != old_body:
                    break
            time.sleep(1)
            logger.info(f"Navigated to page {next_page}")
            return True
        except Exception as e:
            logger.error(f"Error navigating: {str(e)}")
            return False

    def _scrape_page(self, driver):
        """Parse jobs from body text. TCS iBegin renders jobs as repeating blocks:
        title, location, department, experience, date, skills/tags"""
        jobs = []
        date_pattern = re.compile(r'\d{1,2}-?\s*[A-Z][a-z]{2}-?\s*\d{4}')
        year_pattern = re.compile(r'\d+-\d+\s+years?', re.IGNORECASE)
        dept_keywords = ['business process services', 'consultancy', 'it infrastructure services',
                         'technology', 'human resources', 'finance', 'quality assurance',
                         'marketing and sales']

        try:
            body_text = driver.find_element(By.TAG_NAME, 'body').text
            lines = [l.strip() for l in body_text.split('\n') if l.strip()]

            # Find where job listings start (after "Filter" line)
            start_idx = 0
            for i, line in enumerate(lines):
                if line == 'Filter':
                    start_idx = i + 1
                    break

            # Find where job listings end (before footer/pagination)
            end_idx = len(lines)
            for i in range(start_idx, len(lines)):
                if lines[i] in ('Ask', '\u2039\u2039', '\u203a\u203a') or 'LEGAL' in lines[i] or 'CONNECT WITH US' in lines[i]:
                    end_idx = i
                    break

            job_lines = lines[start_idx:end_idx]
            if not job_lines:
                logger.warning("No job lines found in body text")
                return jobs

            # Parse job blocks: each block ends with a date line, followed by skills/tags
            current_block = []
            skip_words = ['filter', 'search jobs', 'jobs at tcs', 'email me', 'jobs found',
                          'my saved', 'browse through', 'guide me']

            for line in job_lines:
                lower = line.lower()
                if any(s in lower for s in skip_words):
                    continue

                current_block.append(line)

                # Date line signals end of main job data; next line is skills
                if date_pattern.search(line) and len(current_block) >= 4:
                    # Peek: if block has exactly title+loc+dept+exp+date, next line is skills
                    continue

                # If previous line was a date and this line looks like skills/tags (contains |)
                if len(current_block) >= 5 and date_pattern.search(current_block[-2]):
                    self._parse_job_block(current_block, jobs, date_pattern, year_pattern, dept_keywords)
                    current_block = []

            # Handle remaining block
            if len(current_block) >= 4:
                self._parse_job_block(current_block, jobs, date_pattern, year_pattern, dept_keywords)

            logger.info(f"Parsed {len(jobs)} jobs from body text")
        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")
        return jobs

    def _parse_job_block(self, block, jobs, date_pattern, year_pattern, dept_keywords):
        """Parse a single job block into a job dict."""
        title = ''
        location = ''
        department = ''
        experience = ''
        posted_date = ''
        skills = ''

        for line in block:
            if date_pattern.search(line) and not posted_date:
                posted_date = line
            elif year_pattern.search(line) and not experience:
                experience = line
            elif any(d in line.lower() for d in dept_keywords) and not department:
                department = line
            elif '|' in line and len(line.split('|')) >= 2:
                skills = line
            elif not title:
                title = line
            elif not location:
                location = line

        if not title or len(title) < 3:
            return

        # Filter out non-job entries
        skip_titles = ['tcs careers', 'first', 'jobs at tcs', 'select', 'email me',
                       'guided search', 'login', 'register', 'new user']
        if title.lower().strip() in skip_titles or title.strip() in ('FIRST', 'EN'):
            return
        # Skip pagination artifacts
        if any(c in title for c in ['\u2039', '\u203a', '\u2039\u2039', '\u203a\u203a']):
            return

        job_id = f"tcs_{hashlib.md5(f'{title}_{location}_{posted_date}'.encode()).hexdigest()[:12]}"

        job_data = {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': skills,
            'location': location if location else 'India',
            'city': '',
            'state': '',
            'country': 'India',
            'employment_type': '',
            'department': department,
            'apply_url': self.url,
            'posted_date': posted_date,
            'job_function': department,
            'experience_level': experience,
            'salary_range': '',
            'remote_type': '',
            'status': 'active'
        }

        location_parts = self.parse_location(location)
        job_data.update(location_parts)

        jobs.append(job_data)
        logger.info(f"Extracted: {title} | {location}")

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
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = TCSScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
from pathlib import Path
import os
import stat


from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('infosys_scraper')

CHROMEDRIVER_PATH = os.path.expanduser(
    '~/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'
)


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
        chrome_options.add_argument('--user-agent=AppleWebKit/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])

        driver_path = CHROMEDRIVER_PATH
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
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
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
            wait = WebDriverWait(driver, 10)
            short_wait = WebDriverWait(driver, 5)

            # Angular SPA - wait for dynamic content to load
            time.sleep(15)

            # Scroll down 5 times to trigger lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "mat-card.mat-mdc-card, div.jobContainer, div.job-titleTxt"
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
                (By.CSS_SELECTOR, 'button.mat-paginator-navigation-next'),
                (By.CSS_SELECTOR, '.mat-paginator-navigation-next'),
                (By.CSS_SELECTOR, 'a.page-link[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'li.page-item:last-child a.page-link'),
                (By.XPATH, '//a[contains(@class, "page-link") and contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, f'//a[contains(@class, "page-link") and text()="{current_page + 1}"]'),
                (By.XPATH, f'//a[text()="{current_page + 1}"]'),
            ]

            for selector_type, selector_value in next_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    if not next_button.is_enabled():
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Navigated to page {current_page + 1}")
                    time.sleep(5)  # Wait for Angular to re-render
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver, wait):
        """Scrape all jobs from current page using actual Infosys DOM selectors"""
        jobs = []
        scraped_ids = set()

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            # Infosys career page uses Angular Material cards
            # Actual DOM: mat-card.mat-mdc-card contains job-titleTxt, job-locationTxt, etc.
            job_elements = []
            selectors = [
                "mat-card.mat-mdc-card",
                "div.col-md-12.jobContainer",
                "div.jobContainer",
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

            # JS-based extraction fallback using actual DOM selectors
            if not job_elements:
                logger.info("Trying JS-based extraction with Infosys DOM selectors")
                js_jobs = driver.execute_script("""
                    var results = [];
                    var titles = document.querySelectorAll('div.job-titleTxt');
                    titles.forEach(function(titleEl, idx) {
                        var title = (titleEl.innerText || '').trim();
                        if (!title) return;
                        var card = titleEl.closest('mat-card') || titleEl.closest('.jobContainer') || titleEl.parentElement;
                        var location = '';
                        var level = '';
                        var roles = '';
                        if (card) {
                            var locEl = card.querySelector('div.job-locationTxt');
                            if (locEl) location = (locEl.innerText || '').trim();
                            var lvlEl = card.querySelector('div.job-levelTxt');
                            if (lvlEl) level = (lvlEl.innerText || '').trim();
                            var rolesEl = card.querySelector('div.job-rolesTxt');
                            if (rolesEl) roles = (rolesEl.innerText || '').trim();
                        }
                        results.push({title: title, location: location, level: level, roles: roles, index: idx});
                    });
                    return results;
                """)
                if js_jobs:
                    for jdata in js_jobs:
                        title = jdata.get('title', '').strip()
                        if not title or len(title) < 3:
                            continue
                        location = jdata.get('location', '').strip()
                        level = jdata.get('level', '').strip()
                        roles = jdata.get('roles', '').strip()
                        idx = jdata.get('index', 0)

                        job_id = f"infosys_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                        external_id = self.generate_external_id(job_id, self.company_name)
                        if external_id in scraped_ids:
                            continue

                        # Clean location: remove org name like "Infosys Limited"
                        clean_location = location
                        for org in ['INFOSYS LIMITED', 'Infosys Limited', 'INFOSYS BPM', 'Infosys BPM']:
                            clean_location = clean_location.replace(org, '').strip().rstrip(',').strip()

                        job_data = {
                            'external_id': external_id,
                            'company_name': self.company_name,
                            'title': title,
                            'description': roles,
                            'location': clean_location,
                            'city': '',
                            'state': '',
                            'country': 'India',
                            'employment_type': '',
                            'department': '',
                            'apply_url': self.url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': level,
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        location_parts = self.parse_location(clean_location)
                        job_data.update(location_parts)
                        jobs.append(job_data)
                        scraped_ids.add(external_id)
                        logger.info(f"JS extracted job {len(jobs)}: {title}")
                    if jobs:
                        logger.info(f"JS extraction found {len(jobs)} jobs")
                        return jobs

            if not job_elements and not jobs:
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
            if not card_text or len(card_text) < 5:
                return None

            title = ""
            location = ""
            experience_level = ""
            description = ""

            # Extract title from div.job-titleTxt (actual Infosys DOM)
            title_selectors = [
                "div.job-titleTxt",
                ".job-titleTxt",
            ]
            for sel in title_selectors:
                try:
                    title_elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                    title = title_elem.text.strip()
                    if title:
                        break
                except:
                    continue

            # Extract location from div.job-locationTxt (actual Infosys DOM)
            loc_selectors = [
                "div.job-locationTxt",
                ".job-locationTxt",
            ]
            for sel in loc_selectors:
                try:
                    loc_elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                    location = loc_elem.text.strip()
                    if location:
                        # Remove org name (e.g., ", Infosys Limited")
                        for org in ['INFOSYS LIMITED', 'Infosys Limited', 'INFOSYS BPM', 'Infosys BPM']:
                            location = location.replace(org, '').strip().rstrip(',').strip()
                        break
                except:
                    continue

            # Extract experience level from div.job-levelTxt
            try:
                level_elem = job_elem.find_element(By.CSS_SELECTOR, "div.job-levelTxt, .job-levelTxt")
                experience_level = level_elem.text.strip()
            except:
                pass

            # Extract roles/description from div.job-rolesTxt
            try:
                roles_elem = job_elem.find_element(By.CSS_SELECTOR, "div.job-rolesTxt, .job-rolesTxt")
                description = roles_elem.text.strip()
            except:
                pass

            # Fallback: parse title from card text lines
            if not title:
                lines = card_text.split('\n')
                for line in lines:
                    line_s = line.strip()
                    if not line_s:
                        continue
                    if any(kw in line_s.lower() for kw in ['work experience', 'skills:', 'responsibilities:', 'infosys']):
                        continue
                    if line_s.isupper() and len(line_s) < 30:
                        continue  # Likely location
                    if len(line_s) > 5:
                        title = line_s
                        break

            if not title:
                return None

            job_id = f"infosys_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

            # Try to get a job URL from a link within the card
            job_url = self.url
            try:
                link_elem = job_elem.find_element(By.TAG_NAME, 'a')
                href = link_elem.get_attribute('href')
                if href:
                    job_url = href
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

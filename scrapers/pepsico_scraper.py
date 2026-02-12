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

try:
    import requests as req_lib
except ImportError:
    req_lib = None


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('pepsico_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class PepsiCoScraper:
    def __init__(self):
        self.company_name = 'PepsiCo'
        self.url = 'https://www.pepsicojobs.com/main/jobs?stretchUnit=MILES&stretch=10&location=India&woe=12&regionCode=IN'
        self.api_url = 'https://www.pepsicojobs.com/api/jobs'

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
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])

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
            logger.warning(f"Could not set permissions: {str(e)}")

        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        # Primary: API-based scraping (fast, reliable)
        if req_lib is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                logger.warning("API returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.warning(f"API failed: {str(e)}, falling back to Selenium")

        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape PepsiCo jobs using Phenom API."""
        all_jobs = []
        limit = 20
        max_results = max_pages * limit
        page = 1

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
        }

        while len(all_jobs) < max_results:
            try:
                params = {'location': 'India', 'page': page, 'limit': limit, 'locale': 'en'}
                logger.info(f"Fetching API page {page}")
                response = req_lib.get(self.api_url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()

                total = data.get('totalCount', 0)
                jobs_list = data.get('jobs', [])
                if not jobs_list:
                    break

                logger.info(f"API page {page}: {len(jobs_list)} jobs (total: {total})")

                for job_raw in jobs_list:
                    try:
                        job_data_raw = job_raw.get('data', job_raw)
                        title = job_data_raw.get('title', '')
                        if not title:
                            continue

                        req_id = str(job_data_raw.get('req_id', job_data_raw.get('slug', '')))
                        city = job_data_raw.get('city', '')
                        state = job_data_raw.get('state', '')
                        country = job_data_raw.get('country', 'India')
                        location = job_data_raw.get('location_name', '')
                        if not location and city:
                            location = f"{city}, {state}" if state else city
                        apply_url = job_data_raw.get('apply_url', '')
                        if not apply_url:
                            slug = job_data_raw.get('slug', req_id)
                            apply_url = f"https://www.pepsicojobs.com/main/jobs/{slug}"

                        job_data = {
                            'external_id': self.generate_external_id(req_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': (job_data_raw.get('description', '') or '')[:3000],
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': country if country else 'India',
                            'employment_type': job_data_raw.get('employment_type', ''),
                            'department': job_data_raw.get('category', ''),
                            'apply_url': apply_url,
                            'posted_date': job_data_raw.get('posted_date', ''),
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': job_data_raw.get('location_type', ''),
                            'status': 'active'
                        }
                        all_jobs.append(job_data)
                    except Exception as e:
                        logger.error(f"Error processing job: {str(e)}")
                        continue

                if len(all_jobs) >= total:
                    break
                page += 1
            except Exception as e:
                logger.error(f"API request failed: {str(e)}")
                break

        logger.info(f"Total jobs from API: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: Selenium-based scraping."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")
            driver.get(self.url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(10)

            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "[class*='job'], a[href*='/job/'], [class*='search-result']"
                )))
            except:
                logger.warning("Timeout waiting for listings")

            current_page = 1
            while current_page <= max_pages:
                jobs = self._scrape_page(driver, wait)
                all_jobs.extend(jobs)
                logger.info(f"Page {current_page}: found {len(jobs)} jobs")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver):
                        break
                    time.sleep(3)
                current_page += 1

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    driver.execute_script("arguments[0].click();", btn)
                    return True
                except:
                    continue
            return False
        except:
            return False

    def _scrape_page(self, driver, wait):
        jobs = []
        scraped_ids = set()

        try:
            # Scroll multiple times to trigger lazy loading
            for _scroll_i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            job_elements = []
            selectors = [
                "a[href*='/job/']",
                "[class*='job-card']",
                "[class*='job-listing']",
                "li[class*='result']",
                "[class*='search-result']",
                "div.job-card",
                "a.job-link",
                "[role='listitem']",
                "article",
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
                links = driver.find_elements(By.TAG_NAME, 'a')
                job_links = [l for l in links if '/job/' in (l.get_attribute('href') or '') and l.text.strip()]
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
                for sel in ["h3 a", "h2 a", "a[href*='/job/']", "[class*='title'] a", "a"]:
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

            # Make URL absolute
            if job_url and job_url.startswith('/'):
                job_url = f"https://www.pepsicojobs.com{job_url}"

            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

            location = ""
            department = ""
            for line in job_elem.text.split('\n')[1:]:
                line_s = line.strip()
                if any(c in line_s for c in ['India', 'Mumbai', 'Gurgaon', 'Hyderabad', 'Bangalore', 'Chennai']):
                    location = line_s
                elif line_s and not department and len(line_s) < 60:
                    department = line_s

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
    scraper = PepsiCoScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

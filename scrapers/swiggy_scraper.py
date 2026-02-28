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

logger = setup_logger('swiggy_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class SwiggyScraper:
    def __init__(self):
        self.company_name = 'Swiggy'
        self.url = 'https://careers.swiggy.com/#/careers?src=careers'

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
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
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
            # Smart wait for the main page to load (wait for iframes or job content)
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, 'iframe'))
                )
            except:
                time.sleep(5)  # Fallback if no iframe detected

            # CRITICAL: Switch to the iframe containing the actual job listings
            # The jobs are inside an iframe from mynexthire.com
            iframe_switched = False
            try:
                # Try to find and switch to iframe
                iframes = driver.find_elements(By.TAG_NAME, 'iframe')
                logger.info(f"Found {len(iframes)} iframes on page")

                for i, iframe in enumerate(iframes):
                    src = iframe.get_attribute('src') or ''
                    logger.info(f"Iframe {i}: src={src[:100]}")
                    if 'mynexthire' in src or 'careers' in src or 'jobs' in src:
                        driver.switch_to.frame(iframe)
                        iframe_switched = True
                        logger.info(f"Switched to iframe {i} with src: {src[:100]}")
                        break

                # If no matching src found, try switching to the first iframe
                if not iframe_switched and iframes:
                    driver.switch_to.frame(iframes[0])
                    iframe_switched = True
                    logger.info("Switched to first iframe (no matching src found)")

            except Exception as e:
                logger.warning(f"Error switching to iframe: {str(e)}")

            # Wait for iframe content to load using smart wait
            if iframe_switched:
                logger.info("Waiting for iframe content to render...")

            wait = WebDriverWait(driver, 10)

            # Try to wait for job-related elements inside the iframe
            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "div.search-banner, div.card, a[href*='job'], div[class*='job'], table tr, li[class*='job']"
                )))
                logger.info("Job elements detected inside iframe")
            except:
                logger.warning("Timeout waiting for job elements in iframe context")

            # Quick scroll inside iframe context to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

            # Scrape jobs from within the iframe context
            jobs = self._scrape_page(driver, wait)
            all_jobs.extend(jobs)

            # If no jobs found in iframe, switch back and try main page
            if not all_jobs and iframe_switched:
                logger.info("No jobs in iframe, switching back to main page")
                driver.switch_to.default_content()
                time.sleep(1)
                jobs = self._scrape_page(driver, wait)
                all_jobs.extend(jobs)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                try:
                    driver.switch_to.default_content()
                except:
                    pass
                driver.quit()
                logger.info("Browser closed")

    def _scrape_page(self, driver, wait):
        jobs = []
        scraped_ids = set()

        try:
            # PRIMARY: JavaScript-based table extraction for mynexthire iframe
            # The iframe contains a table with columns: [Job ID, Job Title, Location, Unit/Department]
            # First row is header (empty + "" + "Location" + "Unit"), skip it
            logger.info("Trying JS table extraction from mynexthire iframe")
            js_table_jobs = driver.execute_script("""
                var results = [];
                var tables = document.querySelectorAll('table.table');
                for (var t = 0; t < tables.length; t++) {
                    var rows = tables[t].querySelectorAll('tr');
                    for (var r = 0; r < rows.length; r++) {
                        var cells = rows[r].querySelectorAll('td');
                        if (cells.length >= 2) {
                            var jobId = (cells[0].innerText || '').trim();
                            var title = (cells[1].innerText || '').trim();
                            var location = cells.length >= 3 ? (cells[2].innerText || '').trim() : '';
                            var department = cells.length >= 4 ? (cells[3].innerText || '').trim() : '';
                            // Skip header row (where title is empty or is "Location"/"Unit")
                            if (title && title.length > 2 && title !== 'Location' && title !== 'Unit' &&
                                jobId !== '' && /^\\d+$/.test(jobId)) {
                                results.push({
                                    jobId: jobId,
                                    title: title,
                                    location: location,
                                    department: department
                                });
                            }
                        }
                    }
                }
                return results;
            """)

            if js_table_jobs and len(js_table_jobs) > 0:
                logger.info(f"JS table extraction found {len(js_table_jobs)} jobs")
                for idx, jdata in enumerate(js_table_jobs, 1):
                    title = jdata.get('title', '').strip()
                    job_id_str = jdata.get('jobId', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or title in scraped_ids:
                        continue
                    scraped_ids.add(title)

                    job_id = f"swiggy_{job_id_str}" if job_id_str else f"swiggy_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

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
                        'department': department,
                        'apply_url': self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': 'Remote' if 'Remote' in location else '',
                        'status': 'active'
                    }
                    location_parts = self.parse_location(location)
                    job_data.update(location_parts)
                    jobs.append(job_data)
                    logger.info(f"Extracted job {len(jobs)}: {title} | {location} | {department}")

                if jobs:
                    return jobs

            # SECONDARY: Selenium-based element extraction
            job_elements = []
            iframe_selectors = [
                "div[class*='job-card']",
                "div[class*='career'] a[href*='job']",
                "li[class*='job']",
                "div[class*='position']",
                "a[href*='job_application']",
                "a[href*='/job/']",
                "a[href*='/jobs/']",
                "[class*='job-card']",
                ".card",
            ]

            for selector in iframe_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Found {len(job_elements)} listings using selector: {selector}")
                        break
                except:
                    continue

            if not job_elements and not jobs:
                try:
                    body_text = driver.execute_script("return document.body ? document.body.innerText.substring(0, 500) : 'no body'")
                    logger.warning(f"No job listings found. Body preview: {body_text[:200]}")
                except:
                    logger.warning("Could not find job listings in any context")
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
                title = job_elem.text.strip().split('\n')[0]
                job_url = job_elem.get_attribute('href')
            elif tag_name == 'tr':
                # Table row - look for first cell or link
                try:
                    link = job_elem.find_element(By.CSS_SELECTOR, 'a[href]')
                    title = link.text.strip().split('\n')[0]
                    job_url = link.get_attribute('href')
                except:
                    cells = job_elem.find_elements(By.TAG_NAME, 'td')
                    if cells:
                        title = cells[0].text.strip().split('\n')[0]
            else:
                title_selectors = [
                    "h3 a", "h2 a", "h4 a",
                    "[class*='title'] a", "[class*='title']",
                    "a[href*='/careers/']",
                    "a[href*='/jobs/']",
                    "a[href*='job_application']",
                    "a[href*='/job/']",
                    "a"
                ]
                for selector in title_selectors:
                    try:
                        title_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip()
                        job_url = title_elem.get_attribute('href') or ''
                        if title:
                            break
                    except:
                        continue

            if not title:
                text = job_elem.text.strip()
                if text:
                    title = text.split('\n')[0].strip()

            if not title:
                return None
            if not job_url:
                job_url = self.url

            job_id = f"swiggy_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"
            if 'job_application' in job_url:
                job_id = job_url.split('job_application/')[-1].split('/')[0].split('?')[0] or job_id
            elif '/detail/' in job_url:
                job_id = job_url.split('/detail/')[-1].split('/')[0].split('?')[0] or job_id
            elif '/careers/' in job_url:
                job_id = job_url.split('/careers/')[-1].split('/')[0].split('?')[0] or job_id

            # Extract fields from text
            location = ""
            department = ""
            all_text = job_elem.text.strip()
            lines = all_text.split('\n')
            for line in lines[1:]:
                line_s = line.strip()
                if any(city in line_s for city in ['Bangalore', 'Bengaluru', 'Mumbai', 'Delhi', 'Hyderabad', 'India', 'Remote', 'Gurugram', 'Gurgaon']):
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
                'remote_type': 'Remote' if 'Remote' in all_text else '',
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
            time.sleep(3)

            desc_selectors = [
                "[class*='job-description']", "[class*='description']",
                "[class*='detail']", "main"
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
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = SwiggyScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

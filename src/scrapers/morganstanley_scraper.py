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

try:
    import requests
except ImportError:
    requests = None

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('morganstanley_scraper')

FRESH_CHROMEDRIVER = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class MorganStanleyScraper:
    def __init__(self):
        self.company_name = 'Morgan Stanley'
        # Eightfold AI platform
        self.url = 'https://morganstanley.eightfold.ai/careers?query=&location=India&pid=549795398771&sort_by=relevance'

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

        driver_path = FRESH_CHROMEDRIVER

        try:
            if os.path.exists(driver_path):
                try:
                    current_permissions = os.stat(driver_path).st_mode
                    os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except Exception as e:
                    logger.warning(f"Could not set permissions on chromedriver: {str(e)}")
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Service driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        # Primary method: Eightfold AI API via requests
        if requests is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("API method returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.error(f"API method failed: {str(e)}, falling back to Selenium")
        else:
            logger.warning("requests library not available, using Selenium only")

        # Fallback: Selenium-based scraping
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Morgan Stanley jobs using Eightfold AI API directly."""
        all_jobs = []
        num_per_page = 20
        max_results = max_pages * num_per_page
        scraped_ids = set()

        api_url = 'https://morganstanley.eightfold.ai/api/apply/v2/jobs'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://morganstanley.eightfold.ai/careers',
        }

        start = 0
        page = 1

        while start < max_results and page <= max_pages:
            params = {
                'domain': 'morganstanley.eightfold.ai',
                'location': 'India',
                'sort_by': 'relevance',
                'num': num_per_page,
                'start': start,
            }

            logger.info(f"API request page {page}: start={start}, num={num_per_page}")

            try:
                response = requests.get(api_url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed at start={start}: {str(e)}")
                break
            except ValueError as e:
                logger.error(f"Failed to parse API JSON response: {str(e)}")
                break

            positions = data.get('positions', [])
            if not positions:
                logger.info(f"No more positions returned at start={start}")
                break

            logger.info(f"API page {page}: received {len(positions)} positions")

            for pos in positions:
                try:
                    job_data = self._parse_api_position(pos)
                    if job_data and job_data['external_id'] not in scraped_ids:
                        all_jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                except Exception as e:
                    logger.error(f"Error parsing API position: {str(e)}")
                    continue

            # If we got fewer than requested, there are no more results
            if len(positions) < num_per_page:
                break

            start += num_per_page
            page += 1

        logger.info(f"API total jobs scraped: {len(all_jobs)}")
        return all_jobs

    def _parse_api_position(self, pos):
        """Parse a single position from the Eightfold AI API response."""
        title = pos.get('name', '').strip()
        if not title:
            return None

        # Build job ID from the position id
        job_id = str(pos.get('id', ''))
        if not job_id:
            job_id = f"ms_api_{hashlib.md5(title.encode()).hexdigest()[:8]}"

        # Build the apply URL
        apply_url = pos.get('apply_url', '')
        if not apply_url:
            apply_url = f"https://morganstanley.eightfold.ai/careers?pid={job_id}&domain=morganstanley.eightfold.ai"

        # Extract location from the locations array
        locations = pos.get('location', [])
        if isinstance(locations, list) and locations:
            location = locations[0] if isinstance(locations[0], str) else str(locations[0])
        elif isinstance(locations, str):
            location = locations
        else:
            location = ''

        # Extract other fields
        department = pos.get('department', '') or pos.get('team', '') or ''
        if isinstance(department, list) and department:
            department = department[0]

        employment_type = pos.get('employment_type', '') or pos.get('type', '') or ''
        if isinstance(employment_type, list) and employment_type:
            employment_type = employment_type[0]

        description = pos.get('description', '') or pos.get('job_description', '') or ''
        if description:
            description = description[:3000]

        posted_date = pos.get('t_create', '') or pos.get('date_created', '') or ''

        experience_level = pos.get('experience', '') or pos.get('experience_level', '') or ''

        job_data = {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'company_name': self.company_name,
            'title': title,
            'apply_url': apply_url,
            'location': location,
            'department': str(department),
            'employment_type': str(employment_type),
            'description': description,
            'posted_date': str(posted_date),
            'city': '',
            'state': '',
            'country': 'India',
            'job_function': '',
            'experience_level': str(experience_level),
            'salary_range': '',
            'remote_type': '',
            'status': 'active'
        }

        location_parts = self.parse_location(location)
        job_data.update(location_parts)

        return job_data

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: Scrape Morgan Stanley jobs using Selenium with correct Eightfold AI selectors."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")

            driver.get(self.url)

            # Eightfold AI is a React SPA - needs 12-15s for initial rendering
            logger.info("Waiting 14s for Eightfold AI SPA to render...")
            time.sleep(14)

            wait = WebDriverWait(driver, 10)

            # Wait for the job cards to appear using actual DOM selectors
            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    'div[class*="cardContainer"], a[class*="card-"], div[class*="cardlist"]'
                )))
                logger.info("Job card containers detected")
            except Exception as e:
                logger.warning(f"Timeout waiting for card containers: {str(e)}")

            scraped_ids = set()
            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")

                # Scroll down to trigger lazy loading of cards
                for scroll_pass in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)

                jobs_on_page = self._extract_jobs_from_page(driver, scraped_ids)
                all_jobs.extend(jobs_on_page)
                logger.info(f"Page {current_page}: found {len(jobs_on_page)} jobs (total: {len(all_jobs)})")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver):
                        break
                    time.sleep(5)
                current_page += 1

            logger.info(f"Total jobs scraped via Selenium: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during Selenium scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _extract_jobs_from_page(self, driver, scraped_ids):
        """Extract all job listings from the current page using actual Eightfold AI DOM selectors."""
        jobs = []

        # Strategy 1: Find job cards using actual DOM class patterns
        card_selectors = [
            'div[class*="cardContainer"]',             # div.cardContainer-GcY1a
            'a[class*="card-"][class*="r-link"]',      # a.r-link.card-F1ebU
            'a.r-link[class*="card-"]',                # alternative match
            'a[id^="job-card-"]',                      # a with id like job-card-549795520602-job-list
        ]

        job_elements = []
        used_selector = ''
        for selector in card_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and len(elements) > 0:
                    job_elements = elements
                    used_selector = selector
                    logger.info(f"Found {len(elements)} elements with selector: {selector}")
                    break
            except Exception:
                continue

        if not job_elements:
            logger.warning("No job cards found with primary selectors, trying JS extraction")
            return self._extract_jobs_via_js(driver, scraped_ids)

        for idx, elem in enumerate(job_elements, 1):
            try:
                job_data = self._parse_card_element(elem, driver, idx, used_selector)
                if job_data and job_data['external_id'] not in scraped_ids:
                    jobs.append(job_data)
                    scraped_ids.add(job_data['external_id'])
                    logger.info(f"  Job {len(jobs)}: {job_data['title']} | {job_data['location']}")
            except Exception as e:
                logger.error(f"Error parsing job card {idx}: {str(e)}")
                continue

        # If no jobs found from card elements, try JS fallback
        if not jobs:
            logger.info("Card parsing yielded 0 jobs, trying JS extraction")
            return self._extract_jobs_via_js(driver, scraped_ids)

        return jobs

    def _parse_card_element(self, elem, driver, idx, used_selector):
        """Parse a single job card element to extract job data."""
        title = ''
        job_url = ''
        location = ''
        department = ''

        tag_name = elem.tag_name

        if tag_name == 'a':
            # The element itself is the link (a.r-link.card-F1ebU)
            job_url = elem.get_attribute('href') or ''

            # Extract title from div[class*="title-"] inside the link
            try:
                title_elem = elem.find_element(By.CSS_SELECTOR, 'div[class*="title-"]')
                title = title_elem.text.strip()
            except Exception:
                pass

            if not title:
                try:
                    title_elem = elem.find_element(By.CSS_SELECTOR, 'h2[class*="position-title"]')
                    title = title_elem.text.strip()
                except Exception:
                    pass

            if not title:
                # Fallback: first line of all text
                all_text = elem.text.strip()
                if all_text:
                    title = all_text.split('\n')[0].strip()

            # Extract location from card text
            all_text = elem.text.strip()
            lines = all_text.split('\n')
            for line in lines:
                line_s = line.strip()
                if self._looks_like_location(line_s):
                    location = line_s
                    break

            # Extract department from div[class*="fieldValue"]
            try:
                dept_elem = elem.find_element(By.CSS_SELECTOR, 'div[class*="fieldValue"]')
                department = dept_elem.text.strip()
            except Exception:
                pass

        elif tag_name == 'div':
            # The element is a card container (div.cardContainer-GcY1a)
            # Find the link inside
            try:
                link_elem = elem.find_element(By.CSS_SELECTOR, 'a[class*="card-"], a.r-link')
                job_url = link_elem.get_attribute('href') or ''
            except Exception:
                pass

            if not job_url:
                try:
                    link_elem = elem.find_element(By.CSS_SELECTOR, 'a[href]')
                    job_url = link_elem.get_attribute('href') or ''
                except Exception:
                    pass

            # Extract title
            try:
                title_elem = elem.find_element(By.CSS_SELECTOR, 'div[class*="title-"]')
                title = title_elem.text.strip()
            except Exception:
                pass

            if not title:
                try:
                    title_elem = elem.find_element(By.CSS_SELECTOR, 'h2[class*="position-title"]')
                    title = title_elem.text.strip()
                except Exception:
                    pass

            if not title:
                all_text = elem.text.strip()
                if all_text:
                    title = all_text.split('\n')[0].strip()

            # Extract location
            try:
                loc_elem = elem.find_element(By.CSS_SELECTOR, 'div[class*="position-location"]')
                location = loc_elem.text.strip()
            except Exception:
                pass

            if not location:
                all_text = elem.text.strip()
                lines = all_text.split('\n')
                for line in lines:
                    line_s = line.strip()
                    if self._looks_like_location(line_s):
                        location = line_s
                        break

            # Extract department
            try:
                dept_elem = elem.find_element(By.CSS_SELECTOR, 'div[class*="fieldValue"]')
                department = dept_elem.text.strip()
            except Exception:
                pass

        if not title or not job_url:
            return None

        # Extract job ID from URL
        job_id = ''
        if 'pid=' in job_url:
            job_id = job_url.split('pid=')[-1].split('&')[0]
        elif 'job-card-' in (elem.get_attribute('id') or ''):
            # Parse from id like "job-card-549795520602-job-list"
            elem_id = elem.get_attribute('id')
            parts = elem_id.replace('job-card-', '').split('-')
            if parts:
                job_id = parts[0]

        if not job_id:
            # Try data-reference-id attribute
            job_id = elem.get_attribute('data-reference-id') or ''

        if not job_id:
            job_id = f"ms_{idx}_{hashlib.md5(job_url.encode()).hexdigest()[:8]}"

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
                details = self._fetch_job_details(driver, job_url)
                if details:
                    job_data.update(details)
            except Exception as e:
                logger.warning(f"Could not fetch details for {title}: {str(e)}")

        location_parts = self.parse_location(job_data.get('location', ''))
        job_data.update(location_parts)

        return job_data

    def _looks_like_location(self, text):
        """Check if a text string looks like a location (Indian cities/states)."""
        if not text or len(text) > 100:
            return False
        india_markers = [
            'Mumbai', 'Bengaluru', 'Bangalore', 'India', 'Hyderabad',
            'Delhi', 'Chennai', 'Pune', 'Kolkata', 'Gurgaon', 'Gurugram',
            'Noida', 'Maharashtra', 'Karnataka', 'Telangana', 'Tamil Nadu',
            'New Delhi'
        ]
        return any(marker in text for marker in india_markers)

    def _extract_jobs_via_js(self, driver, scraped_ids):
        """JavaScript-based extraction fallback using actual Eightfold AI DOM structure."""
        jobs = []
        try:
            js_results = driver.execute_script("""
                var results = [];

                // Try cardContainer divs first
                var cards = document.querySelectorAll('div[class*="cardContainer"]');
                if (cards.length === 0) {
                    // Try card links directly
                    cards = document.querySelectorAll('a[class*="card-"][class*="r-link"], a[id^="job-card-"]');
                }

                cards.forEach(function(card) {
                    var title = '';
                    var url = '';
                    var location = '';
                    var department = '';

                    // Get title from div[class*="title-"]
                    var titleEl = card.querySelector('div[class*="title-"]');
                    if (titleEl) title = titleEl.innerText.trim();
                    if (!title) {
                        var h2 = card.querySelector('h2[class*="position-title"]');
                        if (h2) title = h2.innerText.trim();
                    }

                    // Get URL from link
                    if (card.tagName === 'A') {
                        url = card.href;
                    } else {
                        var link = card.querySelector('a[class*="card-"], a.r-link, a[href]');
                        if (link) url = link.href;
                    }

                    // Get location
                    var locEl = card.querySelector('div[class*="position-location"]');
                    if (locEl) location = locEl.innerText.trim();

                    // Get department
                    var deptEl = card.querySelector('div[class*="fieldValue"]');
                    if (deptEl) department = deptEl.innerText.trim();

                    // Get job ID from data attributes or element id
                    var jobId = card.getAttribute('data-reference-id') || '';
                    if (!jobId && card.id && card.id.startsWith('job-card-')) {
                        jobId = card.id.replace('job-card-', '').split('-')[0];
                    }

                    if (title && url) {
                        results.push({
                            title: title,
                            url: url,
                            location: location || '',
                            department: department || '',
                            jobId: jobId || ''
                        });
                    }
                });

                return results;
            """)

            if js_results:
                for idx, item in enumerate(js_results, 1):
                    title = item.get('title', '').strip()
                    url = item.get('url', '').strip()
                    location = item.get('location', '').strip()
                    department = item.get('department', '').strip()
                    job_id = item.get('jobId', '').strip()

                    if not title or not url:
                        continue

                    if not job_id:
                        if 'pid=' in url:
                            job_id = url.split('pid=')[-1].split('&')[0]
                        else:
                            job_id = f"ms_js_{hashlib.md5(url.encode()).hexdigest()[:8]}"

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    job_data = {
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url,
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

                    location_parts = self.parse_location(location)
                    job_data.update(location_parts)

                    jobs.append(job_data)
                    scraped_ids.add(ext_id)

                logger.info(f"JS extraction found {len(jobs)} jobs")
            else:
                logger.warning("JS extraction returned no results")

        except Exception as e:
            logger.error(f"JS extraction error: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to the next page of results."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            next_selectors = [
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.XPATH, '//button[contains(@aria-label, "Next")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] button:last-child'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[class*="next"]'),
                (By.CSS_SELECTOR, '[class*="paginat"] [class*="next"]'),
            ]

            for selector_type, selector_value in next_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    if next_button.is_enabled() and next_button.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", next_button)
                        logger.info("Navigated to next page")
                        return True
                except Exception:
                    continue

            logger.warning("Could not find next page button")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by opening the job detail page."""
        details = {}
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(5)

            desc_selectors = [
                "[class*='position-job-description']",
                "[class*='job-description']",
                "[class*='description']",
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
                except Exception:
                    continue

            # Employment type
            for selector in ["[class*='employment']", "[class*='job-type']"]:
                try:
                    elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = elem.text.strip()
                    if text and len(text) < 50:
                        details['employment_type'] = text
                        break
                except Exception:
                    continue

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details from {job_url}: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
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
    scraper = MorganStanleyScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

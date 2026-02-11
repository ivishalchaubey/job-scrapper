from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import requests
import hashlib
import time
import re
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('hal_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class HALScraper:
    def __init__(self):
        self.company_name = 'Hindustan Aeronautics'
        self.url = 'https://hal-india.co.in/career'
        self.base_url = 'https://hal-india.co.in'
        # WordPress REST API endpoint discovered from the Angular SPA bundle
        self._api_url = 'https://hal-india.co.in/backend/wp-json/hal/v1/career'
        self._detail_api_url = 'https://hal-india.co.in/backend/wp-json/hal/v1/career_detail'

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
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Auto-detect failed: {str(e)}, trying explicit path")
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _get_headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://hal-india.co.in/career',
            'Origin': 'https://hal-india.co.in',
        }

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Primary strategy: use the WordPress REST API directly (faster, bypasses Selenium timeout).
        Fallback: use Selenium if API fails."""
        all_jobs = []

        # Strategy 1: Direct API call via requests (preferred - avoids slow page load)
        logger.info(f"Starting {self.company_name} scraping via WordPress REST API")
        all_jobs = self._scrape_via_api()

        if all_jobs:
            logger.info(f"API scraping successful: {len(all_jobs)} jobs found")
            return all_jobs

        # Strategy 2: Selenium fallback (with retry logic for slow govt server)
        logger.info("API approach failed, falling back to Selenium")
        all_jobs = self._scrape_via_selenium(max_pages)

        logger.info(f"Total jobs scraped: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_api(self):
        """Scrape via the WordPress REST API that powers the Angular SPA.
        The career page calls POST /backend/wp-json/hal/v1/career with empty FormData."""
        jobs = []
        headers = self._get_headers()

        for attempt in range(3):
            try:
                logger.info(f"API attempt {attempt + 1}/3: Fetching career listings")
                # The Angular app sends a POST with empty multipart/form-data
                # Using a dummy field since requests needs at least something for multipart
                response = requests.post(
                    self._api_url,
                    headers=headers,
                    files={'dummy': (None, '')},
                    timeout=120,
                )

                if response.status_code != 200:
                    logger.warning(f"API returned status {response.status_code}")
                    # Check for WAF block
                    if 'Unauthorized' in response.text:
                        logger.warning("Request blocked by WAF, retrying...")
                        time.sleep(5)
                        continue
                    continue

                data = response.json()
                career_list = data.get('career', [])

                if not career_list:
                    logger.warning("API returned empty career list")
                    continue

                logger.info(f"API returned {len(career_list)} career postings")

                for item in career_list:
                    try:
                        title = (item.get('title') or '').strip()
                        if not title or len(title) < 3:
                            continue

                        career_id = item.get('id', '')
                        division = (item.get('division') or '').strip()
                        floated_date = (item.get('floated_date') or '').strip()
                        active_upto = (item.get('activeupto') or '').strip()

                        # Build apply URL pointing to the career detail page
                        apply_url = f"{self.url}"
                        if career_id:
                            # The Angular app navigates to career-details with state.id
                            apply_url = f"{self.base_url}/career-details"

                        # Try to get more detail (job_url, file links) from the detail API
                        detail_url = ''
                        description = ''
                        if career_id:
                            detail_info = self._get_career_detail(career_id, headers)
                            if detail_info:
                                detail_url = detail_info.get('job_url', '')
                                description = detail_info.get('description', '')
                                # If there's a PDF file, use it as the apply URL
                                file_data = detail_info.get('file', {})
                                if isinstance(file_data, dict):
                                    file_list = file_data.get('file', [])
                                    if file_list and isinstance(file_list, list):
                                        first_file = file_list[0]
                                        if isinstance(first_file, dict) and first_file.get('filename'):
                                            apply_url = first_file['filename']

                        if detail_url:
                            apply_url = detail_url

                        # Determine location from division name
                        location = self._extract_location_from_division(division)
                        loc_data = self.parse_location(location)

                        job_id = career_id if career_id else hashlib.md5(title.encode()).hexdigest()[:12]

                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'apply_url': apply_url or self.url,
                            'location': location,
                            'department': division,
                            'employment_type': '',
                            'description': description,
                            'posted_date': floated_date,
                            'city': loc_data.get('city', ''),
                            'state': loc_data.get('state', ''),
                            'country': loc_data.get('country', 'India'),
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })

                    except Exception as e:
                        logger.error(f"Error parsing career item: {str(e)}")
                        continue

                if jobs:
                    return jobs

            except requests.exceptions.Timeout:
                logger.warning(f"API attempt {attempt + 1} timed out")
                time.sleep(5)
            except requests.exceptions.RequestException as e:
                logger.error(f"API attempt {attempt + 1} request error: {str(e)}")
                time.sleep(5)
            except Exception as e:
                logger.error(f"API attempt {attempt + 1} error: {str(e)}")
                time.sleep(5)

        return jobs

    def _get_career_detail(self, career_id, headers):
        """Fetch detail for a specific career posting from the detail API."""
        try:
            response = requests.post(
                self._detail_api_url,
                headers=headers,
                files={'id': (None, str(career_id))},
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
                career_list = data.get('career', [])
                if career_list and isinstance(career_list, list):
                    return career_list[0]
        except Exception as e:
            logger.debug(f"Could not fetch detail for career {career_id}: {str(e)}")
        return None

    def _extract_location_from_division(self, division):
        """Extract city/location from HAL division name.
        HAL divisions typically include location, e.g. 'Accessories Division, Lucknow'."""
        if not division:
            return 'India'

        # Common HAL locations mapped from division names
        location_keywords = {
            'Bangalore': 'Bangalore, Karnataka, India',
            'Bengaluru': 'Bangalore, Karnataka, India',
            'Lucknow': 'Lucknow, Uttar Pradesh, India',
            'Nashik': 'Nashik, Maharashtra, India',
            'Koraput': 'Koraput, Odisha, India',
            'Korwa': 'Korwa, Uttar Pradesh, India',
            'Hyderabad': 'Hyderabad, Telangana, India',
            'Kanpur': 'Kanpur, Uttar Pradesh, India',
            'Barrackpore': 'Barrackpore, West Bengal, India',
            'Sunabeda': 'Sunabeda, Odisha, India',
        }

        for keyword, location in location_keywords.items():
            if keyword.lower() in division.lower():
                return location

        return 'India'

    def _scrape_via_selenium(self, max_pages):
        """Fallback scraping method using Selenium for when the API is unavailable."""
        all_jobs = []
        driver = None

        for attempt in range(3):
            try:
                driver = self.setup_driver()
                logger.info(f"Selenium attempt {attempt + 1}/3: Loading {self.url}")

                # Do NOT set page_load_timeout - let it take as long as needed
                driver.get(self.url)

                # Wait for Angular SPA to render (govt site is slow)
                time.sleep(20)

                # Scroll for lazy loading
                for _ in range(5):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)

                for page in range(max_pages):
                    page_jobs = self._extract_jobs(driver)
                    if not page_jobs:
                        break
                    all_jobs.extend(page_jobs)
                    logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")
                    if not self._go_to_next_page(driver):
                        break
                    time.sleep(5)

                if all_jobs:
                    break

            except Exception as e:
                logger.error(f"Selenium attempt {attempt + 1} error: {str(e)}")
                # On timeout, try to scrape whatever loaded
                if driver and 'timed out' in str(e).lower():
                    try:
                        driver.execute_script("window.stop();")
                        time.sleep(5)
                        page_jobs = self._extract_jobs(driver)
                        if page_jobs:
                            all_jobs.extend(page_jobs)
                    except:
                        pass
            finally:
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None

            if all_jobs:
                break
            if attempt < 2:
                time.sleep(10)

        return all_jobs

    def _extract_jobs(self, driver):
        jobs = []
        try:
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: HAL-specific table structure (Angular SPA renders a career table)
                var rows = document.querySelectorAll('table tbody tr, table tr');
                for (var i = 0; i < rows.length; i++) {
                    var row = rows[i];
                    var cells = row.querySelectorAll('td');
                    if (cells.length < 2) continue;

                    // HAL table: Division | Title (clickable) | Floated Date | Due Date
                    var division = cells[0] ? cells[0].innerText.trim() : '';
                    var titleCell = cells.length >= 2 ? cells[1] : null;
                    var title = titleCell ? titleCell.innerText.trim() : '';
                    var floatedDate = cells.length >= 3 ? cells[2].innerText.trim() : '';
                    var dueDate = cells.length >= 4 ? cells[3].innerText.trim() : '';

                    if (!title || title.length < 3 || title.length > 300) continue;
                    // Skip header rows
                    if (title.toLowerCase() === 'title' || title.toLowerCase() === 'subject') continue;

                    var link = titleCell ? titleCell.querySelector('a[href]') : null;
                    var href = link ? link.href : '';

                    var key = title + '|' + division;
                    if (seen[key]) continue;
                    seen[key] = true;

                    results.push({
                        title: title,
                        division: division,
                        url: href,
                        floated_date: floatedDate,
                        due_date: dueDate,
                        location: ''
                    });
                }

                // Strategy 2: Any clickable career links
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="career"], a[href*="Career"]');
                    for (var i = 0; i < links.length; i++) {
                        var el = links[i];
                        var text = (el.innerText || '').trim();
                        var href = el.href || '';
                        if (text.length > 5 && text.length < 300 && !seen[href]) {
                            seen[href] = true;
                            results.push({title: text, division: '', url: href, floated_date: '', due_date: '', location: ''});
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} items")
                seen_titles = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    division = jdata.get('division', '').strip()
                    url = jdata.get('url', '').strip()
                    floated_date = jdata.get('floated_date', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    location = self._extract_location_from_division(division)
                    loc_data = self.parse_location(location)
                    job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url or self.url,
                        'location': location,
                        'department': division,
                        'employment_type': '',
                        'description': '',
                        'posted_date': floated_date,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except: pass
        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")
        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] a[class*="next"]'),
                (By.CSS_SELECTOR, '[class*="pagination"] button[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="load-more"]'),
                (By.XPATH, '//button[contains(text(), "Load more")]'),
                (By.XPATH, '//button[contains(text(), "Show more")]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except:
                    continue
            return False
        except:
            return False

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str: return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1: result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str: result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = HALScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

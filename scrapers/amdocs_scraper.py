from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import re

try:
    import requests
except ImportError:
    requests = None

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('amdocs_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class AmdocsScraper:
    def __init__(self):
        self.company_name = "Amdocs"
        self.url = "https://jobs.amdocs.com/careers?_gl=1*15dwam3*_gcl_au*MTYwNTkzMTc1OS4xNzcyMDE2OTU3*_ga*MTg3Nzg4OTE0LjE3NzIwMTY5NTY.*_ga_EVYPKWJHSE*czE3NzIwMTY5NTYkbzEkZzEkdDE3NzIwMTY5NTYkajYwJGwwJGgw&start=0&location=IN&pid=563431012320217&sort_by=distance&filter_include_remote=1"
        self.api_domain = 'amdocs.com'
        self.api_base = 'https://jobs.amdocs.com'

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
        except Exception:
            driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

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
        """Scrape Amdocs jobs using Eightfold AI API directly."""
        all_jobs = []
        num_per_page = 20
        max_results = max_pages * num_per_page
        scraped_ids = set()

        api_url = f'{self.api_base}/api/apply/v2/jobs'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': self.url,
        }

        start = 0
        page = 1

        while start < max_results and page <= max_pages:
            params = {
                'domain': self.api_domain,
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

        job_id = str(pos.get('id', ''))
        if not job_id:
            job_id = f"amdocs_api_{hashlib.md5(title.encode()).hexdigest()[:8]}"

        apply_url = pos.get('canonicalPositionUrl', '') or pos.get('apply_url', '')
        if not apply_url:
            apply_url = f"{self.api_base}/careers?pid={job_id}&domain={self.api_domain}"

        # Extract location
        location = pos.get('location', '')
        if isinstance(location, list) and location:
            location = location[0] if isinstance(location[0], str) else str(location[0])
        elif not isinstance(location, str):
            location = ''

        department = pos.get('department', '') or pos.get('team', '') or pos.get('business_unit', '') or ''
        if isinstance(department, list) and department:
            department = department[0]

        employment_type = pos.get('type', '') or pos.get('employment_type', '') or ''
        if isinstance(employment_type, list) and employment_type:
            employment_type = employment_type[0]

        description = pos.get('job_description', '') or pos.get('description', '') or ''
        if description:
            description = description[:3000]

        posted_date = pos.get('t_create', '') or pos.get('date_created', '') or ''
        experience_level = pos.get('experience', '') or pos.get('experience_level', '') or ''

        # Remote type
        remote_type = ''
        work_option = pos.get('work_location_option', '') or pos.get('location_flexibility', '') or ''
        if isinstance(work_option, str):
            if 'remote' in work_option.lower():
                remote_type = 'Remote'
            elif 'hybrid' in work_option.lower():
                remote_type = 'Hybrid'
            elif 'onsite' in work_option.lower() or 'on-site' in work_option.lower():
                remote_type = 'On-site'

        job_function = pos.get('job_function', '') or pos.get('function', '') or ''
        if isinstance(job_function, list) and job_function:
            job_function = job_function[0]

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
            'job_function': str(job_function),
            'experience_level': str(experience_level),
            'salary_range': '',
            'remote_type': remote_type,
            'status': 'active'
        }

        location_parts = self.parse_location(location)
        job_data.update(location_parts)

        return job_data

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: Scrape Amdocs jobs using Selenium with Eightfold AI DOM selectors."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")
            driver.get(self.url)

            # Wait for Eightfold AI SPA to render
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'div[class*="cardContainer"], a[class*="card-"], '
                        'div[class*="position-card"], div.position-card'
                    ))
                )
                logger.info("Job card containers detected")
            except Exception as e:
                logger.warning(f"Timeout waiting for card containers: {str(e)}")
                time.sleep(8)

            # Scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            scraped_ids = set()
            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")

                # Scroll page to load all cards
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.5)

                jobs_on_page = self._extract_jobs_from_page(driver, scraped_ids)
                all_jobs.extend(jobs_on_page)
                logger.info(f"Page {current_page}: found {len(jobs_on_page)} jobs (total: {len(all_jobs)})")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver):
                        break
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
        """Extract job listings from the current page using Eightfold AI DOM selectors."""
        jobs = []
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Eightfold AI card containers
                var cards = document.querySelectorAll(
                    'div[class*="cardContainer"], a[class*="card-"][class*="r-link"], ' +
                    'a[id^="job-card-"], div.position-card'
                );

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = (card.innerText || '').trim();
                    if (text.length < 5) continue;

                    var title = '';
                    var url = '';
                    var location = '';
                    var department = '';

                    // Title extraction
                    var titleEl = card.querySelector(
                        'div[class*="title-"], h2[class*="position-title"], ' +
                        '.position-title, [class*="jobTitle"]'
                    );
                    if (titleEl) title = titleEl.innerText.trim();
                    if (!title) title = text.split('\\n')[0].trim();
                    if (!title || title.length < 3) continue;

                    // URL extraction
                    if (card.tagName === 'A') {
                        url = card.href;
                    } else {
                        var linkEl = card.querySelector('a[class*="card-"], a.r-link, a[href]');
                        if (linkEl) url = linkEl.href;
                    }

                    // Location extraction
                    var locEl = card.querySelector(
                        'div[class*="position-location"], [class*="location"]'
                    );
                    if (locEl) location = locEl.innerText.trim();
                    if (!location) {
                        var lines = text.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            var line = lines[j].trim();
                            if (line.match(/India|Pune|Gurgaon|Gurugram|Bangalore|Bengaluru|Hyderabad|Mumbai|Chennai|Noida|Delhi/i)) {
                                location = line;
                                break;
                            }
                        }
                    }

                    // Department
                    var deptEl = card.querySelector('div[class*="fieldValue"], [class*="department"]');
                    if (deptEl) department = deptEl.innerText.trim();

                    // Job ID from element attributes
                    var jobId = card.getAttribute('data-reference-id') || '';
                    if (!jobId && card.id && card.id.startsWith('job-card-')) {
                        jobId = card.id.replace('job-card-', '').split('-')[0];
                    }
                    if (!jobId && url && url.includes('pid=')) {
                        jobId = url.split('pid=')[1].split('&')[0];
                    }

                    var key = url || title;
                    if (seen[key]) continue;
                    seen[key] = true;

                    results.push({
                        title: title, url: url, location: location,
                        department: department, jobId: jobId
                    });
                }

                // Strategy 2: Generic fallback - position cards
                if (results.length === 0) {
                    var posCards = document.querySelectorAll(
                        '[class*="position-card"], [class*="job-card"], [class*="career-card"]'
                    );
                    for (var i = 0; i < posCards.length; i++) {
                        var card = posCards[i];
                        var text = (card.innerText || '').trim();
                        if (text.length < 10) continue;

                        var title = text.split('\\n')[0].trim();
                        if (!title || title.length < 3) continue;

                        var linkEl = card.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';

                        var key = url || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        results.push({
                            title: title, url: url, location: '',
                            department: '', jobId: ''
                        });
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Extracted {len(js_jobs)} job cards from page")
                seen_urls = set()
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    job_id_raw = jdata.get('jobId', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    job_id = job_id_raw if job_id_raw else f"amdocs_sel_{idx}"
                    if not job_id_raw and url:
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue
                    scraped_ids.add(ext_id)

                    loc_data = self.parse_location(location)

                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': 'India',
                        'employment_type': '',
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            if not jobs:
                logger.warning("No jobs extracted from page")
                try:
                    body_preview = driver.execute_script(
                        "return document.body ? document.body.innerText.substring(0, 500) : ''"
                    )
                    logger.info(f"Page preview: {body_preview}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Job extraction error: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to the next page of Eightfold AI results."""
        try:
            # Capture first card text for change detection
            old_first = driver.execute_script("""
                var card = document.querySelector(
                    'div[class*="cardContainer"], a[class*="card-"], a[id^="job-card-"]'
                );
                return card ? card.innerText.substring(0, 50) : '';
            """)

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
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", next_button)

                        # Poll until content changes
                        for _ in range(25):
                            time.sleep(0.2)
                            new_first = driver.execute_script("""
                                var card = document.querySelector(
                                    'div[class*="cardContainer"], a[class*="card-"], a[id^="job-card-"]'
                                );
                                return card ? card.innerText.substring(0, 50) : '';
                            """)
                            if new_first and new_first != old_first:
                                break
                        time.sleep(1)

                        logger.info("Navigated to next page")
                        return True
                except Exception:
                    continue

            # Try "Show More Positions" button (Eightfold AI pattern)
            try:
                show_more = driver.execute_script("""
                    var btn = document.querySelector('.show-more-positions, [class*="show-more"]');
                    if (btn && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                    return false;
                """)
                if show_more:
                    logger.info("Clicked 'Show More Positions' button")
                    time.sleep(3)
                    return True
            except Exception:
                pass

            logger.warning("Could not find next page button")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False


if __name__ == "__main__":
    scraper = AmdocsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

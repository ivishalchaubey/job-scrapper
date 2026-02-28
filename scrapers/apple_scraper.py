from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('apple_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class AppleScraper:
    def __init__(self):
        self.company_name = 'Apple'
        # NOTE: The en-in locale auto-filters for India jobs.
        # Do NOT add ?location=india — that param format doesn't match
        # Apple's internal location IDs and returns 0 results.
        self.url = 'https://jobs.apple.com/en-in/search'

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

        try:
            driver_path = CHROMEDRIVER_PATH
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Apple careers page"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            logger.info(f"Target URL: {self.url}")

            driver = self.setup_driver()
            driver.get(self.url)

            wait = WebDriverWait(driver, 15)

            # Wait for the job list accordion to appear
            logger.info("Waiting for job list to load...")
            try:
                wait.until(EC.presence_of_element_located((By.ID, 'search-job-list')))
                logger.info("Job list found")
            except Exception as e:
                logger.warning(f"Job list not found via ID, trying fallback: {str(e)}")
                # Fallback: wait for any job title link
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, 'a.link-inline[href*="/details/"]'
                )))
                logger.info("Job links found via fallback selector")

            # Short wait for rendering to complete
            time.sleep(2)

            # Log current URL and total results
            current_url = driver.current_url
            logger.info(f"Current URL after load: {current_url}")

            try:
                count_el = driver.find_element(By.ID, 'search-result-count')
                logger.info(f"Total results displayed: {count_el.text}")
            except Exception:
                pass

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_page(driver)
                jobs.extend(page_jobs)

                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}, total so far: {len(jobs)}")

                if current_page == 1 and len(page_jobs) == 0:
                    try:
                        page_text = driver.find_element(By.TAG_NAME, 'body').text[:500]
                        logger.warning(f"No jobs found on first page. Page text preview: {page_text}")
                    except Exception:
                        pass

                if current_page < max_pages:
                    if not self._go_to_next_page(driver):
                        logger.info("No more pages available")
                        break
                    # Wait for the job list to update after page change
                    time.sleep(2)
                    try:
                        wait.until(EC.presence_of_element_located((
                            By.CSS_SELECTOR, '#search-job-list > li'
                        )))
                    except Exception:
                        pass

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to the next page using Apple's pagination controls"""
        try:
            # Apple uses rc-pagination with a "Next Page" button
            next_button = driver.find_element(
                By.CSS_SELECTOR, 'button[aria-label="Next Page"]'
            )

            # Check if the button is disabled (last page)
            is_disabled = next_button.get_attribute('disabled')
            if is_disabled:
                logger.info("Next page button is disabled - no more pages")
                return False

            # Record current first job title to detect page change
            try:
                first_job = driver.find_element(
                    By.CSS_SELECTOR, '#search-job-list > li:first-child a.link-inline'
                )
                old_title = first_job.text.strip()
            except Exception:
                old_title = None

            # Click the next page button
            driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                next_button
            )
            time.sleep(0.5)

            try:
                next_button.click()
            except Exception:
                driver.execute_script("arguments[0].click();", next_button)

            logger.info("Clicked next page button")

            # Poll for page content to change (faster than blind sleep)
            if old_title:
                for _ in range(20):
                    time.sleep(0.3)
                    try:
                        new_first = driver.find_element(
                            By.CSS_SELECTOR,
                            '#search-job-list > li:first-child a.link-inline'
                        )
                        if new_first.text.strip() != old_title:
                            logger.info("Page content changed - new page loaded")
                            break
                    except Exception:
                        continue
            else:
                time.sleep(3)

            return True

        except Exception as e:
            logger.warning(f"Could not find or click next page button: {str(e)}")
            return False

    def _scrape_page(self, driver):
        """Scrape jobs from current page using JavaScript for speed and accuracy.

        Apple's job page uses an accordion list (ul#search-job-list) where each
        li contains:
          - a.link-inline: job title link (href has /details/{jobId}/...)
          - span.team-name: department/team
          - span.job-posted-date: posting date
          - span.table--advanced-search__location-sub: location
        """
        jobs = []

        try:
            # Extract all jobs from the current page via JavaScript
            raw_jobs = driver.execute_script("""
                var jobs = [];
                var items = document.querySelectorAll('#search-job-list > li');
                items.forEach(function(item) {
                    var titleLink = item.querySelector('a.link-inline[href*="/details/"]');
                    if (!titleLink) return;

                    var teamEl = item.querySelector('.team-name');
                    var dateEl = item.querySelector('.job-posted-date');
                    var locEl = item.querySelector('.table--advanced-search__location-sub');

                    jobs.push({
                        title: titleLink.textContent.trim(),
                        url: titleLink.href,
                        ariaLabel: titleLink.getAttribute('aria-label') || '',
                        team: teamEl ? teamEl.textContent.trim() : '',
                        posted: dateEl ? dateEl.textContent.trim() : '',
                        location: locEl ? locEl.textContent.trim() : ''
                    });
                });
                return jobs;
            """)

            if not raw_jobs:
                logger.warning("JS extraction returned no jobs, trying Selenium fallback")
                raw_jobs = self._scrape_page_selenium(driver)

            logger.info(f"Found {len(raw_jobs)} jobs on current page")

            seen_urls = set()
            for job_data in raw_jobs:
                try:
                    title = job_data.get('title', '').strip()
                    url = job_data.get('url', '').strip()

                    if not title or not url or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    # Extract job ID from URL: /details/{jobId}/...
                    job_id = self._extract_job_id(url, job_data.get('ariaLabel', ''))

                    # Parse location
                    location = job_data.get('location', '')
                    city, state, country = self.parse_location(location)

                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location if location else 'India',
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': job_data.get('team', ''),
                        'apply_url': url,
                        'posted_date': job_data.get('posted', ''),
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    jobs.append(job)

                except Exception as e:
                    logger.error(f"Error processing job: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        return jobs

    def _scrape_page_selenium(self, driver):
        """Fallback: scrape jobs using Selenium element queries"""
        raw_jobs = []
        try:
            job_items = driver.find_elements(By.CSS_SELECTOR, '#search-job-list > li')
            for item in job_items:
                try:
                    title_link = item.find_element(
                        By.CSS_SELECTOR, 'a.link-inline[href*="/details/"]'
                    )
                    title = title_link.text.strip()
                    url = title_link.get_attribute('href')
                    aria_label = title_link.get_attribute('aria-label') or ''

                    team = ''
                    try:
                        team_el = item.find_element(By.CSS_SELECTOR, '.team-name')
                        team = team_el.text.strip()
                    except Exception:
                        pass

                    posted = ''
                    try:
                        date_el = item.find_element(By.CSS_SELECTOR, '.job-posted-date')
                        posted = date_el.text.strip()
                    except Exception:
                        pass

                    location = ''
                    try:
                        loc_el = item.find_element(
                            By.CSS_SELECTOR, '.table--advanced-search__location-sub'
                        )
                        location = loc_el.text.strip()
                    except Exception:
                        pass

                    if title and url:
                        raw_jobs.append({
                            'title': title,
                            'url': url,
                            'ariaLabel': aria_label,
                            'team': team,
                            'posted': posted,
                            'location': location,
                        })
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Selenium fallback failed: {str(e)}")

        return raw_jobs

    def _extract_job_id(self, url, aria_label=''):
        """Extract Apple job ID from the detail URL or aria-label.

        URL format: /en-in/details/{jobId}/{slug}?team=...
        aria-label format: 'Job Title {jobId}'
        """
        job_id = ''

        # Try from URL first (most reliable)
        try:
            if '/details/' in url:
                parts = url.split('/details/')
                if len(parts) > 1:
                    # jobId is right after /details/, e.g. 200314122 or 200645931-1052
                    job_id = parts[1].split('/')[0].split('?')[0]
        except Exception:
            pass

        # Fallback: extract from aria-label (e.g. "IN-Technical Specialist 200314122")
        if not job_id and aria_label:
            try:
                parts = aria_label.strip().split()
                if parts and parts[-1].replace('-', '').isdigit():
                    job_id = parts[-1]
            except Exception:
                pass

        # Last resort: hash the URL
        if not job_id:
            job_id = hashlib.md5(url.encode()).hexdigest()[:12]

        return job_id

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(3)

            # Extract description
            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, '#jd-description'),
                    (By.CSS_SELECTOR, '[id*="description"]'),
                    (By.CSS_SELECTOR, '[class*="description"]'),
                    (By.CSS_SELECTOR, '[role="article"]'),
                ]

                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        desc_text = desc_elem.text.strip()
                        if desc_text and len(desc_text) > 50:
                            details['description'] = desc_text[:2000]
                            break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Could not extract description: {str(e)}")

            # Extract location if not already present
            try:
                loc_selectors = [
                    (By.CSS_SELECTOR, '[id*="location"]'),
                    (By.CSS_SELECTOR, '[class*="location"]'),
                ]

                for selector_type, selector_value in loc_selectors:
                    try:
                        loc_elem = driver.find_element(selector_type, selector_value)
                        loc_text = loc_elem.text.strip()
                        if loc_text and len(loc_text) > 2:
                            details['location'] = loc_text
                            city, state, _ = self.parse_location(loc_text)
                            details['city'] = city
                            details['state'] = state
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            # Extract team/department
            try:
                team_selectors = [
                    (By.CSS_SELECTOR, '[id*="team"]'),
                    (By.CSS_SELECTOR, '[class*="team"]'),
                ]

                for selector_type, selector_value in team_selectors:
                    try:
                        team_elem = driver.find_element(selector_type, selector_value)
                        team_text = team_elem.text.strip()
                        if team_text and len(team_text) > 2:
                            details['department'] = team_text
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass

        return details

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        # Handle "Various locations within India" pattern
        if 'various locations' in location_str.lower():
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

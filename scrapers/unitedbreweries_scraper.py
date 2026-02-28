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


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('unitedbreweries_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class UnitedBreweriesScraper:
    def __init__(self):
        self.company_name = 'United Breweries'
        self.url = 'https://careers.theheinekencompany.com/India/search/?createNewAlert=false&q=&locationsearch=India'
        # Department listing pages that contain India jobs
        self.department_urls = [
            'https://careers.theheinekencompany.com/India/go/India-Corporate-Affairs/8746801/',
            'https://careers.theheinekencompany.com/India/go/India-Finance/8746901/',
            'https://careers.theheinekencompany.com/India/go/India-Human-Resources/8747001/',
            'https://careers.theheinekencompany.com/India/go/India-Marketing-and-Sales/8747201/',
            'https://careers.theheinekencompany.com/India/go/India-Supply-Chain/8747301/',
        ]

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
            "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _bypass_age_gate(self, driver):
        """Bypass the Heineken age gate using Selenium send_keys.

        The age gate form has:
        - A country select (pre-selected to India based on URL)
        - Three input fields: #input-date-day (DD), #input-date-month (MM), #input-date-year (YYYY)
        - A submit button with class 'form-age__button'
        """
        try:
            # Wait for age gate form to be ready
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, 'input-date-day'))
            )

            # Fill date of birth using send_keys (JS value setting doesn't work)
            day_field = driver.find_element(By.ID, 'input-date-day')
            month_field = driver.find_element(By.ID, 'input-date-month')
            year_field = driver.find_element(By.ID, 'input-date-year')

            day_field.clear()
            day_field.send_keys('15')
            time.sleep(0.3)

            month_field.clear()
            month_field.send_keys('06')
            time.sleep(0.3)

            year_field.clear()
            year_field.send_keys('1990')
            time.sleep(0.3)

            logger.info("Filled age gate date fields via send_keys")

            # Click enter/submit button
            submit_btn = driver.find_element(By.CSS_SELECTOR, 'button.form-age__button')
            submit_btn.click()
            logger.info("Clicked age gate submit button")

            # Wait for redirect to careers page
            time.sleep(10)

            if 'agegate' not in driver.current_url.lower():
                logger.info(f"Age gate bypassed, now at: {driver.current_url}")
                return True
            else:
                logger.warning("Still on age gate after submit")
                return False

        except Exception as e:
            logger.error(f"Age gate bypass failed: {str(e)}")
            return False

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []
        seen_ids = set()

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping")

            # Step 1: Navigate to career page (will redirect to age gate)
            driver.get(self.url)
            time.sleep(10)

            # Step 2: Handle age gate
            if 'agegate' in driver.current_url.lower():
                logger.info("Age gate detected, bypassing...")
                if not self._bypass_age_gate(driver):
                    logger.error("Could not bypass age gate")
                    return all_jobs
            else:
                logger.info("No age gate detected")

            # Step 3: Try the main search page first
            logger.info("Checking main India search page...")
            time.sleep(3)
            page_jobs = self._scrape_page(driver, seen_ids)
            if page_jobs:
                all_jobs.extend(page_jobs)
                logger.info(f"Found {len(page_jobs)} jobs on main search page")

            # Step 4: If main search page had few/no jobs, scrape department pages
            if len(all_jobs) < 5:
                logger.info("Few jobs on main page, checking department pages...")
                for dept_url in self.department_urls:
                    try:
                        logger.info(f"Scraping department: {dept_url}")
                        driver.get(dept_url)
                        time.sleep(8)

                        # Handle age gate again if needed
                        if 'agegate' in driver.current_url.lower():
                            if not self._bypass_age_gate(driver):
                                continue

                        dept_jobs = self._scrape_page(driver, seen_ids)
                        if dept_jobs:
                            all_jobs.extend(dept_jobs)
                            logger.info(f"Found {len(dept_jobs)} jobs from department page")

                        # Paginate within department page
                        current_page = 1
                        while current_page < max_pages:
                            if not self._go_to_next_page(driver, current_page):
                                break
                            time.sleep(5)
                            current_page += 1
                            page_jobs = self._scrape_page(driver, seen_ids)
                            if not page_jobs:
                                break
                            all_jobs.extend(page_jobs)
                            logger.info(f"Department page {current_page}: {len(page_jobs)} jobs")

                    except Exception as e:
                        logger.warning(f"Error scraping department {dept_url}: {str(e)}")
                        continue

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
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            next_selectors = [
                (By.CSS_SELECTOR, 'a.paginationItemLast'),
                (By.CSS_SELECTOR, 'a.next'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.XPATH, '//a[contains(@class,"paginationItemLast")]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), "\u00bb")]'),
                (By.CSS_SELECTOR, f'a[title="Page {current_page + 1}"]'),
                (By.CSS_SELECTOR, '.pagination a.paginationItemLast'),
                (By.CSS_SELECTOR, '.paginationContainer a:last-child'),
            ]

            for selector_type, selector_value in next_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    if not next_button.is_displayed() or not next_button.is_enabled():
                        continue
                    btn_class = next_button.get_attribute('class') or ''
                    if 'disabled' in btn_class:
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Navigated to page {current_page + 1}")
                    return True
                except:
                    continue

            try:
                page_links = driver.find_elements(By.CSS_SELECTOR, '.pagination a, .paginationContainer a')
                for link in page_links:
                    text = link.text.strip()
                    if text == str(current_page + 1):
                        driver.execute_script("arguments[0].click();", link)
                        logger.info(f"Navigated to page {current_page + 1} via page number link")
                        return True
            except:
                pass

            logger.warning("Could not find next page button")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver, seen_ids):
        """Scrape jobs from current SuccessFactors page."""
        jobs = []

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: SuccessFactors job title links
                var titleLinks = document.querySelectorAll('span.jobTitle.hidden-phone a.jobTitle-link');
                if (titleLinks.length === 0) { titleLinks = document.querySelectorAll('a.jobTitle-link'); }
                if (titleLinks.length > 0) {
                    titleLinks.forEach(function(link) {
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || link.getAttribute('href') || '';
                        if (!title || !href || seen[href]) return;
                        seen[href] = true;
                        var row = link.closest('tr');
                        var location = '', department = '', postedDate = '';
                        if (row) {
                            var locElem = row.querySelector('span.jobLocation');
                            if (locElem) location = (locElem.innerText || locElem.textContent || '').trim();
                            var dateElem = row.querySelector('span.jobDate');
                            if (dateElem) postedDate = (dateElem.innerText || dateElem.textContent || '').trim();
                            var deptElem = row.querySelector('span.jobDepartment');
                            if (deptElem) department = (deptElem.innerText || deptElem.textContent || '').trim();
                        }
                        results.push({ title: title, url: href, location: location, department: department, postedDate: postedDate });
                    });
                }

                // Strategy 2: Search results table
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table.searchResults tr');
                    rows.forEach(function(row) {
                        var link = row.querySelector('a.jobTitle-link') || row.querySelector('a[href*="/job/"]') || row.querySelector('a');
                        if (!link) return;
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || link.getAttribute('href') || '';
                        if (!title || !href || href === '#' || seen[href]) return;
                        seen[href] = true;
                        var location = '', department = '', postedDate = '';
                        var locElem = row.querySelector('span.jobLocation, [class*="location"]');
                        if (locElem) location = (locElem.innerText || locElem.textContent || '').trim();
                        var deptElem = row.querySelector('span.jobDepartment, [class*="department"]');
                        if (deptElem) department = (deptElem.innerText || deptElem.textContent || '').trim();
                        var dateElem = row.querySelector('span.jobDate');
                        if (dateElem) postedDate = (dateElem.innerText || dateElem.textContent || '').trim();
                        results.push({ title: title.split('\\n')[0].trim(), url: href, location: location, department: department, postedDate: postedDate });
                    });
                }

                // Strategy 3: Generic job links fallback
                if (results.length === 0) {
                    document.querySelectorAll('a[href*="/job/"]').forEach(function(link) {
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || '';
                        if (title && title.length > 3 && title.length < 200 && href && !seen[href]) {
                            seen[href] = true;
                            var parent = link.closest('tr, div, li');
                            var location = '', department = '';
                            if (parent) {
                                var locElem = parent.querySelector('span.jobLocation, [class*="location"]');
                                if (locElem && locElem !== link) location = (locElem.innerText || '').trim();
                                var deptElem = parent.querySelector('span.jobDepartment, [class*="department"]');
                                if (deptElem && deptElem !== link) department = (deptElem.innerText || '').trim();
                            }
                            results.push({ title: title.split('\\n')[0].trim(), url: href, location: location, department: department, postedDate: '' });
                        }
                    });
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"JavaScript extraction found {len(js_jobs)} jobs")
                for jl in js_jobs:
                    title = jl.get('title', '').strip()
                    url = jl.get('url', '').strip()
                    if not title or not url:
                        continue
                    job_id = self._extract_job_id(url)
                    external_id = self.generate_external_id(job_id, self.company_name)
                    if external_id in seen_ids:
                        continue
                    location = jl.get('location', '').strip()
                    department = jl.get('department', '').strip()
                    posted_date = jl.get('postedDate', '').strip()
                    job_data = {
                        'external_id': external_id, 'company_name': self.company_name,
                        'title': title, 'apply_url': url, 'location': location,
                        'department': department, 'employment_type': '', 'description': '',
                        'posted_date': posted_date, 'city': '', 'state': '', 'country': 'India',
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    }
                    location_parts = self.parse_location(location)
                    job_data.update(location_parts)
                    jobs.append(job_data)
                    seen_ids.add(external_id)
                    logger.info(f"Extracted: {title} | {location}")
            else:
                logger.info("No jobs found on this page")

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        return jobs

    def _extract_job_id(self, job_url):
        job_id = ""
        if '/job/' in job_url:
            parts = job_url.rstrip('/').split('/')
            for part in reversed(parts):
                if part.isdigit():
                    job_id = part
                    break
        if not job_id:
            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]
        return job_id

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str: return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1: result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            if parts[1] in ['IN', 'IND', 'India']: result['country'] = 'India'
            else: result['state'] = parts[1]
        return result


if __name__ == "__main__":
    scraper = UnitedBreweriesScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

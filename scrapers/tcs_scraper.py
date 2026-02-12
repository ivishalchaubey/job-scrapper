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
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('tcs_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class TCSScraper:
    def __init__(self):
        self.company_name = 'TCS'
        self.url = 'https://ibegin.tcs.com/iBegin/jobs/search'
        # ibegin.tcs.com DNS is dead - use tcsapps.com as the working domain
        self.alt_url = 'https://ibegin.tcsapps.com/candidate/'

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

            # Primary URL ibegin.tcs.com has DNS issues - try it first, then fall back
            loaded = False
            for url in [self.url, self.alt_url]:
                try:
                    logger.info(f"Trying URL: {url}")
                    driver.get(url)
                    time.sleep(15)

                    current_url = driver.current_url
                    title = driver.title
                    logger.info(f"Loaded: {current_url} (title: {title})")

                    # Check if page actually loaded (not error page)
                    page_source = driver.page_source
                    if len(page_source) > 1000 and 'error' not in title.lower():
                        loaded = True
                        logger.info(f"Successfully loaded {url}")
                        break
                    else:
                        logger.warning(f"URL {url} loaded but seems like error page")
                except Exception as e:
                    logger.warning(f"Failed to load {url}: {str(e)}")
                    continue

            if not loaded:
                logger.error("Could not load any TCS URL")
                return all_jobs

            # TCS uses Angular SPA - wait for dynamic content
            logger.info("Waiting for Angular SPA to render...")
            time.sleep(12)

            # Scroll to trigger lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Check if we need to navigate to job search
            current_url = driver.current_url
            if '/candidate/' in current_url and '/jobs' not in current_url:
                # Try navigating to the jobs section via Angular routing
                logger.info("On candidate portal, looking for job search section...")
                try:
                    # Look for job search link/button
                    job_nav_selectors = [
                        "a[href*='jobs']",
                        "a[href*='search']",
                        "[ng-click*='job']",
                        "[ng-click*='search']",
                        "a:contains('Jobs')",
                        "a:contains('Search')",
                    ]
                    for sel in job_nav_selectors:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, sel)
                            for elem in elements:
                                text = elem.text.strip().lower()
                                if 'job' in text or 'search' in text or 'career' in text:
                                    driver.execute_script("arguments[0].click();", elem)
                                    logger.info(f"Clicked job nav: {elem.text}")
                                    time.sleep(8)
                                    break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Could not navigate to job search: {str(e)}")

            # Try with short wait for job-related elements
            short_wait = WebDriverWait(driver, 8)
            try:
                short_wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "div[class*='job'], div[class*='result'], div[class*='listing'], "
                    "a[href*='job'], table, [class*='opening'], [ng-repeat]"
                )))
                logger.info("Page content loaded with job elements")
            except Exception as e:
                logger.warning(f"Timeout waiting for job elements: {str(e)}")
                time.sleep(5)

            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                jobs = self._scrape_page(driver)
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
                (By.XPATH, f'//button[text()="{current_page + 1}"]'),
            ]
            for selector_type, selector_value in next_selectors:
                try:
                    btn = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info(f"Navigated to page {current_page + 1}")
                    time.sleep(3)
                    return True
                except:
                    continue
            return False
        except Exception as e:
            logger.error(f"Error navigating: {str(e)}")
            return False

    def _scrape_page(self, driver):
        jobs = []
        scraped_ids = set()

        try:
            logger.info(f"Current URL: {driver.current_url}")
            logger.info(f"Page title: {driver.title}")

            # Scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # STRATEGY 1: JavaScript-first extraction (most reliable for SPAs)
            logger.info("Trying JavaScript-based extraction...")
            js_jobs = driver.execute_script("""
                var results = [];

                // Strategy A: Find all links with job-related hrefs
                document.querySelectorAll('a[href]').forEach(function(link) {
                    var text = (link.innerText || '').trim();
                    var href = link.href || '';
                    if (text.length > 3 && text.length < 200 && href.length > 10) {
                        var lhref = href.toLowerCase();
                        if (lhref.includes('/job') || lhref.includes('/position') ||
                            lhref.includes('/career') || lhref.includes('/opening') ||
                            lhref.includes('/detail') || lhref.includes('/requisition') ||
                            lhref.includes('/vacancy') || lhref.includes('/role') ||
                            lhref.includes('jobid') || lhref.includes('job-id')) {
                            results.push({
                                title: text.split('\\n')[0].trim(),
                                url: href,
                                type: 'link'
                            });
                        }
                    }
                });

                // Strategy B: Find Angular ng-repeat job items
                document.querySelectorAll('[ng-repeat*="job"], [ng-repeat*="result"], [ng-repeat*="item"]').forEach(function(elem) {
                    var text = (elem.innerText || '').trim();
                    if (text.length > 20 && text.length < 600) {
                        var link = elem.querySelector('a[href]');
                        var url = link ? link.href : '';
                        results.push({
                            title: text.split('\\n')[0].trim(),
                            url: url,
                            fullText: text,
                            type: 'ng-repeat'
                        });
                    }
                });

                // Strategy C: Find divs with job-like content
                if (results.length === 0) {
                    document.querySelectorAll('div, li, tr').forEach(function(elem) {
                        var text = (elem.innerText || '').trim();
                        if (text.length > 30 && text.length < 500) {
                            var lower = text.toLowerCase();
                            var hasJobIndicators = (
                                (lower.includes('experience') || lower.includes('year')) &&
                                (lower.includes('location') || lower.includes('bangalore') ||
                                 lower.includes('mumbai') || lower.includes('pune') ||
                                 lower.includes('chennai') || lower.includes('hyderabad') ||
                                 lower.includes('delhi') || lower.includes('india'))
                            );
                            if (hasJobIndicators) {
                                var link = elem.querySelector('a[href]');
                                var url = link ? link.href : '';
                                results.push({
                                    title: text.split('\\n')[0].trim(),
                                    url: url,
                                    fullText: text,
                                    type: 'content-match'
                                });
                            }
                        }
                    });
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JavaScript extraction found {len(js_jobs)} potential jobs")
                seen = set()
                for item in js_jobs:
                    title = item.get('title', '')
                    url = item.get('url', '')
                    full_text = item.get('fullText', '')
                    item_type = item.get('type', '')

                    if not title or len(title) < 3 or title in seen:
                        continue

                    # Filter out navigation/non-job elements
                    exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy',
                               'terms', 'cookie', 'blog', 'filter', 'search jobs',
                               'jobs at tcs', 'job title', 'first', 'submit', 'email',
                               'register', 'saved', 'all jobs', 'sort by', 'filter by']
                    if any(w in title.lower() for w in exclude):
                        continue

                    seen.add(title)

                    # Parse location from full text
                    location = ''
                    experience = ''
                    department = ''
                    posted_date = ''

                    text_to_parse = full_text if full_text else title
                    if text_to_parse:
                        lines = [l.strip() for l in text_to_parse.split('\n') if l.strip()]
                        for line in lines[1:]:
                            line_lower = line.lower()
                            if not location and any(city in line_lower for city in [
                                'bangalore', 'bengaluru', 'mumbai', 'delhi', 'hyderabad',
                                'chennai', 'pune', 'kolkata', 'ahmedabad', 'gurgaon',
                                'noida', 'india', 'chandigarh', 'jaipur', 'kochi'
                            ]):
                                location = line
                            elif not experience and 'year' in line_lower:
                                experience = line
                            elif not posted_date and any(m in line for m in [
                                'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
                            ]):
                                posted_date = line

                    job_id_base = f"{title}_{url}" if url else f"{title}_{location}"
                    job_id = f"tcs_{hashlib.md5(job_id_base.encode()).hexdigest()[:12]}"

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location if location else 'India',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': '',
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    location_parts = self.parse_location(job_data.get('location', ''))
                    job_data.update(location_parts)

                    if job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job: {title}")

            # STRATEGY 2: Selenium selector-based extraction (fallback)
            if not jobs:
                logger.info("JS extraction yielded no results, trying selector-based approach...")
                job_elements = []

                # TCS-specific selectors
                selectors = [
                    ("a[href*='/job/']", "TCS job links"),
                    ("div.job-card", "TCS job cards"),
                    ("div[class*='search-result']", "TCS search results"),
                    ("tr[class*='job']", "TCS job table rows"),
                    ("div[class*='job']", "job divs"),
                    ("a[href*='job']", "job links"),
                    ("[class*='listing']", "listing elements"),
                    ("[class*='result']", "result elements"),
                    ("[class*='opening']", "opening elements"),
                    ("table tbody tr", "table rows"),
                    ("div[ng-repeat]", "ng-repeat divs"),
                    ("[ng-click*='job']", "ng-click jobs"),
                ]

                for selector, desc in selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements and len(elements) >= 2:
                            job_elements = elements
                            logger.info(f"Found {len(job_elements)} elements via: {desc} ({selector})")
                            break
                    except:
                        continue

                # Process found elements
                for idx, job_elem in enumerate(job_elements, 1):
                    try:
                        job_data = self._extract_job(job_elem, driver, idx)
                        if job_data and job_data['external_id'] not in scraped_ids:
                            jobs.append(job_data)
                            scraped_ids.add(job_data['external_id'])
                            logger.info(f"Extracted job #{len(jobs)}: {job_data.get('title', 'N/A')}")
                    except Exception as e:
                        logger.debug(f"Could not extract job {idx}: {str(e)}")

            if not jobs:
                logger.warning("Could not find job listings with any strategy")
                # Log page info for debugging
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText : ""')
                    logger.info(f"Page body text (first 500): {body_text[:500]}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        logger.info(f"Successfully extracted {len(jobs)} jobs from page")
        return jobs

    def _extract_job(self, job_elem, driver, idx):
        try:
            elem_text = job_elem.text.strip()
            elem_tag = job_elem.tag_name
            job_url = self.url

            if elem_tag == 'a':
                href = job_elem.get_attribute('href')
                if href:
                    job_url = href

            if elem_tag == 'tr':
                cells = job_elem.find_elements(By.TAG_NAME, 'td')
                if len(cells) < 2:
                    return None

                title = ""
                location = ""
                department = ""
                posted_date = ""
                experience_level = ""

                try:
                    link = job_elem.find_element(By.TAG_NAME, 'a')
                    href = link.get_attribute('href')
                    if href and 'job' in href.lower():
                        job_url = href
                    title = link.text.strip()
                except:
                    if cells:
                        title = cells[0].text.strip()

                for cell in cells[1:]:
                    cell_text = cell.text.strip()
                    if not cell_text:
                        continue
                    cell_lower = cell_text.lower()
                    if not location and any(city.lower() in cell_lower for city in [
                        'bangalore', 'mumbai', 'delhi', 'hyderabad', 'chennai',
                        'pune', 'kolkata', 'ahmedabad', 'gurgaon', 'noida', 'india'
                    ]):
                        location = cell_text
                    elif not posted_date and any(month in cell_text for month in [
                        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', '/'
                    ]):
                        posted_date = cell_text
                    elif not experience_level and 'year' in cell_lower:
                        experience_level = cell_text
                    elif not department and len(cell_text) > 3:
                        department = cell_text

            else:
                if not elem_text or len(elem_text) < 10:
                    return None

                lines = [line.strip() for line in elem_text.split('\n') if line.strip()]
                if len(lines) < 2:
                    return None

                title = lines[0]
                location = ""
                department = ""
                experience_level = ""
                posted_date = ""

                for badge in ['WALK-IN', 'WALKIN', 'NEW', 'URGENT']:
                    title = title.replace(badge, '').strip()

                for line in lines[1:]:
                    line_lower = line.lower()
                    if not location and any(city.lower() in line_lower for city in [
                        'bangalore', 'bengaluru', 'mumbai', 'delhi', 'hyderabad',
                        'chennai', 'pune', 'kolkata', 'ahmedabad', 'gurgaon', 'noida',
                        'india', 'chandigarh', 'jaipur', 'kochi', 'coimbatore'
                    ]):
                        location = line
                    elif not experience_level and 'year' in line_lower:
                        experience_level = line
                    elif not posted_date and (any(month in line for month in [
                        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
                    ]) or '/' in line) and '-' in line:
                        posted_date = line
                    elif not department and any(dept.lower() in line_lower for dept in [
                        'infrastructure', 'business', 'technology', 'consultancy',
                        'human resources', 'finance', 'quality', 'marketing',
                        'sales', 'operations', 'services', 'engineering'
                    ]):
                        department = line

            if not title or len(title) < 3:
                return None

            invalid_titles = [
                'jobs at tcs', 'job title', 'first', 'submit', 'email',
                'filter', 'search', 'login', 'register', 'home', 'saved'
            ]
            if title.lower() in invalid_titles or any(inv in title.lower() for inv in ['filter by', 'sort by']):
                return None

            job_id_base = f"{title}_{location}_{idx}" if location else f"{title}_{idx}"
            job_id = f"tcs_{hashlib.md5(job_id_base.encode()).hexdigest()[:12]}"

            if job_url == self.url and elem_tag != 'a':
                try:
                    link = job_elem.find_element(By.TAG_NAME, 'a')
                    href = link.get_attribute('href')
                    if href and 'job' in href.lower():
                        job_url = href
                except:
                    pass

            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': location if location else 'India',
                'department': department,
                'employment_type': '',
                'description': '',
                'posted_date': posted_date,
                'city': '',
                'state': '',
                'country': 'India',
                'job_function': department,
                'experience_level': experience_level,
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            location_parts = self.parse_location(job_data.get('location', ''))
            job_data.update(location_parts)

            return job_data

        except Exception as e:
            logger.debug(f"Error extracting job: {str(e)}")
            return None

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

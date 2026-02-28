from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
from pathlib import Path


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('abbott_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class AbbottScraper:
    def __init__(self):
        self.company_name = 'Abbott'
        self.url = 'https://www.jobs.abbott/us/en/search-results?qcountry=India'

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
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"Service driver failed: {str(e)}, trying fallback")
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
            wait = WebDriverWait(driver, 10)

            # Smart wait for Phenom SPA to render (replaces blind sleep(15))
            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "div.job-title, li[data-ph-at-id='job-listing'], a.au-target, div.ph-facet-and-search-results-area"
                )))
                logger.info("Phenom job listings detected")
            except:
                logger.warning("Timeout waiting for Phenom job listings, using fallback wait")
                time.sleep(5)

            # Single quick scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

            current_page = 1
            while current_page <= max_pages:
                jobs = self._scrape_page(driver, wait)
                all_jobs.extend(jobs)
                logger.info(f"Page {current_page}: found {len(jobs)} jobs")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver):
                        break
                    # No extra sleep needed — _go_to_next_page polls for change
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
            time.sleep(0.5)

            # Capture current first job text for change detection
            old_first = driver.execute_script("""
                var card = document.querySelector('div.job-title');
                return card ? card.innerText.substring(0, 50) : '';
            """)

            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[data-ph-at-id="pagination-next-link"]'),
                (By.CSS_SELECTOR, 'a.next-btn'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'a[data-ph-at-id="pagination-next-btn"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '.pagination-next a'),
                (By.CSS_SELECTOR, 'a[data-ph-at-id="next-page"]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if not btn.is_displayed():
                        continue
                    driver.execute_script("arguments[0].click();", btn)

                    # Poll for page change (max 4s, usually <1s)
                    for _ in range(20):
                        time.sleep(0.2)
                        new_first = driver.execute_script("""
                            var card = document.querySelector('div.job-title');
                            return card ? card.innerText.substring(0, 50) : '';
                        """)
                        if new_first and new_first != old_first:
                            break
                    time.sleep(0.5)  # Brief settle after change detected
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
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)

            job_elements = []

            # PRIMARY: Use JavaScript to extract directly from div.job-title elements
            # Abbott's Phenom implementation: div.job-title > span (inside parent a tag with job URL)
            # li.job-cart is the FAVORITES widget, NOT job listings - do NOT use it
            logger.info("Trying JS-based Phenom extraction from div.job-title")
            js_jobs = driver.execute_script("""
                var results = [];
                // Method 1: div.job-title span (most reliable for Abbott)
                var jobTitles = document.querySelectorAll('div.job-title');
                for (var i = 0; i < jobTitles.length; i++) {
                    var titleSpan = jobTitles[i].querySelector('span');
                    var titleText = titleSpan ? titleSpan.innerText.trim() : jobTitles[i].innerText.trim();
                    // Parent is an <a> tag with the job URL
                    var parentA = jobTitles[i].closest('a');
                    var url = parentA ? parentA.href : '';
                    if (!url) {
                        // Look for sibling or nearby link
                        var parentLi = jobTitles[i].closest('li');
                        if (parentLi) {
                            var link = parentLi.querySelector('a[href*="/job/"]');
                            url = link ? link.href : '';
                        }
                    }
                    if (titleText && titleText.length > 2) {
                        results.push({title: titleText, url: url});
                    }
                }
                // Method 2: a[href*="/job/"] links as fallback
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="/job/"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var text = jobLinks[i].innerText.trim();
                        var href = jobLinks[i].href || '';
                        if (text.length > 2 && text.length < 200) {
                            results.push({title: text.split('\\n')[0].trim(), url: href});
                        }
                    }
                }
                return results;
            """)

            if js_jobs and len(js_jobs) > 0:
                logger.info(f"JS Phenom extraction found {len(js_jobs)} jobs from div.job-title")
                seen_titles = set()
                for jdx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    if not title or title in seen_titles or len(title) < 3:
                        continue
                    seen_titles.add(title)

                    if url and url.startswith('/'):
                        url = f"https://www.jobs.abbott{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url or self.url,
                        'location': '',
                        'department': '',
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
                    })
                if jobs:
                    logger.info(f"Successfully extracted {len(jobs)} jobs via JS")
                    return jobs

            # SECONDARY: Selenium-based selectors (skip li.job-cart which is favorites widget)
            phenom_selectors = [
                "div.job-title",                              # Job title container (best)
                "a[href*='/job/'][href*='abbott']",           # Job links with abbott domain
                "li[data-ph-at-id='job-listing']",           # Phenom standard job listing
                "a[data-ph-at-id='job-link']",               # Phenom standard job link
                "div.ph-card-container",                       # Phenom card container
                "section#search-results-list li",             # Search results list items
            ]

            short_wait = WebDriverWait(driver, 8)
            for selector in phenom_selectors:
                try:
                    short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Found {len(elements)} listings using Phenom selector: {selector}")
                        break
                except:
                    continue

            # Secondary: broader selectors
            if not job_elements:
                broader_selectors = [
                    "[class*='search-result'] li",
                    "[class*='job-card']",
                    "[class*='job-listing']",
                    "a[href*='/job/']",
                    "[role='listitem']",
                    ".card",
                ]
                for selector in broader_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            job_elements = elements
                            logger.info(f"Found {len(elements)} listings using broader selector: {selector}")
                            break
                    except:
                        continue

            # FINAL FALLBACK: Generic JS-based link extraction
            if not job_elements and not jobs:
                logger.info("Trying generic JS-based link extraction fallback")
                js_links = driver.execute_script("""
                    var results = [];
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var href = links[i].href || '';
                        var text = (links[i].innerText || '').trim();
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            if (href.includes('/job') || href.includes('/position') || href.includes('/career') || href.includes('/opening')) {
                                results.push({title: text.split('\\n')[0].trim(), url: href});
                            }
                        }
                    }
                    return results;
                """)
                if js_links:
                    logger.info(f"Generic JS fallback found {len(js_links)} links")
                    seen_urls = set()
                    for jdx, link_data in enumerate(js_links):
                        title = link_data.get('title', '')
                        url = link_data.get('url', '')
                        if not title or not url or len(title) < 3 or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                        if url and url.startswith('/'):
                            url = f"https://www.jobs.abbott{url}"
                        job_data = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'apply_url': url,
                            'location': '',
                            'department': '',
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
                        jobs.append(job_data)

            # Process Selenium-found elements
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

            tag_name = job_elem.tag_name

            if tag_name == 'a':
                title = job_elem.text.strip().split('\n')[0]
                job_url = job_elem.get_attribute('href')
            elif tag_name == 'div':
                # Could be div.job-title - extract span text
                try:
                    span = job_elem.find_element(By.TAG_NAME, 'span')
                    title = span.text.strip()
                except:
                    title = job_elem.text.strip().split('\n')[0]
                # Look for nearest link
                try:
                    parent_li = job_elem.find_element(By.XPATH, './ancestor::li')
                    link = parent_li.find_element(By.CSS_SELECTOR, "a.au-target, a[href*='/job/'], a[data-ph-at-id='job-link']")
                    job_url = link.get_attribute('href')
                    if not title:
                        title = link.text.strip().split('\n')[0]
                except:
                    pass
            else:
                # li element (job-cart or job-listing)
                # Try Phenom-specific selectors first
                phenom_title_selectors = [
                    "div.job-title span",
                    "div.job-title",
                    "a.au-target",
                    "a[data-ph-at-id='job-link']",
                    "a[href*='/job/']",
                    "h3 a", "h2 a",
                    "[class*='title'] a",
                    "a"
                ]
                for sel in phenom_title_selectors:
                    try:
                        elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                        text = elem.text.strip()
                        href = elem.get_attribute('href') or ''
                        if text:
                            title = text.split('\n')[0]
                        if href and '/job/' in href:
                            job_url = href
                        if title:
                            break
                    except:
                        continue

                # If we have title but no URL, try to find any link
                if title and not job_url:
                    try:
                        link = job_elem.find_element(By.CSS_SELECTOR, "a[href*='/job/'], a.au-target, a[href]")
                        job_url = link.get_attribute('href')
                    except:
                        pass

            if not title:
                title = job_elem.text.strip().split('\n')[0]
            if not title or not job_url:
                # Allow jobs without URL if they have a title
                if not title:
                    return None
                if not job_url:
                    job_url = self.url

            if job_url and job_url.startswith('/'):
                job_url = f"https://www.jobs.abbott{job_url}"

            job_id = hashlib.md5((job_url or title).encode()).hexdigest()[:12]
            if job_url and '/job/' in job_url:
                parts = job_url.split('/job/')[-1].split('/')
                if parts[0]:
                    job_id = parts[0]

            # Extract location from Phenom card
            location = ""
            department = ""
            all_text = job_elem.text.strip()
            for line in all_text.split('\n')[1:]:
                line_s = line.strip()
                if any(c in line_s for c in ['India', 'Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Pune', 'Gurgaon', 'Hyderabad', 'Kolkata']):
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

            if FETCH_FULL_JOB_DETAILS and job_url and job_url != self.url:
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
    scraper = AbbottScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

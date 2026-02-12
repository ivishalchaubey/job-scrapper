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

logger = setup_logger('techmahindra_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class TechMahindraScraper:
    def __init__(self):
        self.company_name = 'Tech Mahindra'
        self.url = 'https://careers.techmahindra.com/Currentopportunity.aspx#Advance'

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

            # Wait 15s for Drupal/AJAX rendering on ASP.NET page
            time.sleep(15)

            # Try to wait for the joblisting container
            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "div.joblisting, div.card-annimation-bar, a[href*='Registration.aspx']"
                )))
                logger.info("Page elements detected")
            except:
                logger.warning("Timeout waiting for joblisting container")

            # Scroll to trigger any lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1
            while current_page <= max_pages:
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
            logger.error(f"Error: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()

    def _go_to_next_page(self, driver, current_page):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a.next'), (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] a.next'),
                (By.XPATH, f'//a[text()="{current_page + 1}"]'),
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
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # PRIMARY: Use JavaScript to extract jobs from div.joblisting container
            # The Drupal site has job titles in plain divs inside div.joblisting
            logger.info("Trying JavaScript extraction from div.joblisting")
            js_jobs = driver.execute_script("""
                var results = [];
                var container = document.querySelector('.joblisting');
                if (container) {
                    // Get all inner divs that contain text (job titles)
                    var allDivs = container.querySelectorAll('div div');
                    for (var i = 0; i < allDivs.length; i++) {
                        var div = allDivs[i];
                        var text = (div.innerText || '').trim();
                        // Filter: job titles are typically 5-150 chars, no HTML children with lots of text
                        if (text.length > 4 && text.length < 150 && div.children.length === 0) {
                            // Check it's not a label or button
                            var lower = text.toLowerCase();
                            if (lower !== 'search' && lower !== 'apply' && lower !== 'submit' &&
                                lower !== 'next' && lower !== 'previous' && lower !== 'reset' &&
                                !lower.startsWith('page') && lower.indexOf('select') === -1) {
                                results.push({title: text, index: i});
                            }
                        }
                    }
                }
                return results;
            """)

            if js_jobs and len(js_jobs) > 0:
                logger.info(f"JavaScript found {len(js_jobs)} potential job titles from .joblisting")
                seen_titles = set()
                for idx, job_data in enumerate(js_jobs, 1):
                    title = job_data.get('title', '').strip()
                    if not title or title in seen_titles:
                        continue
                    # Skip non-job entries (locations, categories, etc.)
                    if len(title) < 5:
                        continue
                    seen_titles.add(title)
                    job_id = f"techm_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                if jobs:
                    logger.info(f"Extracted {len(jobs)} jobs from .joblisting container")
                    return jobs

            # SECONDARY: Try broader JavaScript extraction from card-annimation-bar or any job-like divs
            logger.info("Trying broader JavaScript extraction")
            js_jobs2 = driver.execute_script("""
                var results = [];
                // Try card animation bars
                var cards = document.querySelectorAll('.card-annimation-bar');
                if (cards.length > 0) {
                    for (var i = 0; i < cards.length; i++) {
                        var text = (cards[i].innerText || '').trim();
                        if (text.length > 4) {
                            var lines = text.split('\\n');
                            results.push({title: lines[0].trim(), fullText: text});
                        }
                    }
                }
                // Also try any div that looks like a job listing
                if (results.length === 0) {
                    var allDivs = document.querySelectorAll('div');
                    for (var i = 0; i < allDivs.length; i++) {
                        var div = allDivs[i];
                        var cls = (div.className || '').toLowerCase();
                        if (cls.indexOf('job') !== -1 || cls.indexOf('listing') !== -1 || cls.indexOf('opportunity') !== -1) {
                            var innerDivs = div.querySelectorAll('div');
                            for (var j = 0; j < innerDivs.length; j++) {
                                var innerText = (innerDivs[j].innerText || '').trim();
                                if (innerText.length > 4 && innerText.length < 150 && innerDivs[j].children.length === 0) {
                                    results.push({title: innerText, fullText: innerText});
                                }
                            }
                            if (results.length > 0) break;
                        }
                    }
                }
                return results;
            """)

            if js_jobs2 and len(js_jobs2) > 0:
                logger.info(f"Broader JS found {len(js_jobs2)} potential jobs")
                seen_titles = set()
                for idx, job_data in enumerate(js_jobs2, 1):
                    title = job_data.get('title', '').strip()
                    if not title or title in seen_titles or len(title) < 5:
                        continue
                    seen_titles.add(title)
                    job_id = f"techm_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                if jobs:
                    logger.info(f"Broader JS extracted {len(jobs)} jobs")
                    return jobs

            # TERTIARY: Selenium-based selectors
            job_elements = []
            selectors = [
                "div.joblisting div",
                "div.card-annimation-bar",
                "a[href*='Registration.aspx']",
                "a[href*='CurrentOpportunity']",
                "table tbody tr",
                "[class*='opportunity']",
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

            for idx, elem in enumerate(job_elements, 1):
                try:
                    job = self._extract_job(elem, driver, wait, idx)
                    if job and job['external_id'] not in scraped_ids:
                        jobs.append(job)
                        scraped_ids.add(job['external_id'])
                        logger.info(f"Extracted: {job.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"Error {idx}: {str(e)}")

            # FINAL FALLBACK: JS-based link extraction
            if not jobs:
                logger.info("Trying JS-based link extraction fallback")
                try:
                    js_links = driver.execute_script("""
                        var results = [];
                        document.querySelectorAll('a[href]').forEach(function(link) {
                            var text = (link.innerText || '').trim();
                            var href = link.href || '';
                            if (text.length > 3 && text.length < 200 && href.length > 10) {
                                var lhref = href.toLowerCase();
                                if (lhref.includes('/job') || lhref.includes('/position') || lhref.includes('/career') ||
                                    lhref.includes('/opening') || lhref.includes('/detail') || lhref.includes('/vacancy') ||
                                    lhref.includes('/role') || lhref.includes('/requisition') || lhref.includes('/apply') ||
                                    lhref.includes('opportunity') || lhref.includes('registration')) {
                                    results.push({title: text.split('\\n')[0].trim(), url: href});
                                }
                            }
                        });
                        return results;
                    """)
                    if js_links:
                        seen = set()
                        exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq']
                        for link_data in js_links:
                            title = link_data.get('title', '')
                            url = link_data.get('url', '')
                            if not title or not url or len(title) < 3 or title in seen:
                                continue
                            if any(w in title.lower() for w in exclude):
                                continue
                            seen.add(title)
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                            jobs.append({
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name,
                                'title': title,
                                'description': '', 'location': '', 'city': '', 'state': '',
                                'country': 'India', 'employment_type': '', 'department': '',
                                'apply_url': url, 'posted_date': '', 'job_function': '',
                                'experience_level': '', 'salary_range': '', 'remote_type': '', 'status': 'active'
                            })
                        if jobs:
                            logger.info(f"JS link fallback found {len(jobs)} jobs")
                except Exception as e:
                    logger.error(f"JS fallback error: {str(e)}")

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
                # Try to get text directly from the div
                text = job_elem.text.strip()
                if text:
                    title = text.split('\n')[0].strip()
                # Try to find a link inside
                for sel in ["a[href*='Registration'], a[href*='opportunity'], a[href*='job'], a"]:
                    try:
                        elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                        link_title = elem.text.strip()
                        link_url = elem.get_attribute('href')
                        if link_title:
                            title = link_title.split('\n')[0]
                        if link_url:
                            job_url = link_url
                        break
                    except:
                        continue

            if not title or len(title) < 3:
                return None
            if not job_url:
                job_url = self.url

            job_id = f"techm_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

            location = ""
            department = ""
            for line in job_elem.text.split('\n')[1:]:
                line_s = line.strip()
                if any(c in line_s for c in ['India', 'Mumbai', 'Pune', 'Bangalore', 'Chennai', 'Hyderabad', 'Delhi', 'Noida']):
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

            job_data.update(self.parse_location(job_data.get('location', '')))
            return job_data
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return None

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
    scraper = TechMahindraScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

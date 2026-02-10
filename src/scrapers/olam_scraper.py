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

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('olam_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class OlamScraper:
    def __init__(self):
        self.company_name = 'Olam'
        self.url = 'https://careers.olamgroup.com/search/?createNewAlert=false&q=&locationsearch=India&optionsFacetsDD_customfield3=&optionsFacetsDD_customfield1='

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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            driver.get(self.url)
            time.sleep(15)

            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            try:
                iframes = driver.find_elements(By.TAG_NAME, 'iframe')
                for iframe in iframes:
                    src = iframe.get_attribute('src') or ''
                    if 'job' in src.lower() or 'career' in src.lower() or 'search' in src.lower():
                        logger.info(f"Switching to iframe: {src}")
                        driver.switch_to.frame(iframe)
                        time.sleep(5)
                        break
            except Exception as e:
                logger.warning(f"Iframe check failed: {str(e)}")

            short_wait = WebDriverWait(driver, 5)
            try:
                short_wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "table.searchResults, a.jobTitle-link, span.jobTitle, tr.data-row, a[href*='/job/']"
                )))
                logger.info("Job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for job listings: {str(e)}")

            current_page = 1
            seen_ids = set()
            consecutive_empty_pages = 0
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                jobs = self._scrape_page(driver, seen_ids)
                all_jobs.extend(jobs)
                logger.info(f"Page {current_page}: found {len(jobs)} new jobs (total: {len(all_jobs)})")

                if len(jobs) == 0:
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= 2:
                        logger.info("No new jobs on 2 consecutive pages, stopping pagination")
                        break
                else:
                    consecutive_empty_pages = 0

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        break
                    time.sleep(5)
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
        jobs = []

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var titleLinks = document.querySelectorAll('span.jobTitle.hidden-phone a.jobTitle-link');
                if (titleLinks.length === 0) { titleLinks = document.querySelectorAll('a.jobTitle-link'); }
                if (titleLinks.length > 0) {
                    titleLinks.forEach(function(link) {
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || link.getAttribute('href') || '';
                        if (!title || !href) return;
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
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table.searchResults tr');
                    rows.forEach(function(row) {
                        var link = row.querySelector('a.jobTitle-link') || row.querySelector('a[href*="/job/"]') || row.querySelector('a');
                        if (!link) return;
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || link.getAttribute('href') || '';
                        if (!title || !href || href === '#') return;
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
                if (results.length === 0) {
                    document.querySelectorAll('a[href*="/job/"]').forEach(function(link) {
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || '';
                        if (title && title.length > 3 && title.length < 200 && href) {
                            results.push({ title: title.split('\\n')[0].trim(), url: href, location: '', department: '', postedDate: '' });
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
                logger.warning("JavaScript extraction found no jobs, trying Selenium fallback")
                jobs = self._scrape_page_selenium(driver, seen_ids)

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        if not jobs:
            try:
                body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                logger.info(f"Page body preview: {body_text}")
            except:
                pass
        return jobs

    def _scrape_page_selenium(self, driver, seen_ids):
        jobs = []
        try:
            job_elements = []
            for selector in ["a.jobTitle-link", "table.searchResults tr", "tr.data-row", "span.jobTitle a", "a[href*='/job/']", "div[class*='job-card']", "li[class*='job']"]:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Selenium found {len(elements)} elements using: {selector}")
                        break
                except:
                    continue
            if not job_elements:
                return jobs
            for idx, elem in enumerate(job_elements, 1):
                try:
                    job_data = self._extract_job_from_element(elem, idx)
                    if job_data and job_data['external_id'] not in seen_ids:
                        jobs.append(job_data)
                        seen_ids.add(job_data['external_id'])
                except:
                    continue
        except Exception as e:
            logger.error(f"Selenium fallback error: {str(e)}")
        return jobs

    def _extract_job_from_element(self, job_elem, idx):
        try:
            title, job_url = "", ""
            if job_elem.tag_name == 'a':
                title = job_elem.text.strip()
                job_url = job_elem.get_attribute('href')
            else:
                for sel in ["a.jobTitle-link", "span.jobTitle a", "a[href*='/job/']", "a"]:
                    try:
                        el = job_elem.find_element(By.CSS_SELECTOR, sel)
                        title = el.text.strip()
                        job_url = el.get_attribute('href')
                        if title and job_url: break
                    except: continue
            if not title:
                text = job_elem.text.strip()
                if text: title = text.split('\n')[0].strip()
            if not title or not job_url: return None
            job_id = self._extract_job_id(job_url)
            location, department = "", ""
            try:
                for sel in ["span.jobLocation", "[class*='location']"]:
                    try:
                        loc_elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                        location = loc_elem.text.strip()
                        if location: break
                    except: continue
            except: pass
            try:
                for sel in ["span.jobDepartment", "[class*='department']"]:
                    try:
                        dept_elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                        department = dept_elem.text.strip()
                        if department: break
                    except: continue
            except: pass
            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name, 'title': title, 'apply_url': job_url,
                'location': location, 'department': department, 'employment_type': '',
                'description': '', 'posted_date': '', 'city': '', 'state': '',
                'country': 'India', 'job_function': '', 'experience_level': '',
                'salary_range': '', 'remote_type': '', 'status': 'active'
            }
            job_data.update(self.parse_location(location))
            return job_data
        except Exception as e:
            logger.error(f"Error extracting job data: {str(e)}")
            return None

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
    scraper = OlamScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

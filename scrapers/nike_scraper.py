from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import stat
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('nike_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class NikeScraper:
    def __init__(self):
        self.company_name = 'Nike'
        self.url = 'https://jobs.nike.com/search-jobs/India'

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
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Nike careers page with pagination support"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)

            # Wait for SPA rendering
            time.sleep(15)

            # Wait for the job listings to appear
            wait = WebDriverWait(driver, 10)
            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "a.results-list__item-title--link, h3.results-list__item-title, ul.results-list"
                )))
                logger.info("Job listings loaded")
            except:
                logger.warning("Timeout waiting for job listings")

            # Scroll to trigger lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1
            seen_ids = set()

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_page(driver, seen_ids)
                jobs.extend(page_jobs)

                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(3)

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page"""
        try:
            next_page_num = current_page + 1

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            next_page_selectors = [
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
                (By.CSS_SELECTOR, 'a.pagination-show-more'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Clicked next page button")
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver, seen_ids):
        """Scrape jobs from current page using JavaScript for reliable extraction."""
        jobs = []
        time.sleep(2)

        try:
            # Scroll to load all content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            # Primary approach: JavaScript extraction targeting Nike's actual DOM
            # Job title links: a.results-list__item-title--link inside h3.results-list__item-title
            js_jobs = driver.execute_script("""
                var results = [];

                // Strategy 1: Nike-specific selectors
                var titleLinks = document.querySelectorAll('a.results-list__item-title--link');
                if (titleLinks.length > 0) {
                    titleLinks.forEach(function(link) {
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || link.getAttribute('href') || '';
                        if (!title || !href) return;

                        // Make absolute URL if relative
                        if (href.startsWith('/')) {
                            href = 'https://jobs.nike.com' + href;
                        }

                        // Find parent list item for location info
                        var listItem = link.closest('li') || link.closest('div');
                        var location = '';

                        if (listItem) {
                            // Look for location text in the list item
                            var locElem = listItem.querySelector('.results-list__item-location, [class*="location"], span.job-location');
                            if (locElem) {
                                location = (locElem.innerText || locElem.textContent || '').trim();
                            }
                            // If no dedicated location element, try to find text after the title
                            if (!location) {
                                var allText = listItem.innerText || '';
                                var lines = allText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                                // Title is first line, location/other info follows
                                for (var i = 1; i < lines.length; i++) {
                                    if (lines[i].length > 2 && lines[i].length < 100 && lines[i] !== title) {
                                        location = lines[i];
                                        break;
                                    }
                                }
                            }
                        }

                        results.push({
                            title: title,
                            url: href,
                            location: location
                        });
                    });
                }

                // Strategy 2: Try h3 with results-list class
                if (results.length === 0) {
                    var h3s = document.querySelectorAll('h3.results-list__item-title');
                    h3s.forEach(function(h3) {
                        var link = h3.querySelector('a');
                        if (!link) return;
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || link.getAttribute('href') || '';
                        if (!title || !href) return;

                        if (href.startsWith('/')) {
                            href = 'https://jobs.nike.com' + href;
                        }

                        var listItem = h3.closest('li') || h3.closest('div');
                        var location = '';
                        if (listItem) {
                            var locElem = listItem.querySelector('[class*="location"]');
                            if (locElem) location = (locElem.innerText || locElem.textContent || '').trim();
                        }

                        results.push({
                            title: title,
                            url: href,
                            location: location
                        });
                    });
                }

                // Strategy 3: General job link fallback
                if (results.length === 0) {
                    document.querySelectorAll('a[href*="/job/"], a[href*="/jobs/"]').forEach(function(link) {
                        var title = (link.innerText || link.textContent || '').trim();
                        var href = link.href || '';
                        if (title && title.length > 3 && title.length < 200 && href) {
                            if (href.startsWith('/')) {
                                href = 'https://jobs.nike.com' + href;
                            }
                            results.push({
                                title: title.split('\\n')[0].trim(),
                                url: href,
                                location: ''
                            });
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
                    city, state, country = self.parse_location(location)

                    job_data = {
                        'external_id': external_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country if country else 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    if FETCH_FULL_JOB_DETAILS and url:
                        full_details = self._fetch_job_details(driver, url)
                        job_data.update(full_details)

                    jobs.append(job_data)
                    seen_ids.add(external_id)
                    logger.info(f"Extracted: {title} | {location}")
            else:
                logger.warning("JavaScript extraction found no jobs, trying Selenium fallback")
                jobs = self._scrape_page_selenium(driver, seen_ids)

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        return jobs

    def _scrape_page_selenium(self, driver, seen_ids):
        """Fallback Selenium-based extraction."""
        jobs = []

        try:
            job_elements = []
            selectors = [
                "a.results-list__item-title--link",
                "h3.results-list__item-title a",
                "ul.results-list li",
                "a[href*='/job/']",
            ]

            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Selenium found {len(elements)} elements using: {selector}")
                        break
                except:
                    continue

            if not job_elements:
                logger.warning("Selenium fallback found no job elements")
                return jobs

            for idx, elem in enumerate(job_elements, 1):
                try:
                    title = ""
                    job_url = ""

                    tag_name = elem.tag_name
                    if tag_name == 'a':
                        title = elem.text.strip()
                        job_url = elem.get_attribute('href')
                    elif tag_name == 'li':
                        try:
                            link = elem.find_element(By.CSS_SELECTOR, "a.results-list__item-title--link, h3 a, a[href*='/job/']")
                            title = link.text.strip()
                            job_url = link.get_attribute('href')
                        except:
                            continue
                    else:
                        try:
                            link = elem.find_element(By.TAG_NAME, 'a')
                            title = link.text.strip()
                            job_url = link.get_attribute('href')
                        except:
                            continue

                    if not title or not job_url:
                        continue

                    if job_url.startswith('/'):
                        job_url = 'https://jobs.nike.com' + job_url

                    job_id = self._extract_job_id(job_url)
                    external_id = self.generate_external_id(job_id, self.company_name)

                    if external_id in seen_ids:
                        continue

                    location = ""
                    try:
                        parent = elem if tag_name == 'li' else elem.find_element(By.XPATH, './..')
                        loc_elem = parent.find_element(By.CSS_SELECTOR, "[class*='location']")
                        location = loc_elem.text.strip()
                    except:
                        pass

                    city, state, country = self.parse_location(location)

                    job_data = {
                        'external_id': external_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country if country else 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': job_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    jobs.append(job_data)
                    seen_ids.add(external_id)
                    logger.info(f"Selenium extracted: {title} | {location}")

                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Selenium fallback error: {str(e)}")

        return jobs

    def _extract_job_id(self, job_url):
        """Extract job ID from Nike URL."""
        job_id = ""
        if '/job/' in job_url:
            job_id = job_url.split('/job/')[-1].split('?')[0].split('/')[0]
        elif 'id=' in job_url:
            job_id = job_url.split('id=')[-1].split('&')[0]
        if not job_id:
            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]
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
                    (By.CSS_SELECTOR, 'div.job-description'),
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, '//div[contains(@class, "description")]'),
                ]

                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        if desc_elem and desc_elem.text.strip():
                            details['description'] = desc_elem.text.strip()[:2000]
                            break
                    except:
                        continue
            except:
                pass

            # Extract department
            try:
                dept_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'Department')]//following-sibling::*")
                details['department'] = dept_elem.text.strip()
            except:
                pass

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass

        return details

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'


if __name__ == "__main__":
    scraper = NikeScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

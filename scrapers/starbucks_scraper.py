from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('starbucks_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class StarbucksScraper:
    def __init__(self):
        self.company_name = 'Starbucks'
        self.url = 'https://www.starbucks.in/careers'

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
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Starbucks India careers page.

        NOTE: As of Feb 2026, the starbucks.in/careers page returns a 404 error.
        The Starbucks India (Tata Starbucks) website has removed the careers section.
        The site is now primarily a consumer ordering/rewards platform built on Angular
        with no career routes defined. This scraper attempts multiple strategies and
        returns an empty list if no careers page is found.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Strategy 1: Try the main careers URL
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(12)

            # Check if we got a 404 page
            is_404 = self._check_if_404(driver)
            if is_404:
                logger.warning(f"Careers page at {self.url} returns 404 - page has been removed")

                # Strategy 2: Try alternative career URLs
                alternative_urls = [
                    'https://www.starbucks.in/about/careers',
                    'https://www.starbucks.in/about-us/careers',
                    'https://www.starbucks.in/join-us',
                    'https://www.starbucks.in/work-with-us',
                ]

                for alt_url in alternative_urls:
                    logger.info(f"Trying alternative URL: {alt_url}")
                    try:
                        driver.get(alt_url)
                        time.sleep(8)
                        if not self._check_if_404(driver):
                            logger.info(f"Found working careers page at: {alt_url}")
                            break
                    except:
                        continue
                else:
                    # All alternative URLs also 404
                    logger.error(
                        "Starbucks India careers page has been removed. "
                        "No alternative career URLs found on starbucks.in. "
                        "The site is now a consumer ordering platform with no career section."
                    )
                    return jobs

            # If we reach here, we have a working page - try to extract jobs
            # Scroll to trigger lazy loading
            for i in range(4):
                driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {(i + 1) / 4});")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_page(driver)
                jobs.extend(page_jobs)

                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(4)

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _check_if_404(self, driver):
        """Check if the current page shows a 404 error"""
        try:
            body_text = driver.execute_script("return document.body.innerText.substring(0, 500)")
            if '404' in body_text and ('not found' in body_text.lower() or 'page not found' in body_text.lower()):
                return True
            # Starbucks-specific 404 message
            if 'coffee beans were spilled' in body_text.lower():
                return True
        except:
            pass
        return False

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page"""
        try:
            next_page_num = current_page + 1

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            next_page_selectors = [
                (By.XPATH, '//button[@aria-label="Next Page"]'),
                (By.XPATH, '//button[contains(@class, "next")]'),
                (By.XPATH, '//a[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'button.pagination-next'),
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    if next_button.is_enabled():
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

    def _scrape_page(self, driver):
        """Scrape jobs from current page using JavaScript-first extraction"""
        jobs = []
        time.sleep(3)

        # Primary: JS-based extraction for any job-like content
        js_jobs = driver.execute_script("""
            var results = [];

            // Try to find job cards using common selectors
            var selectors = [
                'div.job-tile', 'article.job-card', 'div[class*="job-card"]',
                'div[class*="opening"]', 'div[class*="position"]',
                'li[class*="job"]', 'div[class*="career"]', 'div[class*="vacancy"]'
            ];

            for (var s = 0; s < selectors.length; s++) {
                var cards = document.querySelectorAll(selectors[s]);
                if (cards.length > 0) {
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var link = card.querySelector('a');
                        var title = '';
                        var href = '';

                        if (link) {
                            title = link.innerText.trim();
                            href = link.href || '';
                        } else {
                            var h = card.querySelector('h1, h2, h3, h4, h5');
                            if (h) title = h.innerText.trim();
                        }

                        if (title && title.length > 3 && title.length < 200) {
                            results.push({title: title.split('\\n')[0].trim(), url: href});
                        }
                    }
                    break;
                }
            }

            // Fallback: Find all links that look like job postings
            if (results.length === 0) {
                var links = document.querySelectorAll('a[href]');
                var seen = {};
                var jobKeywords = ['/job/', '/jobs/', '/career', '/position/', '/opening/', '/vacancy/', '/apply/'];
                for (var i = 0; i < links.length; i++) {
                    var h = links[i].href.toLowerCase();
                    var t = links[i].innerText.trim();
                    if (t.length > 3 && t.length < 200 && !seen[links[i].href]) {
                        for (var j = 0; j < jobKeywords.length; j++) {
                            if (h.indexOf(jobKeywords[j]) !== -1) {
                                seen[links[i].href] = true;
                                results.push({title: t.split('\\n')[0].trim(), url: links[i].href});
                                break;
                            }
                        }
                    }
                }
            }

            return results;
        """)

        if js_jobs:
            logger.info(f"JS extraction found {len(js_jobs)} potential job listings")
            seen_urls = set()
            exclude_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq']

            for idx, link_data in enumerate(js_jobs):
                title = link_data.get('title', '')
                url = link_data.get('url', '')

                if not title or len(title) < 3:
                    continue
                if url in seen_urls:
                    continue
                if any(w in title.lower() for w in exclude_words):
                    continue

                seen_urls.add(url)
                job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]

                job_data = {
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
                    'apply_url': url if url else self.url,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                jobs.append(job_data)

        return jobs

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(4)

            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div.job-description'),
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, '//h2[contains(text(), "Description")]/following-sibling::div'),
                    (By.CSS_SELECTOR, 'div[id*="description"]'),
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

            try:
                dept_selectors = [
                    (By.CSS_SELECTOR, 'span[class*="department"]'),
                    (By.XPATH, '//*[contains(text(), "Department")]/following-sibling::*'),
                ]

                for selector_type, selector_value in dept_selectors:
                    try:
                        dept_elem = driver.find_element(selector_type, selector_value)
                        if dept_elem and dept_elem.text.strip():
                            details['department'] = dept_elem.text.strip()
                            break
                    except:
                        continue
            except:
                pass

            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(1)

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

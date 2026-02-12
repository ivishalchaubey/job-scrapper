from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import json
import os
from pathlib import Path


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('tataadmin_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class TataAdminScraper:
    def __init__(self):
        self.company_name = 'Tata Administrative Services'
        self.url = 'https://www.tata.com/careers/jobs/joblisting'
        self.base_url = 'https://www.tata.com'

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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(15)

            # Accept cookies if present
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button, a, div[role="button"]');
                    for (var i = 0; i < btns.length; i++) {
                        var txt = (btns[i].innerText || '').toLowerCase();
                        if ((txt.includes('accept') || txt.includes('agree') || txt.includes('got it') || txt.includes('sweet')) && txt.length < 30) {
                            btns[i].click();
                            break;
                        }
                    }
                """)
                time.sleep(2)
            except:
                pass

            # Use the internal API to fetch jobs via XHR from browser context
            # The API at /bin/tata/jobPostingsFilterServlet requires session cookies
            # Use multiple search terms to get broad coverage
            search_terms = ['a', 'e', 'i', 'o', 'u', 'Manager', 'Engineer', 'Analyst', 'Developer', 'Lead']
            seen_job_ids = set()

            for search_term in search_terms:
                if len(all_jobs) >= 100:
                    break

                start_index = 0
                for page in range(max_pages):
                    try:
                        api_result = driver.execute_script("""
                            var result = null;
                            var xhr = new XMLHttpRequest();
                            xhr.open('POST', '/bin/tata/jobPostingsFilterServlet?', false);
                            xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                            var body = 'searchTerm=' + encodeURIComponent(arguments[0]) +
                                       '&searchMode=search&startIndex=' + arguments[1] +
                                       '&resultSize=10';
                            xhr.send(body);
                            if (xhr.status === 200) {
                                try {
                                    result = JSON.parse(xhr.responseText);
                                } catch(e) {
                                    result = null;
                                }
                            }
                            return result;
                        """, search_term, start_index)

                        if not api_result or api_result.get('status') != 'Success':
                            logger.warning(f"API call failed for search term '{search_term}' page {page + 1}")
                            break

                        response = api_result.get('response', {})
                        if isinstance(response, list):
                            # This is a suggest response, skip
                            break

                        total_count = response.get('totalJobPostingsCount', 0)
                        job_postings = response.get('jobPostings', [])

                        if not job_postings:
                            break

                        logger.info(f"Search '{search_term}' page {page + 1}: {len(job_postings)} jobs (total available: {total_count})")

                        new_jobs_this_page = 0
                        for jp in job_postings:
                            job_id = str(jp.get('jobId', ''))
                            if not job_id or job_id in seen_job_ids:
                                continue
                            seen_job_ids.add(job_id)

                            title = jp.get('jobTitle', '').strip()
                            if not title or len(title) < 3:
                                continue

                            location = jp.get('location', '').strip()
                            company = jp.get('companyName', '').strip()
                            job_type = jp.get('jobType', '').strip()
                            posted_date = jp.get('publishedDate', '').strip()

                            loc_data = self.parse_location(location)
                            all_jobs.append({
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name, 'title': title,
                                'apply_url': self.url, 'location': location,
                                'department': company, 'employment_type': job_type,
                                'description': jp.get('shortDescription', '').strip(),
                                'posted_date': posted_date, 'city': loc_data.get('city', ''),
                                'state': loc_data.get('state', ''),
                                'country': loc_data.get('country', 'India'),
                                'job_function': '', 'experience_level': '', 'salary_range': '',
                                'remote_type': '', 'status': 'active'
                            })
                            new_jobs_this_page += 1

                        if new_jobs_this_page == 0:
                            # All jobs on this page were duplicates, stop paginating
                            break

                        start_index += len(job_postings)
                        if start_index >= total_count:
                            break

                    except Exception as e:
                        logger.warning(f"Error fetching page {page + 1} for '{search_term}': {str(e)}")
                        break

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver):
        """Legacy method kept for compatibility - API approach used in scrape() instead."""
        return []

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            next_selectors = [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next page"]'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), ">")]'),
                (By.XPATH, '//a[contains(@class, "next")]'),
                (By.XPATH, '//button[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.CSS_SELECTOR, 'button[title="Next"]'),
            ]

            for sel_type, sel_val in next_selectors:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except:
                    continue

            # Try JS fallback for pagination
            clicked = driver.execute_script("""
                var els = document.querySelectorAll('a, button');
                for (var i = 0; i < els.length; i++) {
                    var txt = (els[i].innerText || '').trim().toLowerCase();
                    var label = (els[i].getAttribute('aria-label') || '').toLowerCase();
                    if (txt === 'next' || txt === '>' || txt === '>>' || label.includes('next')) {
                        if (els[i].offsetParent !== null) {
                            els[i].click();
                            return true;
                        }
                    }
                }
                return false;
            """)
            if clicked:
                logger.info("Navigated to next page via JS fallback")
                return True

            # Try "Load More" as pagination alternative
            loaded = driver.execute_script("""
                var btns = document.querySelectorAll('button, a, div[role="button"]');
                for (var i = 0; i < btns.length; i++) {
                    var txt = (btns[i].innerText || '').toLowerCase().trim();
                    if ((txt.includes('load more') || txt.includes('show more') || txt.includes('view more')) && btns[i].offsetParent !== null) {
                        btns[i].click();
                        return true;
                    }
                }
                return false;
            """)
            if loaded:
                logger.info("Clicked 'Load More' for next batch of jobs")
                return True

            return False
        except:
            return False

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
    scraper = TataAdminScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

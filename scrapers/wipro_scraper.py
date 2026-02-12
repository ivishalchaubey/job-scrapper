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

logger = setup_logger('wipro_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class WiproScraper:
    def __init__(self):
        self.company_name = 'Wipro'
        self.url = 'https://careers.wipro.com/search/?q=&locationsearch=India&searchResultView=LIST'

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

        driver_path = CHROMEDRIVER_PATH

        try:
            current_permissions = os.stat(driver_path).st_mode
            os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            logger.warning(f"Could not set permissions: {str(e)}")

        try:
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"Service driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)
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
            time.sleep(12)  # SPA needs time to render

            # Wait for the job list container to appear
            wait = WebDriverWait(driver, 10)
            short_wait = WebDriverWait(driver, 5)

            # Scroll to trigger lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Wait for SuccessFactors job list elements
            try:
                short_wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    'tr.data-row, a.jobTitle-link, td.colTitle, '
                    'div[class*="jobTitle"], a[href*="jobDetail"], '
                    'li[class*="JobsList"], a[class*="jobCardTitle"]'
                )))
                logger.info("Job list container detected")
            except:
                logger.warning("Timeout waiting for job list container, proceeding anyway")

            current_page = 1
            while current_page <= max_pages:
                jobs = self._scrape_page(driver)
                all_jobs.extend(jobs)
                logger.info(f"Page {current_page}: found {len(jobs)} jobs")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        break
                    time.sleep(5)
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
            # Try various pagination selectors
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'a.next'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, f'a[title="Page {current_page + 1}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {current_page + 1}"]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info(f"Navigated to page {current_page + 1}")
                    return True
                except:
                    continue
            logger.info("No next page button found")
            return False
        except:
            return False

    def _scrape_page(self, driver):
        jobs = []
        scraped_ids = set()

        try:
            # Wipro uses SAP SuccessFactors (career55.sapsf.eu)
            # Strategy 1: SuccessFactors table rows (tr.data-row with a.jobTitle-link)
            job_rows = []
            sf_selectors = [
                'tr.data-row',
                'a.jobTitle-link',
                'td.colTitle a',
                'a[href*="jobDetail"]',
                'a[href*="job-detail"]',
            ]
            for selector in sf_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_rows = elements
                        logger.info(f"Found {len(elements)} elements using SF selector: {selector}")
                        break
                except:
                    continue

            if job_rows:
                for idx, elem in enumerate(job_rows, 1):
                    try:
                        if elem.tag_name == 'tr':
                            # Extract from table row
                            title = ''
                            job_url = ''
                            location = ''
                            try:
                                title_link = elem.find_element(By.CSS_SELECTOR, 'a.jobTitle-link, td.colTitle a, a[href*="jobDetail"]')
                                title = title_link.text.strip()
                                job_url = title_link.get_attribute('href') or ''
                            except:
                                try:
                                    title_elem = elem.find_element(By.CSS_SELECTOR, 'td.colTitle, td:first-child')
                                    title = title_elem.text.strip()
                                except:
                                    continue
                            try:
                                loc_elem = elem.find_element(By.CSS_SELECTOR, 'td.colLocation, td[class*="location"]')
                                location = loc_elem.text.strip()
                            except:
                                pass
                        elif elem.tag_name == 'a':
                            title = elem.text.strip()
                            job_url = elem.get_attribute('href') or ''
                            location = ''
                            try:
                                parent_row = elem.find_element(By.XPATH, './ancestor::tr')
                                loc_td = parent_row.find_element(By.CSS_SELECTOR, 'td.colLocation, td[class*="location"]')
                                location = loc_td.text.strip()
                            except:
                                pass
                        else:
                            continue

                        if not title or len(title) < 3:
                            continue
                        if not job_url:
                            job_url = self.url

                        job_id = hashlib.md5((job_url or title).encode()).hexdigest()[:12]
                        job_data = self._build_job_data(title, job_url, location, job_id)
                        if job_data['external_id'] not in scraped_ids:
                            jobs.append(job_data)
                            scraped_ids.add(job_data['external_id'])
                            logger.info(f"Extracted (SF): {title}")
                    except Exception as e:
                        logger.error(f"Error extracting SF row {idx}: {str(e)}")
                if jobs:
                    return jobs

            # Strategy 2: Card-based selectors (alternative SuccessFactors layout)
            card_selectors = [
                'li[class*="JobsList_jobCard"]',
                'ul[class*="jobCardResultList"] > li',
                'div[class*="job-card"]',
                'div[class*="jobCard"]',
                'a[class*="jobCardTitle"]',
                'a.jobCardTitle',
            ]
            for selector in card_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"Found {len(elements)} job cards using: {selector}")
                        for idx, card in enumerate(elements, 1):
                            try:
                                job = self._extract_job_from_card(card, idx)
                                if job and job['external_id'] not in scraped_ids:
                                    jobs.append(job)
                                    scraped_ids.add(job['external_id'])
                                    logger.info(f"Extracted (card): {job.get('title', 'N/A')}")
                            except Exception as e:
                                logger.error(f"Error extracting card {idx}: {str(e)}")
                        if jobs:
                            return jobs
                except:
                    continue

            # Strategy 3: Comprehensive JavaScript extraction
            logger.info("Trying comprehensive JavaScript extraction")
            js_jobs = driver.execute_script("""
                var results = [];

                // SuccessFactors table rows
                var rows = document.querySelectorAll('tr.data-row');
                if (rows.length > 0) {
                    rows.forEach(function(row) {
                        var titleLink = row.querySelector('a.jobTitle-link, td.colTitle a, a[href*="jobDetail"]');
                        var locTd = row.querySelector('td.colLocation, td[class*="location"]');
                        if (titleLink) {
                            results.push({
                                title: (titleLink.innerText || '').trim(),
                                url: titleLink.href || '',
                                location: locTd ? (locTd.innerText || '').trim() : ''
                            });
                        }
                    });
                    if (results.length > 0) return results;
                }

                // Card-based layout
                var cards = document.querySelectorAll('li[class*="JobsList"], div[class*="job-card"], div[class*="jobCard"]');
                if (cards.length > 0) {
                    cards.forEach(function(card) {
                        var titleLink = card.querySelector('a[class*="jobCardTitle"], a[class*="jobTitle"], a[href*="job"]');
                        var locationDiv = card.querySelector('div[class*="jobCardLocation"], div[class*="location"], span[class*="location"]');
                        if (titleLink) {
                            results.push({
                                title: (titleLink.innerText || '').trim(),
                                url: titleLink.href || '',
                                location: locationDiv ? (locationDiv.innerText || '').trim() : ''
                            });
                        }
                    });
                    if (results.length > 0) return results;
                }

                // Broadest fallback: all job-like links
                var allLinks = document.querySelectorAll('a[href]');
                var seen = {};
                allLinks.forEach(function(link) {
                    var text = (link.innerText || '').trim();
                    var href = link.href || '';
                    var lhref = href.toLowerCase();
                    if (text.length > 5 && text.length < 200 && !seen[text] &&
                        (lhref.includes('/job') || lhref.includes('jobdetail') || lhref.includes('job-detail') ||
                         lhref.includes('/requisition') || lhref.includes('/position') || lhref.includes('/career'))) {
                        var exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq', 'search'];
                        var skip = false;
                        for (var e = 0; e < exclude.length; e++) {
                            if (text.toLowerCase().includes(exclude[e])) { skip = true; break; }
                        }
                        if (!skip) {
                            seen[text] = true;
                            results.push({title: text.split('\n')[0].trim(), url: href, location: ''});
                        }
                    }
                });

                return results;
            """)
            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                for jl in js_jobs:
                    title = jl.get('title', '').strip()
                    url = jl.get('url', '').strip()
                    location = jl.get('location', '').strip()
                    if title and len(title) > 3:
                        job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                        job_data = self._build_job_data(title, url or self.url, location, job_id)
                        if job_data['external_id'] not in scraped_ids:
                            jobs.append(job_data)
                            scraped_ids.add(job_data['external_id'])
                            logger.info(f"JS Extracted: {title}")

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")
        return jobs

    def _extract_job_from_card(self, card, idx):
        """Extract job data from a single job card or link element."""
        title = ""
        job_url = ""
        location = ""

        # If the card IS a link element
        if card.tag_name == 'a':
            title = card.text.strip().split('\n')[0].strip()
            job_url = card.get_attribute('href') or ''
        else:
            # Get title and URL from the title link within the card
            for selector in ['a.jobTitle-link', 'a[class*="jobCardTitle"]', 'a.jobCardTitle',
                             'a[href*="jobDetail"]', 'a[href*="job"]', 'a']:
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, selector)
                    title = title_elem.text.strip()
                    job_url = title_elem.get_attribute('href') or ''
                    if title and job_url:
                        break
                except:
                    continue

        if not title or len(title) < 3:
            return None
        if not job_url:
            job_url = self.url

        # Get location
        for selector in ['td.colLocation', 'div[class*="jobCardLocation"]', 'div[class*="Location"]',
                         'span[class*="location"]', '[class*="location"]']:
            try:
                loc_elem = card.find_element(By.CSS_SELECTOR, selector)
                location = loc_elem.text.strip()
                if location:
                    break
            except:
                continue

        job_id = hashlib.md5((job_url or title).encode()).hexdigest()[:12]

        return self._build_job_data(title, job_url, location, job_id)

    def _build_job_data(self, title, job_url, location, job_id):
        """Build the standard job data dictionary."""
        job_data = {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'company_name': self.company_name,
            'title': title,
            'apply_url': job_url,
            'location': location,
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
        job_data.update(self.parse_location(location))
        return job_data

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
            if parts[1] in ['IN', 'IND', 'India']:
                result['country'] = 'India'
            else:
                result['state'] = parts[1]
        return result


if __name__ == "__main__":
    scraper = WiproScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['apply_url']}")

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
        self.url = 'https://jobs.apple.com/en-in/search?location=india'

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

            wait = WebDriverWait(driver, 5)
            short_wait = WebDriverWait(driver, 5)

            # Wait for page to load and dynamic content to render
            logger.info("Waiting for page to load...")
            time.sleep(12)

            # Scroll to trigger lazy-loaded content
            logger.info("Scrolling to load dynamic content...")
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Log current URL to detect redirects
            current_url = driver.current_url
            logger.info(f"Current URL after load: {current_url}")

            # Try to wait for search results with short wait and Apple-specific selectors
            try:
                short_wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, 'a[href*="/en-in/details/"], table#jobs-list tr, div[class*="table-row"], a.table-col-1'
                )))
                logger.info("Job listing container found")
            except Exception as e:
                logger.warning(f"Could not find job listing container: {str(e)}")

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_page(driver, wait, short_wait)
                jobs.extend(page_jobs)

                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}, total so far: {len(jobs)}")

                if current_page == 1 and len(page_jobs) == 0:
                    try:
                        page_text = driver.find_element(By.TAG_NAME, 'body').text[:500]
                        logger.warning(f"No jobs found on first page. Page text preview: {page_text}")
                    except:
                        pass

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(3)

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

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page"""
        try:
            next_page_selectors = [
                (By.XPATH, '//button[contains(text(), "Next Page")]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next Page"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.XPATH, '//button[contains(@class, "next")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] a:last-child'),
                (By.CSS_SELECTOR, 'a[class*="next"]'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)

                    is_disabled = next_button.get_attribute('disabled')
                    if is_disabled:
                        logger.info("Next page button is disabled - no more pages")
                        return False

                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", next_button)
                    time.sleep(1)

                    try:
                        next_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", next_button)

                    logger.info(f"Clicked next page button")
                    time.sleep(2)
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver, wait, short_wait):
        """Scrape jobs from current page"""
        jobs = []

        # Wait for job listings to load
        time.sleep(3)

        try:
            short_wait.until(lambda d: len(d.find_elements(By.TAG_NAME, 'a')) > 10)
            logger.info("Page loaded with links")
        except Exception as e:
            logger.warning(f"Page may not have loaded properly: {str(e)}")

        try:
            # PRIORITY: Apple-specific selectors
            apple_priority_selectors = [
                (By.CSS_SELECTOR, 'a[href*="/en-in/details/"]'),
                (By.CSS_SELECTOR, 'table#jobs-list tr'),
                (By.CSS_SELECTOR, 'div[class*="table-row"]'),
                (By.CSS_SELECTOR, 'a.table-col-1'),
            ]

            main_job_links = []
            seen_urls = set()

            for sel_type, sel_val in apple_priority_selectors:
                try:
                    found = driver.find_elements(sel_type, sel_val)
                    for link in found:
                        try:
                            link_text = link.text.strip()
                            link_href = link.get_attribute('href')
                            if not link_text or not link_href or len(link_text) < 3:
                                continue
                            if link_href in seen_urls:
                                continue
                            if any(skip in link_text for skip in ['Submit CV', 'Add to Favourites', 'Share this']):
                                continue
                            main_job_links.append({
                                'title': link_text,
                                'apply_url': link_href,
                                'element': link
                            })
                            seen_urls.add(link_href)
                        except:
                            continue
                    if main_job_links:
                        logger.info(f"Found {len(main_job_links)} jobs using Apple priority selector: {sel_val}")
                        break
                except:
                    continue

            # Secondary Apple selectors
            if not main_job_links:
                apple_selectors = [
                    (By.CSS_SELECTOR, 'a[href*="#jobs/"]'),
                    (By.CSS_SELECTOR, 'table#jobs-table tbody tr a'),
                    (By.CSS_SELECTOR, '[role="row"] a'),
                    (By.CSS_SELECTOR, 'tbody tr td a[href*="details"]'),
                    (By.CSS_SELECTOR, '[class*="table-col-1"] a'),
                    (By.CSS_SELECTOR, 'table[id*="jobs"] tr a'),
                    (By.CSS_SELECTOR, '[class*="table-row"] a'),
                    (By.CSS_SELECTOR, 'a[href*="/details/"]'),
                ]

                for sel_type, sel_val in apple_selectors:
                    try:
                        found = driver.find_elements(sel_type, sel_val)
                        for link in found:
                            try:
                                link_text = link.text.strip()
                                link_href = link.get_attribute('href')
                                if not link_text or not link_href or len(link_text) < 3:
                                    continue
                                if link_href in seen_urls:
                                    continue
                                if any(skip in link_text for skip in ['Submit CV', 'Add to Favourites', 'Share this']):
                                    continue
                                main_job_links.append({
                                    'title': link_text,
                                    'apply_url': link_href,
                                    'element': link
                                })
                                seen_urls.add(link_href)
                            except:
                                continue
                        if main_job_links:
                            logger.info(f"Found {len(main_job_links)} jobs using Apple selector: {sel_val}")
                            break
                    except:
                        continue

            # Fallback: get all links and filter for job detail links
            if not main_job_links:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                logger.info(f"Found {len(all_links)} total links on page, filtering for jobs...")

                for link in all_links:
                    try:
                        link_text = link.text.strip()
                        link_href = link.get_attribute('href')

                        if not link_text or not link_href:
                            continue

                        if '/details/' not in link_href and '#jobs/' not in link_href and '/en-in/details/' not in link_href:
                            continue

                        if any(skip in link_text for skip in ['Submit CV', 'Add to Favourites', 'Share this']):
                            continue

                        if link_href in seen_urls:
                            continue

                        if len(link_text) > 3:
                            main_job_links.append({
                                'title': link_text,
                                'apply_url': link_href,
                                'element': link
                            })
                            seen_urls.add(link_href)

                    except Exception as e:
                        continue

            # JS-based link extraction fallback
            if not main_job_links:
                logger.info("Trying JS-based link extraction fallback")
                js_links = driver.execute_script("""
                    var results = [];
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            var lhref = href.toLowerCase();
                            if (lhref.includes('/job') || lhref.includes('/position') || lhref.includes('/career') ||
                                lhref.includes('/opening') || lhref.includes('/detail') || lhref.includes('/requisition') ||
                                lhref.includes('/vacancy') || lhref.includes('/role')) {
                                results.push({title: text.split('\\n')[0].trim(), url: href});
                            }
                        }
                    });
                    return results;
                """)
                if js_links:
                    seen = set()
                    for link_data in js_links:
                        title = link_data.get('title', '')
                        url = link_data.get('url', '')
                        if not title or not url or len(title) < 3 or title in seen:
                            continue
                        exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog']
                        if any(w in title.lower() for w in exclude):
                            continue
                        seen.add(title)
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]
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
                            'apply_url': url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })
                    if jobs:
                        logger.info(f"JS fallback found {len(jobs)} jobs")
                        return jobs

            logger.info(f"Found {len(main_job_links)} job links on page")

            # Extract details for each job
            for idx, job_info in enumerate(main_job_links):
                try:
                    job_title = job_info['title']
                    job_link = job_info['apply_url']

                    job_id = f"apple_{idx}_{int(time.time())}"
                    try:
                        title_parts = job_title.split()
                        for part in reversed(title_parts):
                            if part.isdigit() and len(part) >= 8:
                                job_id = part
                                break

                        if job_id.startswith('apple_') and '/details/' in job_link:
                            url_parts = job_link.split('/details/')
                            if len(url_parts) > 1:
                                job_id = url_parts[1].split('/')[0].split('?')[0]

                        if job_id.startswith('apple_') and '/en-in/details/' in job_link:
                            url_parts = job_link.split('/en-in/details/')
                            if len(url_parts) > 1:
                                job_id = url_parts[1].split('/')[0].split('?')[0]
                    except Exception as e:
                        logger.debug(f"Could not extract job ID: {str(e)}")

                    # Clean up title (remove job ID if it's at the end)
                    clean_title = job_title
                    try:
                        title_words = job_title.split()
                        if title_words and title_words[-1].isdigit():
                            clean_title = ' '.join(title_words[:-1])
                    except:
                        pass

                    # Try to get location from the job element's parent
                    location = ""
                    city = ""
                    state = ""

                    try:
                        job_elem = job_info['element']
                        parent = job_elem.find_element(By.XPATH, './ancestor::*[contains(@class, "result") or contains(@role, "listitem") or self::tr][1]')

                        location_selectors = [
                            'span[class*="location"]',
                            'div[class*="location"]',
                            'p[class*="location"]',
                            'td[class*="location"]',
                            'td:nth-child(2)',
                        ]

                        for loc_sel in location_selectors:
                            try:
                                loc_elem = parent.find_element(By.CSS_SELECTOR, loc_sel)
                                location = loc_elem.text.strip()
                                if location:
                                    city, state, _ = self.parse_location(location)
                                    break
                            except:
                                continue
                    except Exception as e:
                        logger.debug(f"Could not extract location: {str(e)}")

                    # Build job data
                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': clean_title,
                        'description': '',
                        'location': location if location else 'India',
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': job_link,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    if FETCH_FULL_JOB_DETAILS and job_link:
                        try:
                            full_details = self._fetch_job_details(driver, job_link)
                            job_data.update(full_details)
                        except Exception as e:
                            logger.error(f"Error fetching full details for {clean_title}: {str(e)}")

                    jobs.append(job_data)
                    logger.debug(f"Successfully extracted job {idx + 1}: {clean_title}")

                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error finding job links: {str(e)}")

        return jobs

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
                    except:
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
                    except:
                        continue
            except:
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
                    except:
                        continue
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

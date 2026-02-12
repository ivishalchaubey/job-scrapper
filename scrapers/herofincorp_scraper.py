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

logger = setup_logger('herofincorp_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class HeroFinCorpScraper:
    def __init__(self):
        self.company_name = 'Hero FinCorp'
        self.url = 'https://www.herofincorp.com/careers'

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
            service = Service(CHROMEDRIVER_PATH)
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
        """Scrape jobs from Hero FinCorp careers page"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)

            # Wait 15s for SPA/custom page to fully render
            time.sleep(15)

            wait = WebDriverWait(driver, 10)

            # Try to click "Explore Jobs" link to navigate to the job listing section
            try:
                explore_link = driver.find_element(By.CSS_SELECTOR, 'a[href*="#explore_job_section"]')
                driver.execute_script("arguments[0].click();", explore_link)
                logger.info("Clicked 'Explore Jobs' link")
                time.sleep(3)
            except Exception:
                logger.info("No 'Explore Jobs' link found, continuing with page as-is")

            # Scroll down to load lazy content, then back up
            for scroll_i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Scrape the page
            page_jobs = self._scrape_page(driver, wait)
            jobs.extend(page_jobs)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page using Hero FinCorp-specific selectors"""
        jobs = []

        # Primary approach: find job cards inside div.result or div.jobslisting
        job_cards = []

        # Strategy 1: div.job-card-list elements (the actual job cards)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.job-card-list')))
            job_cards = driver.find_elements(By.CSS_SELECTOR, 'div.job-card-list')
            if job_cards:
                logger.info(f"Found {len(job_cards)} job cards using 'div.job-card-list'")
        except Exception:
            logger.info("div.job-card-list not found, trying alternatives")

        # Strategy 2: Look inside div.result for child divs
        if not job_cards:
            try:
                result_container = driver.find_element(By.CSS_SELECTOR, 'div.result')
                job_cards = result_container.find_elements(By.CSS_SELECTOR, 'div.job-card-list')
                if job_cards:
                    logger.info(f"Found {len(job_cards)} job cards inside div.result")
            except Exception:
                logger.info("div.result container not found")

        # Strategy 3: Look inside div.jobslisting
        if not job_cards:
            try:
                listing_container = driver.find_element(By.CSS_SELECTOR, 'div.jobslisting')
                job_cards = listing_container.find_elements(By.CSS_SELECTOR, 'div.job-card-list')
                if not job_cards:
                    # Try direct children
                    job_cards = listing_container.find_elements(By.XPATH, './*')
                if job_cards:
                    logger.info(f"Found {len(job_cards)} cards inside div.jobslisting")
            except Exception:
                logger.info("div.jobslisting container not found")

        # Strategy 4: section.job-listingsPart
        if not job_cards:
            try:
                section = driver.find_element(By.CSS_SELECTOR, 'section.job-listingsPart')
                job_cards = section.find_elements(By.CSS_SELECTOR, 'div.job-card-list')
                if not job_cards:
                    job_cards = section.find_elements(By.CSS_SELECTOR, 'div[class*="job"]')
                if job_cards:
                    logger.info(f"Found {len(job_cards)} cards inside section.job-listingsPart")
            except Exception:
                logger.info("section.job-listingsPart not found")

        # Extract job data from the found cards
        if job_cards:
            for idx, card in enumerate(job_cards):
                try:
                    card_text = card.text.strip()
                    if not card_text or len(card_text) < 5:
                        continue

                    job_title = ""
                    job_link = ""

                    # Title is in h4 inside div.details
                    try:
                        details_div = card.find_element(By.CSS_SELECTOR, 'div.details')
                        title_elem = details_div.find_element(By.TAG_NAME, 'h4')
                        job_title = title_elem.text.strip()
                    except Exception:
                        pass

                    # Fallback: any h4 in the card
                    if not job_title:
                        try:
                            title_elem = card.find_element(By.TAG_NAME, 'h4')
                            job_title = title_elem.text.strip()
                        except Exception:
                            pass

                    # Fallback: any h3 in the card
                    if not job_title:
                        try:
                            title_elem = card.find_element(By.TAG_NAME, 'h3')
                            job_title = title_elem.text.strip()
                        except Exception:
                            pass

                    # Fallback: first line of text
                    if not job_title:
                        job_title = card_text.split('\n')[0].strip()

                    if not job_title or len(job_title) < 3:
                        continue

                    # Try to get a link from the card
                    try:
                        link_elem = card.find_element(By.TAG_NAME, 'a')
                        job_link = link_elem.get_attribute('href') or ''
                    except Exception:
                        pass

                    # Extract location from position-details or job-details
                    location = ""
                    city = ""
                    state = ""

                    # Try ul.position-details li elements
                    try:
                        detail_items = card.find_elements(By.CSS_SELECTOR, 'ul.position-details li')
                        for item in detail_items:
                            item_text = item.text.strip()
                            if any(loc in item_text for loc in ['Delhi', 'Mumbai', 'Bangalore', 'Bengaluru', 'Gurgaon', 'Gurugram', 'Noida', 'Pune', 'Chennai', 'Hyderabad', 'India']):
                                location = item_text
                                city, state, _ = self.parse_location(location)
                                break
                    except Exception:
                        pass

                    # Fallback: scan all lines for location
                    if not location:
                        lines = card_text.split('\n')
                        for line in lines:
                            line_s = line.strip()
                            if any(loc in line_s for loc in ['Delhi', 'Mumbai', 'Bangalore', 'Bengaluru', 'Gurgaon', 'Gurugram', 'Noida', 'Pune', 'Chennai', 'Hyderabad', 'India']):
                                location = line_s
                                city, state, _ = self.parse_location(location)
                                break

                    # Extract department/details from div.job-details
                    department = ""
                    description = ""
                    try:
                        job_details_div = card.find_element(By.CSS_SELECTOR, 'div.job-details')
                        description = job_details_div.text.strip()[:500]
                    except Exception:
                        pass

                    # Extract from job-profiles-box if available
                    try:
                        profiles_box = card.find_element(By.CSS_SELECTOR, 'div.job-profiles-box')
                        if not description:
                            description = profiles_box.text.strip()[:500]
                    except Exception:
                        pass

                    job_id = f"herofincorp_{idx}"
                    if job_link:
                        job_id = job_link.split('/')[-1].split('?')[0] or job_id

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': job_title,
                        'description': description,
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': '',
                        'department': department,
                        'apply_url': job_link if job_link else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    if FETCH_FULL_JOB_DETAILS and job_link:
                        full_details = self._fetch_job_details(driver, job_link)
                        job_data.update(full_details)

                    jobs.append(job_data)
                    logger.info(f"Extracted: {job_title} | {location}")

                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        # JavaScript fallback: extract all visible job-like content from the page
        if not jobs:
            logger.info("Trying JavaScript DOM extraction fallback")
            try:
                js_jobs = driver.execute_script("""
                    var results = [];
                    // Try job-card-list elements
                    var cards = document.querySelectorAll('div.job-card-list');
                    if (cards.length === 0) {
                        // Try inside div.result
                        var resultDiv = document.querySelector('div.result');
                        if (resultDiv) {
                            cards = resultDiv.children;
                        }
                    }
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var text = (card.innerText || '').trim();
                        if (text.length < 5) continue;

                        var title = '';
                        // Try h4 inside div.details
                        var detailsDiv = card.querySelector('div.details');
                        if (detailsDiv) {
                            var h4 = detailsDiv.querySelector('h4');
                            if (h4) title = h4.innerText.trim();
                        }
                        if (!title) {
                            var h4 = card.querySelector('h4');
                            if (h4) title = h4.innerText.trim();
                        }
                        if (!title) {
                            title = text.split('\\n')[0].trim();
                        }
                        if (title.length < 3) continue;

                        var link = '';
                        var aTag = card.querySelector('a[href]');
                        if (aTag) link = aTag.href;

                        results.push({title: title, url: link, text: text});
                    }
                    return results;
                """)
                if js_jobs:
                    logger.info(f"JS fallback found {len(js_jobs)} job entries")
                    seen_titles = set()
                    for idx, jdata in enumerate(js_jobs):
                        title = jdata.get('title', '').strip()
                        url = jdata.get('url', '').strip()
                        full_text = jdata.get('text', '')
                        if not title or title in seen_titles:
                            continue
                        seen_titles.add(title)

                        location = ""
                        for line in full_text.split('\n'):
                            line_s = line.strip()
                            if any(loc in line_s for loc in ['Delhi', 'Mumbai', 'Bangalore', 'Bengaluru', 'Gurgaon', 'Gurugram', 'Noida', 'Pune', 'Chennai', 'Hyderabad', 'India']):
                                location = line_s
                                break

                        city, state, _ = self.parse_location(location)
                        job_id = f"herofincorp_{idx}"
                        if url:
                            job_id = url.split('/')[-1].split('?')[0] or job_id

                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
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
                        })
                    logger.info(f"JS fallback extracted {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"JS fallback error: {str(e)}")

        # Final fallback: generic text extraction from main.careerMain
        if not jobs:
            logger.info("Trying main.careerMain text extraction fallback")
            try:
                js_jobs = driver.execute_script("""
                    var results = [];
                    var main = document.querySelector('main.careerMain');
                    if (!main) main = document.querySelector('body');
                    var allH4 = main.querySelectorAll('h4');
                    for (var i = 0; i < allH4.length; i++) {
                        var title = allH4[i].innerText.trim();
                        if (title.length >= 3 && title.length <= 150) {
                            var parent = allH4[i].closest('div.job-card-list') || allH4[i].parentElement;
                            var link = '';
                            var aTag = parent ? parent.querySelector('a[href]') : null;
                            if (aTag) link = aTag.href;
                            results.push({title: title, url: link});
                        }
                    }
                    return results;
                """)
                if js_jobs:
                    seen_titles = set()
                    for idx, jdata in enumerate(js_jobs):
                        title = jdata.get('title', '').strip()
                        url = jdata.get('url', '').strip()
                        if not title or title in seen_titles:
                            continue
                        # Skip generic nav/header text
                        skip_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'menu', 'careers', 'hero fincorp']
                        if any(w in title.lower() for w in skip_words):
                            continue
                        seen_titles.add(title)
                        job_id = f"herofincorp_h4_{idx}"
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
                            'apply_url': url if url else self.url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })
                    logger.info(f"H4 fallback extracted {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"H4 fallback error: {str(e)}")

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

            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div.job-details'),
                    (By.CSS_SELECTOR, 'div.job-profiles-box'),
                    (By.CSS_SELECTOR, 'div.job-description'),
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                ]

                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        details['description'] = desc_elem.text.strip()[:2000]
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

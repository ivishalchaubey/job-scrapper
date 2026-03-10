from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import html
import json
import re
import time

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, MAX_PAGES_TO_SCRAPE, FETCH_FULL_JOB_DETAILS
from scrapers.csv_url_resolver import get_company_url

logger = setup_logger('accenture_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class AccentureScraper:
    def __init__(self):
        self.company_name = "Accenture"
        default_url = "https://www.accenture.com/in-en/careers/jobsearch?ct=Ahmedabad%7CBengaluru%7CBhubaneswar%7CChennai%7CCoimbatore%7CGandhinagar%7CGurugram%7CHyderabad%7CIndore%7CJaipur%7CKochi%7CKolkata%7CMumbai%7CNagpur%7CNavi%20Mumbai%7CNew%20Delhi%7CNoida%7CPune%7CThiruvananthapuram"
        self.url = get_company_url(self.company_name, default_url)
    
    def setup_driver(self):
        """Set up Chrome driver with options"""
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            # Install and get the correct chromedriver path
            driver_path = CHROMEDRIVER_PATH
            logger.info(f"ChromeDriver installed at: {driver_path}")
            
            # Fix for macOS ARM - ensure we use the actual chromedriver binary
            if 'chromedriver-mac-arm64' in driver_path and not driver_path.endswith('chromedriver'):
                import os
                driver_dir = os.path.dirname(driver_path)
                actual_driver = os.path.join(driver_dir, 'chromedriver')
                if os.path.exists(actual_driver):
                    driver_path = actual_driver
                    logger.info(f"Using corrected path: {driver_path}")
            
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            # Fallback: try without service specification
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
            return driver
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _normalize_text(self, value):
        """Normalize escaped unicode fragments like '\\u002D' and HTML entities."""
        if not value:
            return ''
        text = html.unescape(str(value)).strip()
        text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Accenture careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Smart wait for job cards instead of blind sleep
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.rad-filters-vertical__job-card'))
                )
                logger.info("Job cards loaded")
            except:
                logger.warning("Timeout waiting for job cards, using fallback wait")
                time.sleep(5)
            
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                # Scrape current page
                page_jobs = self._scrape_page(driver)
                jobs.extend(page_jobs)
                
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")
                
                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    # No extra sleep — _go_to_next_page already handles waiting
                
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
            
            # Scroll to pagination area
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            # Capture current state for change detection
            old_first = driver.execute_script("""
                var card = document.querySelector('div.rad-filters-vertical__job-card');
                return card ? card.innerText.substring(0, 50) : '';
            """)

            # Try to find and click next page button
            next_page_selectors = [
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'button[aria-label="Go to page {next_page_num}"]'),
                (By.XPATH, '//button[@aria-label="Go to next page"]'),
                (By.XPATH, '//button[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'button.pagination-next'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Clicked next page button")

                    # Poll for content change
                    for _ in range(20):
                        time.sleep(0.2)
                        new_first = driver.execute_script("""
                            var card = document.querySelector('div.rad-filters-vertical__job-card');
                            return card ? card.innerText.substring(0, 50) : '';
                        """)
                        if new_first and new_first != old_first:
                            break
                    time.sleep(0.5)
                    return True
                except:
                    continue
            
            logger.warning("Could not find next page button")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver):
        """Scrape jobs from current page"""
        jobs = []
        # Quick scroll for lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.3)
        
        # Look for job cards by the correct class
        job_cards = []
        
        try:
            # Find job cards using the actual class from Accenture's page
            job_cards = driver.find_elements(By.CSS_SELECTOR, "div.rad-filters-vertical__job-card")
            if job_cards:
                logger.info(f"Found {len(job_cards)} job cards")
        except Exception as e:
            logger.error(f"Error finding job cards: {str(e)}")
        
        if not job_cards:
            logger.warning("No job cards found")
            return jobs
        
        # Process each job card
        for idx, card in enumerate(job_cards):
            try:
                # Extract job title from h3
                job_title = ""
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, "h3.rad-filters-vertical__job-card-title")
                    job_title = title_elem.text.strip()
                except:
                    logger.debug(f"Could not extract title for card {idx}")
                    continue
                
                if not job_title or len(job_title) < 3:
                    logger.debug(f"Skipping card {idx}: Title too short")
                    continue
                
                # Extract job link
                job_link = ""
                job_number = ""
                try:
                    link_elem = card.find_element(By.CSS_SELECTOR, 'a[href*="jobdetails"]')
                    job_link = link_elem.get_attribute('href')
                    
                    # Extract job ID from URL
                    if 'id=' in job_link:
                        job_number = job_link.split('id=')[-1].split('&')[0]
                except:
                    logger.debug(f"Could not extract link for card {idx}")
                    # Try to get job number from the card content
                    try:
                        job_num_elem = card.find_element(By.CSS_SELECTOR, "span.rad-filters-vertical__job-card-content-job-number-dynamic-text")
                        job_number = job_num_elem.text.strip()
                    except:
                        pass

                if job_number.endswith('_en'):
                    job_number = job_number[:-3]

                if not job_number:
                    logger.warning(f"Skipping job without scraped job_id: {job_title}")
                    continue
                
                # Extract location
                location = ""
                city = ""
                state = ""
                try:
                    loc_elem = card.find_element(By.CSS_SELECTOR, "span.rad-filters-vertical__job-card-details-location")
                    location = loc_elem.text.strip()
                    city, state, _ = self.parse_location(location)
                except:
                    pass
                
                # Extract employment type
                employment_type = ""
                try:
                    schedule_elem = card.find_element(By.CSS_SELECTOR, "span.rad-filters-vertical__job-card-details-schedule")
                    employment_type = schedule_elem.text.strip()
                except:
                    pass
                
                # Extract experience level
                experience_level = ""
                try:
                    exp_elem = card.find_element(By.CSS_SELECTOR, "span.rad-filters-vertical__job-card-details-type")
                    experience_level = exp_elem.text.strip()
                except:
                    pass
                
                # Generate external ID
                external_id = self.generate_external_id(job_number, self.company_name)
                
                # If no job link, construct one
                if not job_link:
                    job_link = self.url
                
                logger.info(f"Found job: '{job_title}' (ID: {job_number})")
                
                job_data = {
                    'external_id': external_id,
                    'job_id': job_number,
                    'company_name': self.company_name,
                    'title': job_title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': '',
                    'employment_type': employment_type,
                    'department': '',
                    'apply_url': job_link,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': experience_level,
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                
                # Open detail page and scrape full content directly.
                if job_link and job_link != self.url:
                    full_details = self._fetch_job_details(driver, job_link)
                    if full_details.get('job_id'):
                        job_data['job_id'] = full_details['job_id']
                        job_data['external_id'] = self.generate_external_id(full_details['job_id'], self.company_name)
                    job_data.update(full_details)
                
                jobs.append(job_data)
                logger.info(f"Successfully added job: {job_title}")
                
            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                continue
        
        return jobs
    
    def _fetch_job_details(self, driver, job_url):
        """Open job detail page and scrape full description/sections from DOM."""
        details = {}
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(job_url)

            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.rad-job-details__wrapper")))

            # Expand all collapsed sections to ensure full text is available.
            for _ in range(3):
                toggles = driver.find_elements(
                    By.CSS_SELECTOR,
                    "button.rad-accordion-atom__toggle[aria-expanded='false']",
                )
                if not toggles:
                    break
                for btn in toggles:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                        time.sleep(0.1)
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.1)
                    except Exception:
                        continue

            wrapper = driver.find_element(By.CSS_SELECTOR, "div.rad-job-details__wrapper")
            raw_job_id = self._normalize_text(wrapper.get_attribute("data-jobid") or "")
            if raw_job_id:
                details["job_id"] = raw_job_id.replace("_en", "")

            raw_location = self._normalize_text(wrapper.get_attribute("data-joblocation") or "")
            if raw_location:
                details["location"] = raw_location
                city, state, country = self.parse_location(raw_location)
                if city:
                    details["city"] = city
                if state:
                    details["state"] = state
                if country:
                    details["country"] = country

            emp_type = self._normalize_text(wrapper.get_attribute("data-employeetype") or "")
            if emp_type:
                details["employment_type"] = emp_type

            job_func = self._normalize_text(wrapper.get_attribute("data-jobfunction") or "")
            if job_func:
                details["job_function"] = job_func

            business_area = self._normalize_text(wrapper.get_attribute("data-businessarea") or "")
            if business_area:
                details["department"] = business_area

            years_exp = self._normalize_text(wrapper.get_attribute("data-jobyearsofexperience") or "")
            if years_exp:
                details["experience_level"] = years_exp

            # Build full description from DOM using textContent to include hidden accordion content.
            full_detail_text = driver.execute_script("""
                const wrapper = document.querySelector('div.rad-job-details__wrapper');
                if (!wrapper) return '';
                const sectionTexts = [];
                const sections = wrapper.querySelectorAll('div.rad-accordion-atom');
                sections.forEach((section) => {
                    const heading = (section.querySelector('h2.rad-accordion-atom__toggle-title') || {}).textContent || '';
                    const contentNode = section.querySelector('div.rad-accordion-atom__content');
                    const content = contentNode ? ((contentNode.innerText || contentNode.textContent || '')) : '';
                    const h = heading.trim();
                    const c = content.replace(/\\r/g, '').replace(/\\n{3,}/g, '\\n\\n').trim();
                    if (c) {
                        sectionTexts.push(h ? `${h}:\\n${c}` : c);
                    }
                });
                if (sectionTexts.length) return sectionTexts.join('\\n\\n');
                const fallback = (wrapper.textContent || '').replace(/\\s+/g, ' ').trim();
                return fallback;
            """)
            if full_detail_text:
                details["description"] = full_detail_text[:15000]

            # Pull structured metadata from JSON-LD scripts via DOM, avoiding regex truncation.
            payload = None
            jsonld_scripts = driver.execute_script("""
                return Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
                  .map((s) => s.textContent || '');
            """)
            if isinstance(jsonld_scripts, list):
                for raw in jsonld_scripts:
                    if not raw:
                        continue
                    try:
                        candidate = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(candidate, dict) and candidate.get("@type") == "JobPosting":
                        payload = candidate
                        break
                    if isinstance(candidate, list):
                        for item in candidate:
                            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                                payload = item
                                break
                        if payload:
                            break
            if payload:
                date_posted = str(payload.get("datePosted", "")).strip()
                if date_posted:
                    details["posted_date"] = date_posted.split("T")[0]

                if not details.get("job_id"):
                    identifier = payload.get("identifier") or {}
                    if isinstance(identifier, dict):
                        id_val = str(identifier.get("value", "")).strip()
                        if id_val:
                            details["job_id"] = id_val

                # If accordion extraction fails, fallback to JSON-LD description.
                if not details.get("description"):
                    description_html = payload.get("description", "")
                    if description_html:
                        text = html.unescape(description_html)
                        text = re.sub(r"<br\\s*/?>", "\n", text, flags=re.IGNORECASE)
                        text = re.sub(r"<[^>]+>", " ", text)
                        text = re.sub(r"\\s+", " ", text).strip()
                        details["description"] = text[:15000]

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.debug(f"Error fetching job details from {job_url}: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass
        return details
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', ''

        raw = location_str.strip()
        if '/' in raw:
            first = raw.split('/')[0].strip()
            return first, '', ''

        parts = [p.strip() for p in raw.split(',') if p.strip()]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        country = parts[2] if len(parts) > 2 else ''
        return city, state, country

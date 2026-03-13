from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import re

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, MAX_PAGES_TO_SCRAPE
from scrapers.csv_url_resolver import get_company_url

logger = setup_logger('aws_scraper')

class AWSScraper:
    def __init__(self):
        self.company_name = "Amazon Web Services"
        default_url = "https://www.amazon.jobs/en/search?offset=0&result_limit=10&sort=relevant&business_category%5B%5D=amazon-web-services&distanceType=Mi&radius=24km&latitude=&longitude=&loc_group_id=&loc_query=India&base_query=&city=&country=IND&region=&county=&query_options=&"
        self.url = get_company_url(self.company_name, default_url)
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        # Use job ID + company name for stable external ID
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from AWS careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Smart wait for job content instead of blind sleep
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.job-tile')))
                logger.info("Job content loaded")
            except:
                logger.warning("Timeout waiting for job tiles, using fallback wait")
                time.sleep(3)
            
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                # Scrape current page
                page_jobs = self._scrape_page(driver, wait)
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
            # Method 1: Click on next page number
            next_page_num = current_page + 1
            next_page_selectors = [
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.5)

                    # Capture current state for change detection
                    old_first = driver.execute_script("""
                        var card = document.querySelector('div.job-tile');
                        return card ? card.innerText.substring(0, 50) : '';
                    """)

                    next_button.click()
                    logger.info(f"Clicked next page button using selector: {selector_value}")

                    # Poll for content change
                    for _ in range(20):
                        time.sleep(0.2)
                        new_first = driver.execute_script("""
                            var card = document.querySelector('div.job-tile');
                            return card ? card.innerText.substring(0, 50) : '';
                        """)
                        if new_first and new_first != old_first:
                            break
                    time.sleep(0.5)
                    return True
                except:
                    continue

            # Method 2: Modify URL with offset parameter
            current_url = driver.current_url
            if 'offset=' in current_url:
                import re
                new_offset = current_page * 10
                new_url = re.sub(r'offset=\d+', f'offset={new_offset}', current_url)
                driver.get(new_url)
                logger.info(f"Navigated to next page via URL modification")
            else:
                separator = '&' if '?' in current_url else '?'
                new_url = f"{current_url}{separator}offset={current_page * 10}"
                driver.get(new_url)
                logger.info(f"Navigated to next page via URL modification")

            # Smart wait after URL navigation
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.job-tile'))
                )
            except:
                time.sleep(3)
            return True
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        # Quick scroll for lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.3)
        
        # Try multiple selectors for job listings
        job_cards = []
        selectors = [
            (By.CSS_SELECTOR, 'div.job-tile'),
            (By.CSS_SELECTOR, 'div[class*="job"]'),
            (By.XPATH, '//div[contains(@class, "result")]'),
            (By.TAG_NAME, 'article'),
        ]
        
        for selector_type, selector_value in selectors:
            try:
                wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                job_cards = driver.find_elements(selector_type, selector_value)
                if job_cards and len(job_cards) > 0:
                    logger.info(f"Found {len(job_cards)} job cards using selector: {selector_value}")
                    break
            except:
                continue
        
        if not job_cards:
            # Fallback: get all job links
            logger.warning("Standard selectors failed, using fallback method")
            all_links = driver.find_elements(By.TAG_NAME, 'a')
            job_links = [link for link in all_links if '/jobs/' in link.get_attribute('href') or 'Job ID' in link.text]
            
            for idx, link in enumerate(job_links):
                try:
                    job_title = link.text.strip().split('\n')[0]
                    if not job_title or len(job_title) < 3:
                        continue
                        
                    job_url = link.get_attribute('href')
                    
                    # Extract Job ID from URL
                    job_id = f"aws_{idx}"
                    if '/jobs/' in job_url:
                        job_id = job_url.split('/jobs/')[-1].split('/')[0]
                    
                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'job_id': job_id,
                        'company_name': self.company_name,
                        'title': job_title,
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
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
                    
                    # Fetch full details from detail page
                    if job_url:
                        full_details = self._fetch_job_details(driver, job_url)
                        job_data.update(full_details)
                    
                    jobs.append(job_data)
                    
                except Exception as e:
                    logger.error(f"Error in fallback extraction {idx}: {str(e)}")
                    continue
        else:
            # Extract from job cards
            for idx, card in enumerate(job_cards):
                try:
                    card_text = card.text
                    if not card_text or len(card_text) < 10:
                        continue
                    
                    # Get job title and link
                    job_title = ""
                    job_link = ""
                    try:
                        title_link = card.find_element(By.TAG_NAME, 'a')
                        job_title = title_link.text.strip()
                        job_link = title_link.get_attribute('href')
                    except:
                        job_title = card_text.split('\n')[0].strip()
                    
                    if not job_title or len(job_title) < 3:
                        continue
                    
                    # Extract Job ID from URL or text
                    job_id = f"aws_{idx}"
                    if 'Job ID:' in card_text:
                        try:
                            job_id = card_text.split('Job ID:')[-1].strip().split()[0]
                        except:
                            pass
                    elif job_link and '/jobs/' in job_link:
                        job_id = job_link.split('/jobs/')[-1].split('/')[0]
                    
                    # Extract location
                    location = ""
                    city = ""
                    state = ""
                    lines = card_text.split('\n')
                    for line in lines:
                        if ', IND' in line or 'India' in line or ', IN' in line:
                            location = line.split('|')[0].strip()
                            city, state, _ = self.parse_location(location)
                            break
                    
                    # Extract posted date
                    posted_date = ""
                    for line in lines:
                        if 'Posted' in line or 'Updated' in line:
                            posted_date = line.replace('Posted', '').replace('Updated', '').strip()
                            break
                    
                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'job_id': job_id,
                        'company_name': self.company_name,
                        'title': job_title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': job_link if job_link else self.url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    
                    # Fetch full details from detail page
                    if job_link:
                        full_details = self._fetch_job_details(driver, job_link)
                        job_data.update(full_details)
                    
                    jobs.append(job_data)
                    
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue
        
        return jobs
    
    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}
        
        try:
            # Open job in new tab to avoid losing search results page
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
            driver.get(job_url)
            time.sleep(3)
            
            # Extract full description sections from the detail body.
            try:
                section_blocks = driver.find_elements(By.CSS_SELECTOR, "#job-detail-body .content .section")
                section_texts = []
                for block in section_blocks:
                    heading = ''
                    body = ''
                    try:
                        heading = block.find_element(By.TAG_NAME, 'h2').text.strip()
                    except Exception:
                        pass
                    try:
                        body = block.text.strip()
                        if heading and body.startswith(heading):
                            body = body[len(heading):].strip()
                    except Exception:
                        body = ''
                    if body:
                        if heading:
                            section_texts.append(f"{heading}:\n{body}")
                        else:
                            section_texts.append(body)
                if section_texts:
                    details['description'] = '\n\n'.join(section_texts)[:15000]
            except Exception:
                pass
            
            # Extract department/job category
            try:
                dept_elem = driver.find_element(By.CSS_SELECTOR, 'a[href*="/jobs/category/"]')
                details['department'] = dept_elem.text.strip()
            except:
                try:
                    dept_elem = driver.find_element(By.CSS_SELECTOR, 'a[href*="/job_categories/"]')
                    details['department'] = dept_elem.text.strip()
                except:
                    try:
                        dept_elem = driver.find_element(By.XPATH, "//a[contains(@href, 'category')]")
                        details['department'] = dept_elem.text.strip()
                    except:
                        try:
                            dept_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'Job details')]/following-sibling::*//a")
                            details['department'] = dept_elem.text.strip()
                        except:
                            pass
            
            # Extract precise location from job details
            try:
                location_elem = driver.find_element(By.CSS_SELECTOR, "#job-detail-body .association.location-icon li")
                location_text = location_elem.text.strip()
                if location_text:
                    details['location'] = location_text
                    city, state, country = self.parse_location(location_text)
                    details['city'] = city
                    details['state'] = state
                    details['country'] = country
            except Exception:
                pass
            
            # Extract job type (Full Time, etc.)
            try:
                job_type_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'Full Time') or contains(text(), 'Part Time')]")
                details['employment_type'] = job_type_elem.text.strip()
            except:
                pass
            
            # Close tab and return to search results
            driver.close()
            driver.switch_to.window(original_window)
            
        except Exception as e:
            logger.error(f"Error fetching job details from {job_url}: {str(e)}")
            # Make sure we return to original window
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
            return '', '', ''

        cleaned = location_str.strip().replace('Location:', '').strip()
        if '|' in cleaned:
            cleaned = cleaned.split('|')[0].strip()

        parts = [p.strip() for p in cleaned.split(',') if p.strip()]
        city = ''
        state = ''
        country = ''

        if len(parts) == 3 and parts[0].upper() in {'IND', 'IN'}:
            country = 'India'
            state = parts[1]
            city = parts[2]
        elif len(parts) >= 3:
            city = parts[0]
            state = parts[1]
            country = parts[2]
        elif len(parts) == 2:
            city = parts[0]
            state = parts[1]
        elif len(parts) == 1:
            city = parts[0]

        if not country:
            upper_cleaned = cleaned.upper()
            if re.search(r'\b(IND|IN)\b', upper_cleaned) or 'INDIA' in upper_cleaned:
                country = 'India'

        return city, state, country

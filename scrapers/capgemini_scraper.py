from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import hashlib
from datetime import datetime
import re

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('capgemini_scraper')

class CapgeminiScraper:
    def __init__(self):
        self.company_name = "Capgemini"
        self.base_url = "https://www.capgemini.com"
        self.url = "https://www.capgemini.com/in-en/careers/join-capgemini/job-search/?page=1&size=11&country_code=in-en"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Capgemini India search with pagination support."""
        all_jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR,
                'ul.JobList-module__job-list___pVEKw li[class*="JobRow-module__job-card-wrapper"]'
            )))

            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                # Scrape current page
                page_jobs = self._scrape_page(driver, wait)
                all_jobs.extend(page_jobs)
                
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")
                
                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, wait):
                        logger.info("No more pages available")
                        break
                
                current_page += 1
            
            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")
            
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise
        
        finally:
            if driver:
                driver.quit()
        
        return all_jobs
    
    def _go_to_next_page(self, driver, wait):
        """Navigate to next page using the Next button in pagination."""
        try:
            first_card = driver.find_element(
                By.CSS_SELECTOR,
                'ul.JobList-module__job-list___pVEKw li[class*="JobRow-module__job-card-wrapper"]'
            )
            next_button = driver.find_element(By.CSS_SELECTOR, 'button[class*="Pagination-module__next"]')
            if not next_button.is_enabled() or next_button.get_attribute('disabled') is not None:
                return False

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
            clicked = False
            for _ in range(3):
                try:
                    next_button.click()
                    clicked = True
                    break
                except Exception:
                    # Try to move the viewport slightly and retry
                    driver.execute_script("window.scrollBy(0, -120);")
            if not clicked:
                # Fallback for overlapping elements intercepting click
                driver.execute_script("arguments[0].click();", next_button)

            WebDriverWait(driver, 15).until(EC.staleness_of(first_card))
            wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR,
                'ul.JobList-module__job-list___pVEKw li[class*="JobRow-module__job-card-wrapper"]'
            )))
            return True
        except Exception as e:
            logger.warning(f"Could not find or click next page button: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page using Capgemini-specific card selectors."""
        jobs = []
        job_cards = []
        try:
            wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR,
                'ul.JobList-module__job-list___pVEKw li[class*="JobRow-module__job-card-wrapper"]'
            )))
            job_cards = driver.find_elements(
                By.CSS_SELECTOR,
                'ul.JobList-module__job-list___pVEKw li[class*="JobRow-module__job-card-wrapper"]'
            )
        except Exception:
            job_cards = []

        if not job_cards:
            logger.warning("No job cards found")
            return jobs
        
        # Extract from job cards
        for idx, card in enumerate(job_cards):
            try:
                anchor = card.find_element(By.CSS_SELECTOR, 'a[class*="JobRow-module__job-card"]')
                job_link = anchor.get_attribute('href') or ''
                if job_link.startswith('/'):
                    job_link = f"{self.base_url}{job_link}"

                title_elem = anchor.find_element(By.CSS_SELECTOR, 'div[class*="JobRow-module__title"]')
                job_title = title_elem.text.strip()
                if not job_title:
                    continue

                # Extract Job ID from /in-en/jobs/{job_id}
                m = re.search(r'/jobs/([^/?]+)', job_link)
                job_id = m.group(1) if m else hashlib.md5(f"{job_title}_{idx}".encode()).hexdigest()[:12]

                location = ''
                city = ''
                state = ''
                location_elems = anchor.find_elements(By.CSS_SELECTOR, 'div[class*="JobRow-module__location"]')
                if location_elems:
                    location = location_elems[0].text.strip()
                    loc = self.parse_location(location)
                    city = loc.get('city', '')
                    state = loc.get('state', '')

                department = ''
                employment_type = ''
                experience_level = ''
                feature_items = anchor.find_elements(By.CSS_SELECTOR, 'ul[class*="JobRow-module__features"] li')
                for item in feature_items:
                    txt = item.text.strip()
                    cls = item.get_attribute('class') or ''
                    if 'professional-communities' in cls:
                        department = txt
                    elif 'contract-type' in cls:
                        if txt.lower() == 'permanent':
                            employment_type = 'Full Time'
                        elif 'fixed term' in txt.lower() or 'contract' in txt.lower():
                            employment_type = 'Contract'
                        else:
                            employment_type = txt
                    elif 'experience-level' in cls:
                        experience_level = txt
                
                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': job_title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': 'India',
                    'employment_type': employment_type,
                    'department': department,
                    'apply_url': job_link if job_link else self.url,
                    'posted_date': '',
                    'job_function': department,
                    'experience_level': experience_level,
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                
                # Fetch full details if enabled
                if FETCH_FULL_JOB_DETAILS and job_link:
                    full_details = self._fetch_job_details(driver, job_link)
                    job_data.update(full_details)
                
                jobs.append(job_data)
                
            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                continue
        
        return jobs
    
    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page."""
        details = {}
        
        try:
            # Open job in new tab to avoid losing search results page
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
            driver.get(job_url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'h1')))

            # Description from primary detail container
            try:
                desc_container = driver.find_element(
                    By.CSS_SELECTOR,
                    'div[class*="SingleJobDescription-module__description"]'
                )
                description = desc_container.text.strip()
                if description:
                    details['description'] = description[:5000]
            except Exception:
                pass

            # Apply URL on detail page
            try:
                apply_link = driver.find_element(By.CSS_SELECTOR, 'a[class*="Header-module__apply"]')
                href = apply_link.get_attribute('href') or ''
                if href:
                    details['apply_url'] = href
            except Exception:
                pass

            # Detail metadata in header features (experience/community/contract/ref)
            try:
                meta_items = driver.find_elements(By.CSS_SELECTOR, 'div[class*="Header-module__features"] li')
                for item in meta_items:
                    txt = item.text.strip()
                    cls = item.get_attribute('class') or ''
                    if 'experience_level' in cls and txt:
                        details['experience_level'] = txt
                    elif 'professional_communities' in cls and txt:
                        details['department'] = txt
                        details['job_function'] = txt
                    elif 'contract_type' in cls and txt:
                        lower_txt = txt.lower()
                        if lower_txt == 'permanent':
                            details['employment_type'] = 'Full Time'
                        elif 'fixed term' in lower_txt or 'contract' in lower_txt:
                            details['employment_type'] = 'Contract'
                        else:
                            details['employment_type'] = txt
                    elif 'ref' in cls:
                        m = re.search(r'ID\s+(.+)', txt)
                        if m:
                            ref_job_id = m.group(1).strip()
                            details['external_id'] = self.generate_external_id(ref_job_id, self.company_name)
            except Exception:
                pass

            # Location can be more complete on detail page
            try:
                loc_elem = driver.find_element(By.CSS_SELECTOR, 'p[class*="Header-module__job-location"]')
                loc_str = loc_elem.text.strip()
                if loc_str:
                    loc = self.parse_location(loc_str)
                    details['location'] = loc_str
                    details['city'] = loc.get('city', '')
                    details['state'] = loc.get('state', '')
                    details['country'] = loc.get('country', 'India')
            except Exception:
                pass
            
            # Close tab and return to search results
            driver.close()
            driver.switch_to.window(original_window)
            
        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            # Make sure we return to original window
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass
        
        return details
    
    def parse_location(self, location_str):
        """Parse location string into city/state/country dict."""
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        
        parts = [p.strip() for p in location_str.split(',')]
        if parts:
            result['city'] = parts[0]
        if len(parts) >= 2:
            result['state'] = parts[1]
        if any('india' in p.lower() for p in parts):
            result['country'] = 'India'
        elif len(parts) >= 3:
            result['country'] = parts[-1]
        
        return result

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('reckitt_scraper')

class ReckittScraper:
    def __init__(self):
        self.company_name = "Reckitt"
        self.url = "https://careers.reckitt.com/search/?createNewAlert=false&q=&locationsearch=India&optionsFacetsDD_facility=&optionsFacetsDD_country="
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Reckitt careers page with pagination support"""
        jobs = []
        driver = None
        seen_external_ids = set()
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for search table
            WebDriverWait(driver, SCRAPE_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'table#searchresults tbody tr.data-row'))
            )
            time.sleep(1)
            
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                # Scrape current page
                page_jobs = self._scrape_page(driver, seen_external_ids)
                jobs.extend(page_jobs)
                
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")
                
                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(1)
                
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
            old_first = driver.find_element(By.CSS_SELECTOR, 'table#searchresults tbody tr.data-row td.colTitle a.jobTitle-link')

            next_page_selectors = [
                (By.XPATH, f'//div[contains(@class, "pagination-bottom")]//a[@title="Page {next_page_num}"]'),
                (By.XPATH, f'//div[contains(@class, "pagination-top")]//a[@title="Page {next_page_num}"]'),
                (By.XPATH, f'//a[contains(@href, "startrow") and normalize-space(text())="{next_page_num}"]'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", next_button)
                    WebDriverWait(driver, 12).until(EC.staleness_of(old_first))
                    WebDriverWait(driver, 12).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'table#searchresults tbody tr.data-row'))
                    )
                    logger.info(f"Clicked next page button")
                    return True
                except:
                    continue
            
            logger.warning("Could not find next page button")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, seen_external_ids):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(1)

        rows = driver.find_elements(By.CSS_SELECTOR, 'table#searchresults tbody tr.data-row')
        logger.info(f"Found {len(rows)} Reckitt rows")

        for idx, row in enumerate(rows):
            try:
                title_elem = row.find_element(By.CSS_SELECTOR, 'td.colTitle a.jobTitle-link')
                job_title = title_elem.text.strip()
                job_link = urljoin(self.url, title_elem.get_attribute('href') or '')
                if not job_title:
                    continue

                location = ''
                job_function = ''
                posted_date = ''
                try:
                    location = row.find_element(By.CSS_SELECTOR, 'td.colLocation span.jobLocation').text.strip()
                except:
                    pass
                try:
                    job_function = row.find_element(By.CSS_SELECTOR, 'td.colFacility span.jobFacility').text.strip()
                except:
                    pass
                try:
                    raw_date = row.find_element(By.CSS_SELECTOR, 'td.colDate span.jobDate').text.strip()
                    posted_date = self._parse_list_date(raw_date)
                except:
                    pass

                if 'india' not in location.lower() and ', IN' not in location:
                    continue

                city, state, country = self.parse_location(location)
                job_id = self._extract_job_id_from_url(job_link) or f"reckitt_{idx}_{hashlib.md5(job_title.encode()).hexdigest()[:8]}"
                external_id = self.generate_external_id(job_id, self.company_name)
                if external_id in seen_external_ids:
                    continue

                job_data = {
                    'external_id': external_id,
                    'company_name': self.company_name,
                    'title': job_title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': country,
                    'employment_type': '',
                    'department': '',
                    'apply_url': job_link,
                    'posted_date': posted_date,
                    'job_function': job_function,
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                
                if FETCH_FULL_JOB_DETAILS and job_link:
                    full_details = self._fetch_job_details(driver, job_link)
                    for key, value in full_details.items():
                        if value:
                            job_data[key] = value

                if not job_data.get('job_function') and job_function:
                    job_data['job_function'] = job_function

                seen_external_ids.add(external_id)
                
                jobs.append(job_data)
                
            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                continue
        
        return jobs
    
    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {
            'description': '',
            'posted_date': '',
            'employment_type': '',
            'experience_level': '',
            'job_function': '',
            'salary_range': '',
            'remote_type': '',
            'department': '',
            'apply_url': job_url,
        }
        
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
            driver.get(job_url)
            WebDriverWait(driver, SCRAPE_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'span[itemprop="description"], span.jobdescription'))
            )
            time.sleep(1)

            try:
                desc_elem = driver.find_element(By.CSS_SELECTOR, 'span[itemprop="description"]')
                details['description'] = desc_elem.text.strip()[:7000]
            except Exception:
                try:
                    desc_elem = driver.find_element(By.CSS_SELECTOR, 'span.jobdescription')
                    details['description'] = desc_elem.text.strip()[:7000]
                except Exception:
                    pass

            if details.get('description'):
                details['experience_level'] = self._extract_experience(details['description'])

            # Keep apply_url as the job detail URL from the search table.
            # Do not replace it with talentcommunity/apply links.
            
            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass
        
        return details

    def _extract_job_id_from_url(self, url):
        match = re.search(r'/([0-9]{8,})/?$', url or '')
        return match.group(1) if match else ''

    def _parse_list_date(self, date_str):
        """Parse Reckitt list date format: 14 Mar 2026 -> YYYY-MM-DD"""
        try:
            return datetime.strptime(date_str.strip(), '%d %b %Y').strftime('%Y-%m-%d')
        except Exception:
            return ''

    def _extract_experience(self, text):
        """Extract experience from description text"""
        if not text:
            return ''

        match = re.search(r'(\d+)\s*(?:to|-|–)\s*(\d+)\s*years?', text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}-{match.group(2)} years"

        match = re.search(r'min(?:imum)?\s+of\s+(\d+)\s*years?', text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}+ years"

        match = re.search(r'(\d+)\+\s*years?', text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}+ years"

        match = re.search(r'(\d+)\s*years?', text, re.IGNORECASE)
        if match:
            return f"{match.group(1)} years"

        return ''
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'
        
        parts = [p.strip() for p in location_str.split(',') if p.strip()]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        if state.upper() in {'IN', 'N/A'}:
            state = ''
        
        return city, state, 'India'

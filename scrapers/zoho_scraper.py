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
from urllib.parse import urljoin

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('zoho_scraper')

class ZohoScraper:
    def __init__(self):
        self.company_name = "Zoho Corporation"
        self.url = "https://www.zoho.com/careers/#jobs"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Zoho careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load
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
                    time.sleep(4)  # Wait for next page to load
                
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
            time.sleep(1)
            
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
        """Scrape jobs from the current page"""
        jobs = []
        time.sleep(3)  # Wait for page content to load

        # Look for job cards
        job_cards = []
        selectors = [
            (By.CSS_SELECTOR, 'ul.rec-job-info'),
        ]

        for selector_type, selector_value in selectors:
            try:
                job_cards = driver.find_elements(selector_type, selector_value)
                if job_cards and len(job_cards) > 0:
                    logger.info(f"Found {len(job_cards)} job cards using selector: {selector_value}")
                    break
            except:
                continue

        if not job_cards:
            logger.warning("No job cards found")
            return jobs

        # Process each job card
        for idx, card in enumerate(job_cards):
            try:
                # Extract job title and link
                job_title = ""
                job_link = ""
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, 'li.rec-job-title a')
                    job_title = title_elem.text.strip()
                    raw_link = title_elem.get_attribute('href')
                    job_link = urljoin(self.url, raw_link) if raw_link else ""
                except Exception as e:
                    logger.warning(f"Error extracting title or link: {str(e)}")
                    continue

                if not job_title or len(job_title) < 3:
                    continue

                # Extract brief description
                brief_description = ""
                try:
                    desc_elem = card.find_element(By.CSS_SELECTOR, 'li.zrsite_Job_Description span')
                    brief_description = desc_elem.text.strip()
                except:
                    pass

                # Extract employment type
                employment_type = ""
                try:
                    type_elem = card.find_element(By.CSS_SELECTOR, 'div.typescontainer span.jbtype')
                    employment_type = type_elem.text.strip()
                except:
                    pass

                # Generate job ID
                job_id = f"zoho_{idx}"
                if job_link:
                    try:
                        job_id = job_link.split('job_id=')[-1].split('&')[0]
                    except:
                        pass

                # Extract location (if available)
                location = ""
                city = ""
                state = ""
                try:
                    location_elem = card.find_element(By.CSS_SELECTOR, 'li.zrsite_City span')
                    location = location_elem.text.strip()
                    city, state, _ = self.parse_location(location)
                except:
                    pass

                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': job_title,
                    'description': brief_description,
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': 'India',
                    'employment_type': employment_type,
                    'department': '',
                    'apply_url': job_link if job_link else self.url,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }

                # Zoho listing page provides truncated snippets, so always fetch detail page.
                if job_link:
                    full_details = self._fetch_job_details(driver, job_link)
                    if full_details:
                        job_data.update(full_details)

                    # Ensure full detail text replaces the truncated listing snippet.
                    if full_details.get('description'):
                        job_data['description'] = full_details['description']

                jobs.append(job_data)

            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                continue

        return jobs

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}

        try:
            # Open job in new tab
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)

            # Wait for the job description to load fully
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div#jobdescription_data span#spandesc'))
            )

            # Extract full description
            try:
                desc_elem = driver.find_element(By.CSS_SELECTOR, 'div#jobdescription_data span#spandesc')
                if desc_elem:
                    # Use innerText from details page body so line breaks from lists are preserved.
                    full_text = driver.execute_script("return arguments[0].innerText;", desc_elem) or ""
                    details['description'] = full_text.strip()
            except Exception as e:
                logger.warning(f"Error extracting job description: {str(e)}")

            # Fallback: if #spandesc is empty, read the full description container.
            if not details.get('description'):
                try:
                    desc_block = driver.find_element(By.CSS_SELECTOR, 'div#jobdescription_data')
                    block_text = driver.execute_script("return arguments[0].innerText;", desc_block) or ""
                    if block_text.strip():
                        details['description'] = block_text.strip()
                except Exception:
                    pass

            # Extract additional fields (e.g., location, employment type)
            try:
                info_selectors = {
                    'location': (By.CSS_SELECTOR, 'em#data_city'),
                    'country': (By.CSS_SELECTOR, 'em#data_country'),
                }

                for field, (selector_type, selector_value) in info_selectors.items():
                    try:
                        elem = driver.find_element(selector_type, selector_value)
                        if elem and elem.text.strip():
                            details[field] = elem.text.strip()
                    except:
                        continue
            except Exception as e:
                logger.warning(f"Error extracting additional job details: {str(e)}")

            # Parse city/state if region text was captured from details page.
            if details.get('location'):
                city, state, _ = self.parse_location(details['location'])
                details['city'] = city
                details['state'] = state

            if details.get('description'):
                logger.info(f"Fetched full description length={len(details['description'])} for {job_url}")

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
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'
        
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        
        return city, state, 'India'

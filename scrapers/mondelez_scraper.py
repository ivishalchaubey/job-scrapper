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

logger = setup_logger('mondelez_scraper')

class MondelezScraper:
    def __init__(self):
        self.company_name = "Mondelez International"
        self.url = "https://www.mondelezinternational.com/careers/jobs/?term&countrycode=IN"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Mondelez careers page with pagination support"""
        jobs = []
        driver = None
        seen_external_ids = set()
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load
            time.sleep(10)

            # Scroll once to trigger lazy-loaded content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
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
                    time.sleep(2)
                
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
            old_marker = driver.find_element(By.CSS_SELECTOR, 'div.resultRenderContainer > div:nth-child(1) a')

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            
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
                    WebDriverWait(driver, 10).until(EC.staleness_of(old_marker))
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
        wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.resultRenderContainer')))
        time.sleep(1)

        job_cards = driver.find_elements(By.CSS_SELECTOR, 'div.resultRenderContainer > div')
        logger.info(f"Found {len(job_cards)} Mondelez job cards")

        for idx, card in enumerate(job_cards):
            try:
                card_text = card.text or ''
                if len(card_text.strip()) < 10:
                    continue

                job_title = ''
                job_link = ''
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, 'a[href*="/careers/jobs/job?"]')
                    job_title = title_elem.text.strip()
                    href = title_elem.get_attribute('href')
                    job_link = urljoin(self.url, href)
                except:
                    job_title = card_text.split('\n')[0].strip()

                if not job_title or len(job_title) < 3:
                    continue

                posted_date = ''
                req_id = ''
                location = ''
                for p in card.find_elements(By.TAG_NAME, 'p'):
                    line = p.text.strip()
                    if not line:
                        continue
                    parsed_date = self._parse_list_date(line)
                    if parsed_date:
                        posted_date = parsed_date
                    if '|' in line and 'R-' in line:
                        parts = [x.strip() for x in line.split('|')]
                        for part in parts:
                            if part.startswith('R-'):
                                req_id = part
                        if len(parts) > 1:
                            location = parts[1]

                if not location:
                    try:
                        loc_link = card.find_element(By.CSS_SELECTOR, 'p a[href*="locationid="]')
                        location = loc_link.text.strip()
                    except:
                        pass

                if not location or 'India' not in location:
                    continue

                city, state, country = self.parse_location(location)
                job_id = req_id if req_id else f"mondelez_{idx}_{hashlib.md5(job_title.encode()).hexdigest()[:8]}"
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
                    'apply_url': job_link if job_link else self.url,
                    'posted_date': posted_date,
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }

                if FETCH_FULL_JOB_DETAILS and job_link:
                    full_details = self._fetch_job_details(driver, job_link)
                    job_data.update(full_details)

                if not job_data.get('apply_url'):
                    job_data['apply_url'] = job_link
                if 'remote' in (job_data.get('location', '') or '').lower():
                    job_data['remote_type'] = 'Remote'

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
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.jobDetailLeftContentWrap'))
            )
            time.sleep(1)

            try:
                desc_elem = driver.find_element(By.CSS_SELECTOR, 'div.jobDetailLeftContentWrap > div[data-action-detail]')
                details['description'] = desc_elem.text.strip()[:6000]
            except Exception as e:
                logger.warning(f"Mondelez description not found: {e}")

            try:
                detail_rows = driver.find_elements(By.CSS_SELECTOR, 'div.jobDescWrap > div > div')
                for row in detail_rows:
                    ps = row.find_elements(By.TAG_NAME, 'p')
                    if not ps:
                        continue
                    label = ps[0].text.strip().lower()
                    value = ''
                    if len(ps) > 1:
                        value = ps[1].text.strip()
                    else:
                        value = row.text.replace(ps[0].text, '', 1).strip()

                    if label == 'title' and not value:
                        continue
                    if label == 'function' and value:
                        details['job_function'] = value
                    elif label == 'date' and value:
                        parsed = self._parse_detail_date(value)
                        if parsed:
                            details['posted_date'] = parsed
                    elif label == 'work schedule' and value:
                        details['employment_type'] = value
                    elif label == 'job type' and value:
                        details['department'] = value
                    elif label == 'location' and value:
                        details['location'] = value
            except Exception as e:
                logger.warning(f"Mondelez job details map parse failed: {e}")

            try:
                apply_btn = driver.find_element(By.CSS_SELECTOR, 'a.event_external_link[aria-label="Apply Now"]')
                apply_href = apply_btn.get_attribute('href') or ''
                if apply_href:
                    details['apply_url'] = apply_href
            except Exception:
                pass

            if details.get('description'):
                details['experience_level'] = self._extract_experience(details['description'])

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

    def _parse_list_date(self, date_str):
        """Parse list page date format: Friday, March 13, 2026 -> YYYY-MM-DD"""
        try:
            return datetime.strptime(date_str.strip(), '%A, %B %d, %Y').strftime('%Y-%m-%d')
        except Exception:
            return ''

    def _parse_detail_date(self, date_str):
        """Parse detail page date format: 3/13/2026 -> YYYY-MM-DD"""
        try:
            month, day, year = [x.strip() for x in date_str.split('/')]
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except Exception:
            return ''

    def _extract_experience(self, text):
        """Extract experience range/single value from description"""
        if not text:
            return ''

        match = re.search(r'(\d+)\s*(?:to|-|–)\s*(\d+)\s*years?', text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}-{match.group(2)} years"

        match = re.search(r'(\d+)\+?\s*years?', text, re.IGNORECASE)
        if match:
            return f"{match.group(1)} years"

        return ''
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        if 'remote' in location_str.lower():
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        if city.lower() == 'india':
            city = ''

        state = ''
        if len(parts) > 2:
            state = parts[1]
        elif len(parts) > 1 and parts[1].lower() != 'india':
            state = parts[1]

        return city, state, 'India'

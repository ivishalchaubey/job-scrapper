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

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('cognizant_scraper')

class CognizantScraper:
    def __init__(self):
        self.company_name = "Cognizant"
        self.url = "https://careers.cognizant.com/india-en/jobs/?keyword=&location=India&lat=&lng=&cname=India&ccode=IN&origin=global"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Cognizant careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(5)  # Wait for dynamic content
            
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
                    time.sleep(3)  # Wait for next page to load
                
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
            next_page_selectors = [
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
                (By.XPATH, '//button[@aria-label="Go to next page"]'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    next_button.click()
                    logger.info(f"Clicked next page button using selector: {selector_value}")
                    return True
                except:
                    continue
            
            logger.warning("Could not find next page button")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        seen_links = set()
        time.sleep(2)  # Wait for page content
        
        # Try multiple selectors for job listings
        job_cards = []
        selectors = [
            (By.CSS_SELECTOR, 'div.job-card'),
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
            logger.warning("No job cards found")
            return jobs
        
        # Extract from job cards
        for idx, card in enumerate(job_cards):
            try:
                card_text = card.text
                if not card_text or len(card_text) < 10:
                    continue
                
                # Get job title
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

                # Skip non-job widgets and duplicates.
                title_l = job_title.lower()
                if 'be the first to know about new jobs' in title_l:
                    continue
                if 'join our talent community' in title_l:
                    continue
                if not job_link or '/india-en/jobs/' not in job_link or '/india-en/jobs/?' in job_link:
                    continue
                if job_link in seen_links:
                    continue
                seen_links.add(job_link)

                # Extract Job ID
                job_id = f"cognizant_{idx}"
                if job_link:
                    job_id = hashlib.md5(job_link.encode()).hexdigest()[:12]
                
                # Extract location
                location = ""
                city = ""
                state = ""
                lines = card_text.split('\n')
                for line in lines:
                    if any(city_name in line for city_name in ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai', 'Pune', 'Kolkata', 'India']):
                        location = line.strip()
                        city, state, _ = self.parse_location(location)
                        break
                
                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
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
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                
                # Cognizant list pages are incomplete; always enrich from detail page.
                if job_link:
                    base_location = job_data.get('location', '')
                    base_city = job_data.get('city', '')
                    base_state = job_data.get('state', '')

                    full_details = self._fetch_job_details(driver, job_link)
                    if full_details:
                        job_data.update(full_details)

                        # Keep richer listing location when detail location is less specific.
                        detail_location = full_details.get('location', '')
                        if base_location and (
                            not detail_location or base_location.count(',') > detail_location.count(',')
                        ):
                            job_data['location'] = base_location
                            job_data['city'] = base_city
                            job_data['state'] = base_state

                        if job_data.get('location'):
                            city, state, country = self.parse_location(job_data['location'])
                            job_data['city'] = city
                            job_data['state'] = state
                            job_data['country'] = country
                
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
            WebDriverWait(driver, SCRAPE_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'main#content, div#js-job-detail'))
            )
            
            # Extract full article content/description.
            try:
                content_elem = driver.find_element(By.CSS_SELECTOR, 'div#js-job-detail article.cms-content')
                desc_text = driver.execute_script("return arguments[0].innerText;", content_elem) or ''
                if desc_text.strip():
                    details['description'] = desc_text.strip()
            except Exception:
                pass

            # Title and stable job id from detail page attributes.
            try:
                job_container = driver.find_element(By.CSS_SELECTOR, 'div#js-job-detail')
                page_job_id = (job_container.get_attribute('data-id') or '').strip()
                if page_job_id:
                    details['external_id'] = self.generate_external_id(page_job_id, self.company_name)
            except Exception:
                pass

            # Apply URL from sidebar button.
            try:
                apply_elem = driver.find_element(By.CSS_SELECTOR, 'a#js-apply-external, a.js-apply-now')
                apply_href = (apply_elem.get_attribute('href') or '').strip()
                if apply_href:
                    details['apply_url'] = apply_href
            except Exception:
                pass

            # Hero metadata: date/location/category/work model.
            try:
                meta_items = driver.find_elements(By.CSS_SELECTOR, 'ul.job-meta li.job-meta-item')
                for li in meta_items:
                    li_text = (li.text or '').strip().lower()
                    strong_text = ''
                    try:
                        strong = li.find_element(By.TAG_NAME, 'strong')
                        strong_text = (strong.text or '').strip()
                    except Exception:
                        strong_text = (li.text or '').strip()

                    if not strong_text:
                        continue

                    if 'date published' in li_text:
                        details['posted_date'] = self._normalize_posted_date(strong_text)
                    elif 'location' in li_text:
                        details['location'] = self._normalize_location_text(strong_text)
                    elif 'job category' in li_text:
                        details['department'] = strong_text
                        details['job_function'] = strong_text
                    elif 'work model' in li_text:
                        details['remote_type'] = strong_text
            except Exception:
                pass

            # Extract experience from full text (e.g., "minimum of 7 years").
            if details.get('description'):
                exp = self._extract_experience_level(details['description'])
                if exp:
                    details['experience_level'] = exp
                logger.info(f"Fetched Cognizant full description length={len(details['description'])} for {job_url}")
            
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

    def _normalize_posted_date(self, posted_text):
        if not posted_text:
            return ''

        txt = posted_text.strip().replace('.', '')
        for fmt in ('%b %d %Y', '%B %d %Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(txt, fmt).strftime('%Y-%m-%d')
            except Exception:
                continue
        return posted_text.strip()

    def _normalize_location_text(self, loc_text):
        if not loc_text:
            return ''

        # Example: "Gandhi Nagar / COIMBATORE / India"
        parts = [p.strip() for p in loc_text.split('/') if p.strip()]
        if not parts:
            return loc_text.strip()
        return ', '.join(parts)

    def _extract_experience_level(self, text):
        if not text:
            return ''

        patterns = [
            r'(\b\d+\s*(?:-|to)\s*\d+\+?\s*years?\b)',
            r'(\b\d+\+?\s*years?\b)\s+(?:of\s+)?(?:relevant\s+)?experience',
            r'minimum\s+of\s+(\d+\+?\s*years?\b)',
            r'over\s+(\d+\+?\s*years?\b)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            value = (match.group(1) or '').strip()
            value = re.sub(r'\s+', ' ', value)
            if value:
                return value.replace(' to ', '-')

        return ''
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        # For multi-location strings, parse the first location block only.
        # Example: "Gandhi Nagar, Gujarat, India / COIMBATORE, Tamil Nadu, India"
        primary = location_str.split('/')[0].strip()
        parts = [p.strip() for p in primary.split(',') if p.strip()]

        if not parts:
            return '', '', 'India'

        # Format: City, State, India
        if len(parts) >= 3 and parts[2].lower() == 'india':
            return parts[0], parts[1], 'India'

        # Format: State, India
        if len(parts) == 2 and parts[1].lower() == 'india':
            return '', parts[0], 'India'

        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        if state.lower() == 'india':
            state = ''

        return city, state, 'India'

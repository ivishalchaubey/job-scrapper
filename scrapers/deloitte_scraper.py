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
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, MAX_PAGES_TO_SCRAPE
from scrapers.csv_url_resolver import get_company_url

logger = setup_logger('deloitte_scraper')

class DeloitteScraper:
    def __init__(self):
        self.company_name = "Deloitte"
        default_url = "https://usijobs.deloitte.com/en_US/careersusi"
        self.url = get_company_url(self.company_name, default_url)
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _extract_job_id(self, job_url):
        if not job_url:
            return ''

        patterns = [
            r'[?&](?:jobId|jobID|jobid|requisitionId|reqId|id)=([A-Za-z0-9_-]+)',
            r'/job/[^/]+/([A-Za-z0-9_-]+)(?:\?|$)',
            r'/([A-Za-z]{1,6}-\d{3,})',
            r'/(\d{6,})(?:\?|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, job_url)
            if match:
                return match.group(1).strip()

        slug = job_url.rstrip('/').split('/')[-1]
        if slug and slug.lower() not in {'job', 'jobs'}:
            slug = slug.split('?', 1)[0].strip()
            if slug:
                return slug
        return hashlib.md5(job_url.encode()).hexdigest()[:12]

    def _clean_text(self, value):
        if not value:
            return ''
        text = html.unescape(value)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<li[^>]*>', '\n- ', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'[ \t\r\f\v]+', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        return text.strip()[:15000]
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Deloitte careers page with pagination support"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            # Wait for page to load - Deloitte page has dynamic loading
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            
            # Handle potential cookie consent or privacy popups
            try:
                time.sleep(3)  # Wait for any popups to appear
                # Try to close cookie/privacy popups
                popup_close_selectors = [
                    'button[id*="accept"]',
                    'button[id*="cookie"]',
                    'button[class*="accept"]',
                    'button[aria-label*="Accept"]',
                    'button[aria-label*="Close"]',
                    'a[class*="close"]',
                ]
                for selector in popup_close_selectors:
                    try:
                        popup_btn = driver.find_element(By.CSS_SELECTOR, selector)
                        popup_btn.click()
                        logger.info(f"Closed popup using selector: {selector}")
                        time.sleep(1)
                        break
                    except:
                        continue
            except:
                pass
            
            # Wait for the search results section to load first
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'section.section--search-jobs')))
                logger.info("Search jobs section loaded")
            except:
                logger.warning("Could not find search section")
            
            # Wait for the job count indicator to appear (confirms page loaded)
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'span.jobListTotalRecords')))
                job_count_elem = driver.find_element(By.CSS_SELECTOR, 'span.jobListTotalRecords')
                total_jobs = job_count_elem.text
                logger.info(f"Job list page loaded successfully - Total jobs available: {total_jobs}")
            except:
                logger.warning("Could not find job count indicator, but continuing...")
            
            time.sleep(5)  # Additional wait for dynamic content to render
            
            # Scroll page to trigger any lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            
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
            
            # Deloitte uses specific aria-labels for pagination
            next_page_selectors = [
                (By.XPATH, f'//a[contains(@aria-label, "Go to Next Page")]'),
                (By.XPATH, f'//a[contains(@aria-label, "Go to Page Number {next_page_num}")]'),
                (By.XPATH, f'//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    # Scroll to element
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", next_button)
                    time.sleep(1)
                    # Try clicking with JavaScript if regular click fails
                    try:
                        next_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Clicked next page button using selector: {selector_value}")
                    time.sleep(2)  # Wait for page to load
                    return True
                except Exception as e:
                    logger.debug(f"Could not click with selector {selector_value}: {e}")
                    continue
            
            logger.warning("Could not find next page button")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(3)  # Wait for page content to load
        
        try:
            # Wait for job results to appear - Deloitte uses article--result class
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article.article--result')))
        except Exception as e:
            logger.warning(f"Timeout waiting for job listings: {e}")
        
        # Find all job listings using the correct Deloitte selector
        job_listings = []
        
        try:
            # Deloitte uses article.article--result for each job listing
            job_listings = driver.find_elements(By.CSS_SELECTOR, 'article.article--result')
            logger.info(f"Found {len(job_listings)} job listings")
        except Exception as e:
            logger.error(f"Error finding job listings: {e}")
            return jobs
        
        if not job_listings:
            logger.warning("No job listings found on page")
            logger.info(f"Page title: {driver.title}")
            logger.info(f"Current URL: {driver.current_url}")
            # Save page source for debugging
            try:
                with open('deloitte_no_jobs_debug.html', 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                logger.info("Saved debug page source to deloitte_no_jobs_debug.html")
            except Exception as debug_err:
                logger.error(f"Could not save debug page: {debug_err}")
            return jobs
        
        # Extract data from each job listing
        for idx, listing in enumerate(job_listings):
            try:
                # Find the job title and link
                job_title = ""
                job_url = ""
                
                try:
                    # Deloitte structure: h3.article__header__text__title > a
                    title_link = listing.find_element(By.CSS_SELECTOR, 'h3.article__header__text__title a')
                    job_title = title_link.text.strip()
                    job_url = title_link.get_attribute('href')
                except Exception as e:
                    logger.debug(f"Error finding title link for job {idx}: {e}")
                    continue
                
                if not job_title or not job_url:
                    logger.debug(f"Skipping listing {idx} - no title or URL found")
                    continue
                
                # Extract job ID from URL
                job_id = self._extract_job_id(job_url)
                
                # Extract location information from subtitle
                location = ""
                city = ""
                state = ""
                country = ""
                department = ""
                
                try:
                    # Deloitte listing subtitle often includes org, department, and location pieces.
                    subtitle_elem = listing.find_element(By.CSS_SELECTOR, 'div.article__header__text__subtitle')
                    subtitle_spans = subtitle_elem.find_elements(By.TAG_NAME, 'span')
                    
                    if subtitle_spans:
                        span_texts = [s.text.strip() for s in subtitle_spans if s.text and s.text.strip() and s.text.strip() != '|']
                        location_candidates = []
                        for text in span_texts:
                            lower = text.lower()
                            if (
                                ',' in text
                                or ' - ' in text
                                or lower.endswith(' india')
                                or ' united states' in lower
                                or ' usa' in lower
                                or ' uk' in lower
                                or 'canada' in lower
                                or 'australia' in lower
                                or 'germany' in lower
                                or 'singapore' in lower
                                or 'japan' in lower
                                or 'remote' in lower
                            ):
                                location_candidates.append(text)

                        if location_candidates:
                            location = location_candidates[-1]
                        elif len(span_texts) >= 3:
                            location = span_texts[-1]

                        for text in span_texts:
                            if text == location:
                                continue
                            lower = text.lower()
                            if 'deloitte' in lower or lower in {'|'}:
                                continue
                            department = text
                            break
                    
                    # Parse location if found
                    if location:
                        city, state, country = self.parse_location(location)
                    
                except Exception as e:
                    logger.debug(f"Error extracting location for job {idx}: {e}")
                
                # Extract additional metadata if available
                employment_type = ""
                
                try:
                    # Look for job metadata in the listing text
                    metadata_text = listing.text
                    if 'Full-time' in metadata_text or 'Full Time' in metadata_text:
                        employment_type = 'Full-time'
                    elif 'Part-time' in metadata_text or 'Part Time' in metadata_text:
                        employment_type = 'Part-time'
                    elif 'Contract' in metadata_text:
                        employment_type = 'Contract'
                except:
                    pass
                
                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'job_id': job_id,
                    'company_name': self.company_name,
                    'title': job_title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': country,
                    'employment_type': employment_type,
                    'department': department,
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
                logger.debug(f"Extracted job: {job_title} - {location}")
                
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
            
            # Extract description
            try:
                # Primary: Deloitte job details rich-text payload (full JD body).
                primary_selectors = [
                    (By.CSS_SELECTOR, 'article.article--details .article__view__item.view--row.no-label.view--rich-text span.field-value'),
                    (By.CSS_SELECTOR, 'article.article--details .article__view__item.view--rich-text span.field-value'),
                ]
                best_description = ''
                for selector_type, selector_value in primary_selectors:
                    try:
                        for elem in driver.find_elements(selector_type, selector_value):
                            html_or_text = elem.get_attribute('innerHTML') or elem.text or ''
                            cleaned = self._clean_text(html_or_text)
                            if len(cleaned) > len(best_description):
                                best_description = cleaned
                    except Exception:
                        continue

                if best_description:
                    details['description'] = best_description

                desc_selectors = [
                    (By.CSS_SELECTOR, 'article.article.article--job-detail div.article__content'),
                    (By.CSS_SELECTOR, 'section.section--article div.article__content'),
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, "//h2[contains(text(), 'Description')]/following-sibling::div"),
                    (By.CSS_SELECTOR, 'div.job-description'),
                ]
                
                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        if desc_elem:
                            candidate = self._clean_text(desc_elem.get_attribute('innerHTML') or desc_elem.text)
                            if len(candidate) > len(details.get('description', '')):
                                details['description'] = candidate
                    except:
                        continue
                if not details.get('description'):
                    page_source = driver.page_source
                    # Fallback 1: embedded JSON-style description payload in page source.
                    embedded = re.search(r'\"description\":\"(.*?)\"\\s*,\\s*\"title\"', page_source, flags=re.DOTALL)
                    if embedded:
                        raw = embedded.group(1)
                        try:
                            decoded = json.loads(f'\"{raw}\"')
                        except Exception:
                            decoded = raw
                        cleaned = self._clean_text(decoded)
                        if cleaned:
                            details['description'] = cleaned[:15000]

                if not details.get('description'):
                    # Fallback 2: use og:description when full payload extraction fails.
                    try:
                        og_desc = driver.find_element(By.CSS_SELECTOR, 'meta[property=\"og:description\"]').get_attribute('content')
                        if og_desc:
                            details['description'] = html.unescape(og_desc).strip()[:15000]
                    except Exception:
                        pass
            except:
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
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', ''

        cleaned = re.sub(r'\s+', ' ', location_str).strip()
        cleaned = cleaned.replace(' | ', ', ')
        parts = [p.strip() for p in cleaned.split(',') if p.strip()]

        if len(parts) == 1 and ' - ' in parts[0]:
            parts = [p.strip() for p in parts[0].split(' - ') if p.strip()]

        city = parts[0] if len(parts) >= 1 else ''
        state = ''
        country = ''
        if len(parts) == 2:
            # Keep only scraped facts: if second token looks like country, map to country.
            token = parts[1]
            if token.lower() in {
                'india', 'united states', 'usa', 'uk', 'united kingdom', 'canada',
                'australia', 'germany', 'japan', 'singapore'
            }:
                country = token
            else:
                state = token
        elif len(parts) >= 3:
            state = parts[1]
            country = parts[-1]

        return city, state, country

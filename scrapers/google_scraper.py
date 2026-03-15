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
import re

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('google_scraper')

class GoogleScraper:
    def __init__(self):
        self.company_name = "Google"
        self.url = "https://www.google.com/about/careers/applications/jobs/results?location=India"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Google careers page"""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(6)  # Give extra time for JavaScript to load
            
            current_page = 1
            
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                
                page_jobs = self._scrape_page(driver, wait)
                jobs.extend(page_jobs)
                
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")
                
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(3)
                
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
            # Scroll to bottom of page to ensure pagination button is loaded
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Google careers uses "Go to next page" link at the bottom
            next_page_selectors = [
                (By.LINK_TEXT, 'Go to next page'),
                (By.PARTIAL_LINK_TEXT, 'Go to next'),
                (By.XPATH, '//a[contains(text(), "next")]'),
                (By.XPATH, '//a[contains(@aria-label, "next") or contains(@aria-label, "Next")]'),
                (By.CSS_SELECTOR, 'a[aria-label*="next"], a[aria-label*="Next"]'),
                # Try pagination links by checking for page numbers
                (By.XPATH, f'//a[contains(text(), "{current_page + 1}")]'),
            ]
            
            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    # Make sure it's visible
                    if next_button.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                        time.sleep(1)
                        # Click using JavaScript to avoid click interception
                        driver.execute_script("arguments[0].click();", next_button)
                        logger.info(f"Clicked next page button successfully")
                        time.sleep(4)  # Wait for new page to load
                        
                        # Scroll back to top to see all jobs
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(1)
                        return True
                except Exception as e:
                    continue
            
            logger.warning("Could not find next page button - may be on last page")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs from current page"""
        jobs = []
        time.sleep(5)
        
        # Scroll down multiple times to load more jobs (lazy loading)
        logger.info("Scrolling to load more jobs...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scrolls = 5  # Scroll up to 5 times to load more jobs
        
        while scroll_attempts < max_scrolls:
            # Scroll down
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Wait for content to load
            
            # Check if new content loaded
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                # No new content, stop scrolling
                break
            
            last_height = new_height
            scroll_attempts += 1
            logger.info(f"Scrolled {scroll_attempts} times, loading more jobs...")
        
        # Scroll back to top to ensure all elements are in the DOM
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # Find all h3 elements - these contain job titles
        try:
            h3_elements = driver.find_elements(By.TAG_NAME, 'h3')
            logger.info(f"Total h3 elements found: {len(h3_elements)}")
            
            # Filter to only job titles (those that are long enough and not filter names)
            job_title_elements = []
            filter_keywords = ['Locations', 'Experience', 'Skills', 'Degree', 'Job types', 
                             'Organizations', 'Sort by', 'Search', 'Follow']
            
            for h3 in h3_elements:
                h3_text = h3.text.strip()
                # Job titles are usually longer and don't match filter keywords
                if h3_text and len(h3_text) > 10 and not any(keyword in h3_text for keyword in filter_keywords):
                    job_title_elements.append(h3)
            
            logger.info(f"Filtered to {len(job_title_elements)} potential job title elements")
            
            if not job_title_elements:
                logger.error("No job title elements found")
                return jobs
            
        except Exception as e:
            logger.error(f"Error finding h3 elements: {str(e)}")
            return jobs
        
        for idx, h3_elem in enumerate(job_title_elements):
            try:
                # Get job title from h3
                job_title = h3_elem.text.strip()
                
                if not job_title or len(job_title) < 3:
                    continue
                
                # Find the parent container for this job (go up to find the list item or card)
                parent = h3_elem
                job_link = ""
                location = ""
                city = ""
                state = ""
                
                try:
                    # Go up to find the job card container
                    for _ in range(6):  # Go up max 6 levels
                        parent = parent.find_element(By.XPATH, '..')
                        parent_tag = parent.tag_name.lower()
                        
                        # Stop if we found a list item or article
                        if parent_tag in ['li', 'article', 'div']:
                            parent_text = parent.text
                            # Check if this looks like a complete job card
                            if parent_text and 'India' in parent_text and len(parent_text) > 50:
                                break
                    
                    # Try to find a link within this container
                    try:
                        link_elem = parent.find_element(By.XPATH, './/a[contains(@href, "/jobs/results/")]')
                        job_link = link_elem.get_attribute('href')
                    except:
                        # Try to find any link in the parent
                        try:
                            link_elem = parent.find_element(By.TAG_NAME, 'a')
                            job_link = link_elem.get_attribute('href')
                        except:
                            pass
                    
                    # Extract location from parent text
                    parent_text = parent.text
                    lines = [line.strip() for line in parent_text.split('\n') if line.strip()]
                    
                    for line in lines:
                        if 'Google |' in line or 'YouTube |' in line:
                            location_parts = line.split('|')
                            if len(location_parts) > 1:
                                location = location_parts[1].strip()
                                city, state, _ = self.parse_location(location)
                                break
                        elif 'India' in line and '|' not in line and 'Minimum' not in line and 'qualifications' not in line:
                            # This might be a direct location line
                            if any(city_name in line for city_name in ['Bengaluru', 'Mumbai', 'Delhi', 'Hyderabad', 'Pune', 'Chennai', 'Gurugram', 'Gurgaon', 'Noida']):
                                location = line.strip()
                                city, state, _ = self.parse_location(location)
                                break
                    
                except Exception as e:
                    logger.warning(f"Could not find parent container for job {idx}: {str(e)}")
                
                # Extract job ID from URL or use index
                job_id = f"google_{idx}"
                if job_link and '/jobs/results/' in job_link:
                    try:
                        url_parts = job_link.split('/jobs/results/')[-1]
                        job_id = url_parts.split('-')[0].split('?')[0]
                    except:
                        pass
                
                if not job_link:
                    job_link = self.url
                
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
                    'department': self._infer_department_from_title(job_title),
                    'apply_url': job_link,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }
                
                # Always attempt to fetch full details for better completeness
                if job_link and job_link != self.url:
                    try:
                        full_details = self._fetch_job_details(driver, job_link)
                        if full_details:
                            # Do not overwrite valid listing fields with empty detail values
                            non_empty_details = {
                                k: v for k, v in full_details.items()
                                if v is not None and (not isinstance(v, str) or v.strip())
                            }
                            job_data.update(non_empty_details)
                    except Exception as e:
                        logger.warning(f"Failed to fetch full details for {job_link}: {e}")
                
                jobs.append(job_data)
                logger.debug(f"Extracted job {idx + 1}: {job_title}")
                
            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                continue
        
        return jobs
    
    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {
            'description': '',
            'apply_url': '',
            'posted_date': '',
            'employment_type': '',
            'department': '',
            'job_function': '',
            'experience_level': '',
            'salary_range': '',
            'remote_type': '',
            'location': '',
            'city': '',
            'state': '',
            'country': 'India'
        }

        original_window = None
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            full_job_url = urljoin(self.url, job_url)
            driver.get(full_job_url)
            time.sleep(2)

            # Gather page text for heuristic searches
            try:
                body_text = driver.find_element(By.TAG_NAME, 'body').text
            except:
                body_text = ''

            # 1) Apply URL
            try:
                try:
                    apply_elem = driver.find_element(By.ID, 'apply-action-button')
                    apply_href = apply_elem.get_attribute('href') or apply_elem.get_attribute('data-href')
                    if apply_href:
                        details['apply_url'] = urljoin(full_job_url, apply_href)
                except:
                    apply_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="apply?jobId"], a[aria-label*="Apply"], a[id*="apply"]')
                    if apply_links:
                        details['apply_url'] = urljoin(full_job_url, apply_links[0].get_attribute('href'))
            except Exception:
                pass

            # 2) Locations (collect all shown locations)
            try:
                # Prefer active job header location chips to avoid pulling unrelated sidebar/listing text
                loc_elems = driver.find_elements(By.CSS_SELECTOR, 'div.op1BBf span.pwO9Dc span.r0wTof')
                if not loc_elems:
                    loc_elems = driver.find_elements(By.CSS_SELECTOR, 'span.pwO9Dc span.r0wTof')
                locs = []
                for e in loc_elems:
                    t = e.text.strip().strip(';').strip()
                    t = re.sub(r'\s+', ' ', t)
                    if t and t not in locs:
                        locs.append(t)
                if locs:
                    details['location'] = '; '.join(locs)
                    # parse first location into city/state
                    first = locs[0]
                    parts = [p.strip() for p in first.split(',')]
                    if parts:
                        details['city'] = parts[0]
                    if len(parts) > 1:
                        details['state'] = parts[1]
                    details['country'] = 'India'
            except Exception:
                pass

            # 3) Experience level (UI badge like 'Mid')
            try:
                exp_elems = driver.find_elements(By.CSS_SELECTOR, '.wVSTAb, button[aria-label*="experience"] .VfPpkd-vQzf8d')
                if exp_elems:
                    ev = ''
                    for elem in exp_elems:
                        candidate = elem.text.strip()
                        if candidate in ['Early', 'Mid', 'Advanced'] or candidate.lower().startswith('entry'):
                            ev = candidate
                            break
                    if ev:
                        details['experience_level'] = ev
            except Exception:
                pass

            # 3b) Extract years-of-experience requirement from qualifications text
            try:
                exp_match = re.search(
                    r'((?:\d+\+?|\d+\s*[-–]\s*\d+)\s+years?\s+of\s+experience[^\n\.]*)',
                    body_text,
                    re.I,
                )
                if exp_match:
                    details['experience_level'] = self._normalize_experience_value(exp_match.group(1).strip())
                elif not details.get('experience_level'):
                    # Fallback: minimum years only
                    year_match = re.search(r'(\d+\+?)\s+years?\s+of\s+experience', body_text, re.I)
                    if year_match:
                        details['experience_level'] = self._normalize_experience_value(year_match.group(1).strip())
            except Exception:
                pass

            # 4) Description — only keep core job sections, avoid UI/footer/legal noise
            desc_parts = []
            try:
                selectors = ['div.KwJkGe', 'div.aG5W3', 'div.BDNOWe']
                for sel in selectors:
                    try:
                        script = "var el = document.querySelector('" + sel.replace("'", "\\'") + "'); return el ? el.innerText : null;"
                        txt = driver.execute_script(script)
                        if txt and len(txt.strip()) > 30:
                            desc_parts.append(txt.strip())
                    except Exception:
                        continue
                if not desc_parts and body_text:
                    desc_parts.append(body_text)
                if desc_parts:
                    full_desc = '\n\n'.join(desc_parts)
                    details['description'] = self._clean_google_description(full_desc)[:8000]
            except Exception:
                pass

            # 5) Posted date heuristic (search for common phrases)
            try:
                # look for patterns like 'Posted on March 1, 2026' or ISO dates
                m = re.search(r'(?:Posted(?: on)?:?\s*)([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})', body_text)
                if m:
                    try:
                        dt = datetime.strptime(m.group(1), '%B %d, %Y')
                        details['posted_date'] = dt.strftime('%Y-%m-%d')
                    except Exception:
                        try:
                            dt = datetime.strptime(m.group(1), '%b %d, %Y')
                            details['posted_date'] = dt.strftime('%Y-%m-%d')
                        except Exception:
                            details['posted_date'] = m.group(1)
                else:
                    # ISO-like
                    m2 = re.search(r'(\d{4}-\d{2}-\d{2})', body_text)
                    if m2:
                        details['posted_date'] = m2.group(1)
            except Exception:
                pass

            # 6) Employment type / salary / department heuristics
            try:
                # Use scoped labels to avoid false positives from unrelated page text
                employment_match = re.search(
                    r'(?:Job\s*Type|Employment\s*Type)\s*[:\-]?\s*(Full[- ]?time|Part[- ]?time|Contract|Intern(?:ship)?)',
                    body_text,
                    re.I,
                )
                if employment_match:
                    emp = employment_match.group(1).strip().lower()
                    if 'full' in emp:
                        details['employment_type'] = 'Full Time'
                    elif 'part' in emp:
                        details['employment_type'] = 'Part Time'
                    elif 'intern' in emp:
                        details['employment_type'] = 'Intern'
                    elif 'contract' in emp:
                        details['employment_type'] = 'Contract'
                elif re.search(r'\bintern(ship)?\b', body_text, re.I):
                    # Only keep this safe fallback for intern roles
                    details['employment_type'] = 'Intern'

                if re.search(r'\bremote\b', body_text, re.I):
                    details['remote_type'] = 'Remote'
                elif re.search(r'\bhybrid\b', body_text, re.I):
                    details['remote_type'] = 'Hybrid'
                elif re.search(r'\bon[-\s]?site\b', body_text, re.I):
                    details['remote_type'] = 'On-site'

                sal = re.search(r'(?:\bSalary\b[:\s]*)([\w\s\-–,\d₹$€]+)', body_text, re.I)
                if sal:
                    details['salary_range'] = sal.group(1).strip()
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
        finally:
            try:
                if original_window and len(driver.window_handles) > 0:
                    # close detail tab if still open and switch back
                    if driver.current_window_handle != original_window:
                        driver.close()
                        driver.switch_to.window(original_window)
            except Exception:
                pass

        return details

    def _infer_department_from_title(self, title):
        """Infer a broad department from title keywords."""
        if not title:
            return ''

        t = title.lower()

        keyword_map = [
            ('Engineering', ['engineer', 'developer', 'sre', 'site reliability', 'architect']),
            ('Product', ['product manager', 'product management', 'group product manager']),
            ('Data', ['data scientist', 'data engineer', 'data analyst', 'machine learning', 'ml ']),
            ('Sales', ['account manager', 'sales', 'customer engineer', 'customer solutions', 'solutions engineer']),
            ('Human Resources', ['people consultant', 'hr ', 'human resources', 'talent', 'recruit']),
            ('Operations', ['operations', 'program manager', 'project manager']),
            ('Security', ['security', 'cyber']),
            ('Finance', ['finance', 'accounting']),
            ('Legal', ['legal', 'counsel']),
            ('Marketing', ['marketing', 'brand', 'growth']),
            ('Design', ['designer', 'ux', 'ui']),
            ('Research', ['research', 'scientist']),
        ]

        for department, keywords in keyword_map:
            for kw in keywords:
                if kw in t:
                    return department

        return 'General'

    def _normalize_experience_value(self, exp_text):
        """Normalize experience text to compact forms like '8 years' or '2-4 years'."""
        if not exp_text:
            return ''

        range_match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*years?', exp_text, re.I)
        if range_match:
            return f"{range_match.group(1)}-{range_match.group(2)} years"

        single_match = re.search(r'(\d+)\+?\s*years?', exp_text, re.I)
        if single_match:
            return f"{single_match.group(1)} years"

        return exp_text.strip()

    def _clean_google_description(self, text):
        """Remove duplicated/UI/legal fragments from Google description blocks."""
        if not text:
            return ''

        # Cut off legal/footer content if present
        cut_markers = [
            'Information collected and processed as part of your Google Careers profile',
            'Google is proud to be an equal opportunity and affirmative action employer',
            'To all recruitment agencies: Google does not accept agency resumes',
        ]
        for marker in cut_markers:
            idx = text.find(marker)
            if idx != -1:
                text = text[:idx]

        junk_lines = {
            'share',
            'apply',
            'info_outline',
            'x',
            'corporate_fare',
            'place',
            'bar_chart',
        }

        cleaned_lines = []
        seen = set()
        for raw_line in text.splitlines():
            line = re.sub(r'\s+', ' ', raw_line).strip()
            if not line:
                continue
            if line.lower() in junk_lines:
                continue
            # Avoid repeated paragraphs/headers
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'
        
        # Remove "Google |" or "YouTube |" if present
        location_str = location_str.replace('Google |', '').replace('YouTube |', '').strip()
        
        # Split by comma
        parts = [p.strip() for p in location_str.split(',')]
        
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        
        # Clean up common variations
        if city:
            city = city.strip()
        if state:
            state = state.strip()
        
        return city, state, 'India'

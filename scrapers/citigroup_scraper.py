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

logger = setup_logger('citigroup_scraper')

class CitigroupScraper:
    def __init__(self):
        self.company_name = "Citigroup"
        self.url = "https://jobs.citi.com/location/india-jobs/287/1269750/2"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Citigroup careers page with pagination support"""
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
        """Scrape jobs from current page using NAS/Radancy platform selectors"""
        jobs = []
        time.sleep(2)

        # NAS/Radancy JS extraction: #search-results-list li a
        js_jobs = driver.execute_script("""
            var results = [];
            var seen = {};
            var container = document.querySelector('#search-results-list');
            if (container) {
                var items = container.querySelectorAll('li');
                for (var i = 0; i < items.length; i++) {
                    var item = items[i];
                    var link = item.querySelector('a[href]');
                    if (!link) continue;
                    var title = link.innerText.trim().split('\\n')[0];
                    var url = link.href;
                    if (!title || title.length < 3 || seen[url]) continue;
                    seen[url] = true;
                    var locEl = item.querySelector('.job-location, [class*="location"]');
                    var location = locEl ? locEl.innerText.trim() : '';
                    var dateEl = item.querySelector('.job-date-posted, [class*="date"]');
                    var date = dateEl ? dateEl.innerText.trim() : '';
                    results.push({title: title, url: url, location: location, date: date});
                }
            }
            return results;
        """)

        if not js_jobs:
            logger.warning("No jobs found via NAS/Radancy selectors")
            return jobs

        logger.info(f"NAS/Radancy extraction found {len(js_jobs)} jobs")

        for jdata in js_jobs:
            try:
                title = jdata.get('title', '').strip()
                url = jdata.get('url', '').strip()
                location = jdata.get('location', '').strip()

                if not title or len(title) < 3 or not url:
                    continue

                job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                city, state, _ = self.parse_location(location)

                job_data = {
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
                    'apply_url': url,
                    'posted_date': jdata.get('date', ''),
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }

                # Citi listing pages are incomplete; always enrich from detail page.
                if url:
                    full_details = self._fetch_job_details(driver, url)
                    if full_details:
                        job_data.update(full_details)
                        if full_details.get('location'):
                            city, state, country = self.parse_location(full_details['location'])
                            job_data['city'] = city
                            job_data['state'] = state
                            job_data['country'] = country

                jobs.append(job_data)

            except Exception as e:
                logger.error(f"Error extracting job: {str(e)}")
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
                EC.presence_of_element_located((By.CSS_SELECTOR, 'section.job-description[data-selector-name="jobdetails"]'))
            )
            
            # Extract full description/content block.
            try:
                desc_elem = driver.find_element(By.CSS_SELECTOR, 'section.job-description .ats-description')
                desc_text = driver.execute_script("return arguments[0].innerText;", desc_elem) or ''
                if desc_text.strip():
                    details['description'] = desc_text.strip()
            except Exception:
                pass

            # Extract apply URL from detail page Apply button.
            try:
                apply_elem = driver.find_element(By.CSS_SELECTOR, 'a.button.job-apply')
                apply_url = (apply_elem.get_attribute('data-apply-url') or apply_elem.get_attribute('href') or '').strip()
                if apply_url:
                    details['apply_url'] = apply_url
            except Exception:
                pass

            # Extract structured details from definition list.
            try:
                info_map = {}
                rows = driver.find_elements(By.CSS_SELECTOR, 'section.job-description dl.job-description__desc-list > div')
                for row in rows:
                    try:
                        term = row.find_element(By.CSS_SELECTOR, 'dt.job-description__desc-term').text.strip().rstrip(':')
                        value = row.find_element(By.CSS_SELECTOR, 'dd.job-description__desc-detail').text.strip()
                        if term and value:
                            info_map[term.lower()] = value
                    except Exception:
                        continue

                # Location(s)
                loc_val = info_map.get('location(s)') or info_map.get('location')
                if loc_val:
                    details['location'] = loc_val

                # Remote type / Job type
                job_type_val = info_map.get('job type')
                if job_type_val:
                    details['remote_type'] = job_type_val

                # Posted date
                posted_val = info_map.get('posted')
                if posted_val:
                    details['posted_date'] = self._normalize_posted_date(posted_val)

                # External id from Job Req Id (more stable than URL hash)
                req_id = info_map.get('job req id')
                if req_id:
                    details['external_id'] = self.generate_external_id(req_id, self.company_name)
            except Exception:
                pass

            # Parse additional semantics from long description text.
            desc_for_parse = details.get('description', '')
            if desc_for_parse:
                exp = self._extract_experience_level(desc_for_parse)
                if exp:
                    details['experience_level'] = exp

                job_family_group = self._extract_label_value(desc_for_parse, 'Job Family Group')
                job_family = self._extract_label_value(desc_for_parse, 'Job Family')
                time_type = self._extract_label_value(desc_for_parse, 'Time Type')

                if job_family_group and not details.get('department'):
                    details['department'] = job_family_group
                if job_family and not details.get('job_function'):
                    details['job_function'] = job_family
                if time_type and not details.get('employment_type'):
                    details['employment_type'] = time_type

            if details.get('description'):
                logger.info(f"Fetched Citi full description length={len(details['description'])} for {job_url}")
            
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
        """Convert formats like 'Mar. 13, 2026' to YYYY-MM-DD when possible."""
        if not posted_text:
            return ''

        txt = posted_text.strip().replace('.', '')
        for fmt in ('%b %d, %Y', '%B %d, %Y', '%d %b %Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(txt, fmt).strftime('%Y-%m-%d')
            except Exception:
                continue
        return posted_text.strip()

    def _extract_label_value(self, text, label):
        """Extract value that follows labels like 'Job Family Group:' in plain text."""
        if not text:
            return ''

        pattern = rf'{re.escape(label)}\s*:\s*\n?\s*([^\n]+)'
        m = re.search(pattern, text, flags=re.IGNORECASE)
        return (m.group(1).strip() if m else '')

    def _extract_experience_level(self, text):
        """Extract experience strings like '8+ years of relevant experience'."""
        if not text:
            return ''

        patterns = [
            r'(\b\d+\s*(?:-|to)\s*\d+\+?\s*years?\b)',
            r'(\b\d+\+?\s*years?\b)\s+(?:of\s+)?(?:relevant\s+)?experience',
            r'experience\s*(?:of|:)?\s*(\d+\s*(?:-|to)\s*\d+\+?\s*years?\b)',
            r'experience\s*(?:of|:)?\s*(\d+\+?\s*years?\b)',
        ]

        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if not m:
                continue
            val = (m.group(1) or '').strip()
            val = re.sub(r'\s+', ' ', val)
            if val:
                return val.replace(' to ', '-')

        return ''
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',') if p.strip()]
        if not parts:
            return '', '', 'India'

        # Format: "City, State, India"
        if len(parts) >= 3:
            # Format like "Haryana, India, Remote" -> state-level location
            if parts[1].lower() == 'india':
                return '', parts[0], 'India'
            city = parts[0]
            state = parts[1]
            return city, state, 'India'

        # Format: "State, India"
        if len(parts) == 2 and parts[1].lower() == 'india':
            return '', parts[0], 'India'

        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        if city.lower() in {'india', 'remote'}:
            city = ''

        return city, state, 'India'

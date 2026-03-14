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

logger = setup_logger('colgatepalmolive_scraper')

class ColgatePalmoliveScraper:
    def __init__(self):
        self.company_name = "Colgate-Palmolive"
        self.url = "https://jobs.colgate.com/go/View-All-Jobs/8506400/?markerViewed=&carouselIndex=&facetFilters=%7B%22filter1%22%3A%5B%22India%22%5D%7D&pageNumber=0"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Colgate-Palmolive careers page with pagination support"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            time.sleep(10)

            current_url = driver.current_url
            logger.info(f"Landed on: {current_url}")

            # If NAS container not found, try the View All Jobs page
            has_nas = 'search-results-list' in driver.page_source
            if not has_nas:
                logger.info("NAS container not found, navigating to View All Jobs page")
                driver.get('https://jobs.colgate.com/go/View-All-Jobs/8506400/')
                time.sleep(10)
                logger.info(f"Redirected to: {driver.current_url}")

            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(3)

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
                    time.sleep(1)
                    next_button.click()
                    logger.info(f"Clicked next page button")
                    return True
                except:
                    continue
            
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver, wait):
        """Scrape jobs - tries NAS/Radancy first, then generic job link extraction"""
        jobs = []
        time.sleep(3)

        # Scroll to load dynamic content
        for scroll_i in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        # Strategy 1: NAS/Radancy JS extraction
        js_jobs = driver.execute_script("""
            var results = [];
            var seen = {};
            var container = document.querySelector('#search-results-list');
            if (container) {
                var items = container.querySelectorAll('li, div.list-item');
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
                    results.push({title: title, url: url, location: location});
                }
            }
            return results;
        """)

        if js_jobs:
            logger.info(f"NAS/Radancy extraction found {len(js_jobs)} jobs")
        else:
            # Strategy 2: Generic job link extraction (SuccessFactors / /go/ pages)
            logger.info("Trying generic job link extraction")
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};
                var links = document.querySelectorAll('a[href*="/job/"]');
                for (var i = 0; i < links.length; i++) {
                    var a = links[i];
                    var t = (a.innerText || '').trim().split('\\n')[0];
                    var h = a.href;
                    if (t.length > 3 && t.length < 200 && !seen[h]) {
                        if (h.indexOf('login') > -1 || h.indexOf('sign-in') > -1) continue;
                        seen[h] = true;
                        var parent = a.closest('tr, li, div[class*="job"], article');
                        var location = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], .job-location, td:nth-child(2)');
                            if (locEl) location = locEl.innerText.trim();
                        }
                        results.push({title: t, url: h, location: location});
                    }
                }
                return results;
            """)
            if js_jobs:
                logger.info(f"Generic extraction found {len(js_jobs)} jobs")

        if not js_jobs:
            logger.warning("No jobs found on page")
            return jobs

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
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }

                if FETCH_FULL_JOB_DETAILS and url:
                    full_details = self._fetch_job_details(driver, url)
                    job_data.update(full_details)
                # Enrich with full job details regardless of global flag (ensures full descriptions)
                if url and not job_data.get('description'):
                    try:
                        full_details = self._fetch_job_details(driver, url)
                        if full_details:
                            job_data.update(full_details)
                    except Exception:
                        logger.debug('Detail fetch failed for %s', url)

                jobs.append(job_data)

            except Exception as e:
                logger.error(f"Error extracting job: {str(e)}")
                continue

        return jobs
    
    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}
        
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
            driver.get(job_url)
            # small wait for JS-rendered content
            time.sleep(2)

            page_src = driver.page_source

            # Extract description(s) using common selectors and itemprop
            desc_texts = []
            try:
                desc_elems = driver.find_elements(By.CSS_SELECTOR, '[itemprop="description"], div[class*="description"], div.job-description')
                for el in desc_elems:
                    try:
                        text = driver.execute_script('return arguments[0].innerText;', el)
                        if text:
                            desc_texts.append(text.strip())
                    except:
                        try:
                            text = el.text
                            if text:
                                desc_texts.append(text.strip())
                        except:
                            continue
            except Exception:
                pass

            # fallback: try pulling a large text blob from body if nothing found
            if not desc_texts:
                try:
                    body = driver.find_element(By.TAG_NAME, 'body')
                    body_text = driver.execute_script('return arguments[0].innerText;', body)
                    if body_text:
                        desc_texts.append(body_text.strip())
                except:
                    pass

            if desc_texts:
                details['description'] = '\n\n'.join(desc_texts)[:20000]

            # Apply link: look for common apply button patterns
            try:
                apply_el = None
                candidates = driver.find_elements(By.CSS_SELECTOR, 'a.unify-apply-now, a.apply, a[href*="/apply"], a[href*="talentcommunity"], a[href*="/job/"]')
                for a in candidates:
                    try:
                        href = a.get_attribute('href')
                        if href and ('apply' in href or 'talentcommunity' in href):
                            apply_el = a
                            break
                    except:
                        continue

                if not apply_el and candidates:
                    apply_el = candidates[0]

                if apply_el:
                    href = apply_el.get_attribute('href')
                    if href:
                        details['apply_url'] = urljoin(job_url, href)
            except Exception:
                pass

            # Posted date: try regex first on visible text
            try:
                m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b", page_src)
                if m:
                    norm = self._normalize_posted_date(m.group(1))
                    if norm:
                        details['posted_date'] = norm
            except Exception:
                pass

            # Remote type / employment hints
            try:
                if 'On-site' in page_src or 'On-site' in driver.page_source:
                    details['remote_type'] = 'On-site'
                elif 'Remote' in page_src or 'Remote' in driver.page_source:
                    details['remote_type'] = 'Remote'
            except:
                pass

            # Try extracting visible location tokens to enrich city/state/country
            try:
                loc_match = re.search(r'([A-Za-z\s]+),\s*([A-Za-z\s]+),\s*([A-Za-z\s]+)', page_src)
                if loc_match:
                    city = loc_match.group(1).strip()
                    state = loc_match.group(2).strip()
                    country = loc_match.group(3).strip()
                    details['city'] = city
                    details['state'] = state
                    details['country'] = country
                else:
                    if 'Barcelona' in page_src:
                        details['city'] = 'Barcelona'
                        details['country'] = 'Spain'
                    elif 'Spain' in page_src:
                        details['country'] = 'Spain'
            except:
                pass

            driver.close()
            driver.switch_to.window(original_window)
            
        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
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

        parts = [p.strip() for p in location_str.split(',') if p.strip()]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        # detect country heuristics
        country = 'India'
        loc_lower = location_str.lower()
        if 'spain' in loc_lower or 'barcelona' in loc_lower or 'catal' in loc_lower:
            country = 'Spain'
        elif 'india' in loc_lower or 'bengaluru' in loc_lower or 'mumbai' in loc_lower:
            country = 'India'

        return city, state, country

    def _normalize_posted_date(self, date_str):
        """Normalize various short date formats to YYYY-MM-DD. Returns empty string on failure."""
        if not date_str:
            return ''
        date_str = date_str.strip()
        for fmt in ('%m/%d/%y', '%d/%m/%y', '%m/%d/%Y', '%d/%m/%Y'):
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.year < 1970:
                    if dt.year < 100:
                        dt = dt.replace(year=dt.year + 2000)
                return dt.strftime('%Y-%m-%d')
            except Exception:
                continue
        return ''

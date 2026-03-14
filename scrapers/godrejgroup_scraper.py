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

logger = setup_logger('godrejgroup_scraper')

class GodrejGroupScraper:
    def __init__(self):
        self.company_name = "Godrej Group"
        self.url = "https://godrejcareers.peoplestrong.com/job/joblist"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Godrej Group careers page.

        The godrej.com/careers page is a corporate landing page. The actual job listings
        are on godrejenterprises.com/about-us/careers/openings which has a table of job openings.
        The scraper navigates from the original URL to the actual listings page.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # The godrej.com/careers page links to godrejenterprises.com which has actual job listings
            # Navigate directly to the openings page
            driver.get(self.url)
            time.sleep(12)

            # Look for link to Godrej Enterprises (where actual jobs are)
            enterprises_url = 'https://www.godrejenterprises.com/about-us/careers/openings'
            try:
                explore_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="godrejenterprises"]')
                if explore_links:
                    enterprises_url = explore_links[0].get_attribute('href')
                    if '/careers' not in enterprises_url:
                        enterprises_url = 'https://www.godrejenterprises.com/about-us/careers/openings'
                    logger.info(f"Found Godrej Enterprises link: {enterprises_url}")
            except Exception as e:
                logger.warning(f"Could not find enterprises link: {e}")

            logger.info(f"Navigating to job listings: {enterprises_url}")
            driver.get(enterprises_url)
            time.sleep(15)

            # Scroll to load all content
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try clicking "See all" button to load all jobs
            try:
                see_all = driver.find_elements(By.XPATH, '//button[contains(text(),"See all")] | //a[contains(text(),"See all")]')
                if see_all:
                    driver.execute_script("arguments[0].click();", see_all[0])
                    logger.info("Clicked 'See all' button")
                    time.sleep(3)
            except Exception as e:
                logger.debug(f"No 'See all' button: {e}")

            # Extract jobs from the table using JavaScript
            jobs = self._extract_jobs_js(driver)

            # Enrich each job with detail page content when available
            for j in jobs:
                try:
                    href = j.get('apply_url') or j.get('href')
                    if href:
                        details = self._fetch_job_details(driver, href)
                        if details:
                            # only overwrite keys if details provide values
                            for k, v in details.items():
                                if v:
                                    j[k] = v
                except Exception as e:
                    logger.debug(f"Failed to fetch details for {j.get('apply_url')}: {e}")

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _fetch_job_details(self, driver, job_url):
        """Open job detail page and extract rich fields (description, experience, posted_date, department)."""
        details = {}
        try:
            original = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(job_url)
            time.sleep(2)

            # Extract description blocks (many pages use <pre> for content)
            try:
                pres = driver.find_elements(By.TAG_NAME, 'pre')
                desc_parts = []
                for p in pres:
                    try:
                        t = driver.execute_script('return arguments[0].innerText;', p)
                        if t:
                            desc_parts.append(t.strip())
                    except:
                        try:
                            if p.text:
                                desc_parts.append(p.text.strip())
                        except:
                            continue
                if desc_parts:
                    details['description'] = '\n\n'.join(desc_parts)[:20000]
            except Exception:
                pass

            # Extract summary fields (Company Name, Business, Function, Designation, Location)
            try:
                # function / department
                func = ''
                func_els = driver.find_elements(By.CSS_SELECTOR, 'span.valuetext')
                if func_els and len(func_els) >= 3:
                    # known order from template: Company, Business, Function, Designation, Location
                    func = func_els[2].text.strip()
                if func:
                    details['department'] = func
                    details['job_function'] = func
                # location
                try:
                    loc_el = driver.find_element(By.CSS_SELECTOR, 'span.valuetext')
                    if loc_el and loc_el.text:
                        # the last valuetext is location in template; fallback keep original
                        details['location'] = loc_el.text.strip()
                        city, state, country = self.parse_location(details['location'])
                        details['city'] = city
                        details['state'] = state
                        details['country'] = country
                except Exception:
                    pass
            except Exception:
                pass

            # Experience: look for 'Experience Details' pre or keywords
            try:
                exp_text = ''
                try:
                    exp_header = driver.find_element(By.XPATH, "//h4[contains(., 'Experience Details')]")
                    # next sibling pre
                    exp_pre = exp_header.find_element(By.XPATH, 'following-sibling::div//pre')
                    exp_text = exp_pre.text.strip() if exp_pre.text else ''
                except Exception:
                    # try to search for 'Experience' headings or sections
                    pres = driver.find_elements(By.TAG_NAME, 'pre')
                    for p in pres:
                        txt = p.text or ''
                        if 'experience' in txt.lower() or re.search(r'\d{1,2}\s*-\s*\d{1,2}\s*years', txt.lower()):
                            exp_text = txt
                            break

                if exp_text:
                    # capture patterns like '8-9 years' or '6-7 years' or '8 years'
                    matches = re.findall(r"\d{1,2}\s*-\s*\d{1,2}\s*years|\d{1,2}\+?\s*years", exp_text, flags=re.IGNORECASE)
                    if matches:
                        details['experience_level'] = '; '.join([m.strip() for m in matches])
                    else:
                        # store raw if no explicit pattern
                        details['experience_level'] = exp_text.strip()[:200]
            except Exception:
                pass

            # Posted date: try to find date patterns on page
            try:
                page = driver.page_source
                m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b", page)
                if m:
                    pd = self._normalize_posted_date(m.group(1))
                    if pd:
                        details['posted_date'] = pd
            except Exception:
                pass

            # Normalize apply_url
            try:
                details['apply_url'] = urljoin(job_url, driver.current_url)
            except:
                details['apply_url'] = job_url

            driver.close()
            driver.switch_to.window(original)
        except Exception as e:
            logger.debug(f"Error fetching Godrej details {job_url}: {e}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass

        return details

    def _extract_jobs_js(self, driver):
        """Extract jobs from the Godrej Enterprises careers table using JavaScript"""
        jobs = []

        # Primary: Extract from table rows via JS
        try:
            table_data = driver.execute_script("""
                var results = [];
                var rows = document.querySelectorAll('table tr');
                for (var i = 0; i < rows.length; i++) {
                    var cells = rows[i].querySelectorAll('td');
                    if (cells.length >= 3) {
                        var titleCell = cells[0];
                        var link = titleCell.querySelector('a');
                        var titleText = titleCell.innerText.trim();
                        var lines = titleText.split('\\n');
                        var title = lines[0] ? lines[0].trim() : '';
                        var location = lines[1] ? lines[1].trim() : '';
                        var href = link ? link.href : '';
                        var businessUnit = cells[1] ? cells[1].innerText.trim() : '';
                        var func = cells[2] ? cells[2].innerText.trim() : '';
                        if (title && title.length > 2 && title !== 'DESIGNATION/' && title !== 'LOCATION') {
                            results.push({
                                title: title,
                                location: location,
                                href: href,
                                businessUnit: businessUnit,
                                department: func
                            });
                        }
                    }
                }
                return results;
            """)

            if table_data:
                logger.info(f"JS table extraction found {len(table_data)} jobs")
                for idx, job_data in enumerate(table_data):
                    title = job_data.get('title', '')
                    href = job_data.get('href', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    business_unit = job_data.get('businessUnit', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = f"godrejgroup_{idx}"
                    if href:
                        # Extract SRNO from URL like vacancy-details?SRNO=30317
                        if 'SRNO=' in href:
                            job_id = href.split('SRNO=')[-1].split('&')[0]
                        else:
                            job_id = hashlib.md5(href.encode()).hexdigest()[:12]

                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': f"Business Unit: {business_unit}" if business_unit else '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country if country else 'India',
                        'employment_type': '',
                        'department': department,
                        'apply_url': href if href else self.url,
                        'posted_date': '',
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
        except Exception as e:
            logger.error(f"JS table extraction failed: {e}")

        # Fallback: Extract from career opportunity links
        if not jobs:
            logger.info("Table extraction failed, trying link-based fallback")
            try:
                link_data = driver.execute_script("""
                    var results = [];
                    var seen = {};
                    document.querySelectorAll('a[href*="careeropportunities"], a[href*="vacancy-details"], a[href*="CareerWEB"]').forEach(function(a) {
                        var text = (a.innerText || '').trim().split('\\n')[0].trim();
                        var href = a.href;
                        if (text.length > 3 && text.length < 200 && !seen[href]) {
                            seen[href] = true;
                            var exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'apply'];
                            var skip = false;
                            for (var i = 0; i < exclude.length; i++) {
                                if (text.toLowerCase() === exclude[i]) { skip = true; break; }
                            }
                            if (!skip) {
                                // Try to get location from parent row
                                var row = a.closest('tr');
                                var location = '';
                                var dept = '';
                                var bUnit = '';
                                if (row) {
                                    var cells = row.querySelectorAll('td');
                                    if (cells.length >= 3) {
                                        var lines = cells[0].innerText.trim().split('\\n');
                                        location = lines[1] ? lines[1].trim() : '';
                                        bUnit = cells[1] ? cells[1].innerText.trim() : '';
                                        dept = cells[2] ? cells[2].innerText.trim() : '';
                                    }
                                }
                                results.push({title: text, href: href, location: location, department: dept, businessUnit: bUnit});
                            }
                        }
                    });
                    return results;
                """)

                if link_data:
                    logger.info(f"Link fallback found {len(link_data)} jobs")
                    for idx, ld in enumerate(link_data):
                        title = ld.get('title', '')
                        href = ld.get('href', '')
                        location = ld.get('location', '')
                        department = ld.get('department', '')

                        if not title or len(title) < 3:
                            continue

                        job_id = hashlib.md5(href.encode()).hexdigest()[:12] if href else f"godrejgroup_{idx}"
                        city, state, country = self.parse_location(location)

                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': country if country else 'India',
                            'employment_type': '',
                            'department': department,
                            'apply_url': href if href else self.url,
                            'posted_date': '',
                            'job_function': department,
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })
            except Exception as e:
                logger.error(f"Link fallback failed: {e}")

        return jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

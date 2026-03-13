from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import html
import re
import time
import os
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('flipkart_scraper')

class FlipkartScraper:
    def __init__(self):
        self.company_name = "Flipkart"
        # Use job search page with hash routing
        self.url = "https://www.flipkartcareers.com/flipkart/jobslist"
        self.base_url = 'https://www.flipkartcareers.com'

    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)
    
    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Flipkart careers page using careers APIs via browser context."""
        jobs = []
        driver = None
        
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Open careers page first so browser session can call protected API endpoints.
            logger.info(f"Navigating to {self.url}")
            driver.get(self.url)
            time.sleep(8)

            page_size = 10
            seen_external_ids = set()

            for page_index in range(max_pages):
                offset = page_index * page_size
                logger.info(f"Fetching API page {page_index + 1}/{max_pages} (offset={offset})")

                page_items = self._fetch_jobs_page_api(driver, offset)
                if not page_items:
                    logger.info("No jobs returned by API for this page; stopping pagination")
                    break

                page_added = 0
                for item in page_items:
                    source = item.get('_source', {}) if isinstance(item, dict) else {}
                    job_id = source.get('id')
                    if not job_id:
                        continue

                    details = None
                    if FETCH_FULL_JOB_DETAILS:
                        details = self._fetch_job_detail_api(driver, source)

                    job = self._build_job_record(source, details)
                    if not job:
                        continue

                    needs_page_enrichment = len((job.get('description') or '').strip()) < 120
                    if (FETCH_FULL_JOB_DETAILS or needs_page_enrichment) and job.get('apply_url'):
                        page_details = self._fetch_job_page_details(driver, job['apply_url'])
                        if page_details:
                            if page_details.get('description') and len(page_details['description']) > len(job.get('description', '')):
                                job['description'] = page_details['description']
                            if page_details.get('experience_level'):
                                job['experience_level'] = page_details['experience_level']
                            if page_details.get('job_function'):
                                job['job_function'] = page_details['job_function']
                            if page_details.get('posted_date'):
                                job['posted_date'] = page_details['posted_date']
                            if page_details.get('location'):
                                job['location'] = page_details['location']
                                city, state, country = self.parse_location(page_details['location'])
                                job['city'] = city
                                job['state'] = state
                                job['country'] = country
                            if page_details.get('department') and not job.get('department'):
                                job['department'] = page_details['department']

                    if job['external_id'] in seen_external_ids:
                        continue

                    seen_external_ids.add(job['external_id'])
                    jobs.append(job)
                    page_added += 1

                logger.info(f"API page {page_index + 1}: added {page_added} jobs (total: {len(jobs)})")

                # If API returns fewer than page size, assume last page.
                if len(page_items) < page_size:
                    break

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
            
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        finally:
            if driver:
                driver.quit()
        
        return jobs
    
    def _fetch_jobs_page_api(self, driver, offset):
        """Fetch one listing page from the jobs/search API through browser context."""
        try:
            script = """
                const done = arguments[arguments.length - 1];
                const start = arguments[0];
                const fd = new FormData();
                fd.append('filterCri', JSON.stringify({
                    paginationStartNo: start,
                    selectedCall: 'sort',
                    sortCriteria: {name: 'modifiedDate', isAscending: false},
                    anyOfTheseWords: ''
                }));
                fd.append('domain', 'www.flipkartcareers.com');
                fd.append('companyId', 'MTUxMTA=');

                fetch('https://public.zwayam.com/jobs/search', {method: 'POST', body: fd})
                  .then(r => r.json())
                  .then(j => done(j))
                  .catch(e => done({error: String(e)}));
            """

            response = driver.execute_async_script(script, offset)
            if not isinstance(response, dict):
                return []
            if response.get('error'):
                logger.warning(f"jobs/search API error: {response.get('error')}")
                return []

            data = response.get('data', {}) if isinstance(response.get('data'), dict) else {}
            items = data.get('data', []) if isinstance(data.get('data'), list) else []
            return items
        except Exception as e:
            logger.error(f"Error fetching jobs/search API page: {str(e)}")
            return []

    def _fetch_job_detail_api(self, driver, source):
        """Fetch full job detail from jobs-service/v1/jobs/careersite."""
        try:
            job_id = source.get('id')
            job_url_slug = source.get('jobUrl')
            if not job_id or not job_url_slug:
                return None

            if '?id=' in job_url_slug:
                job_url_param = job_url_slug
            else:
                job_url_param = f"{job_url_slug}?id={job_id}"

            script = """
                const done = arguments[arguments.length - 1];
                const payload = {
                    jobUrl: arguments[0],
                    externalSource: 'CareerSite',
                    campusUrl: 'empty',
                    companyId: '15110',
                    jobId: String(arguments[1])
                };

                fetch('https://public.zwayam.com/jobs-service/v1/jobs/careersite', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                })
                .then(r => r.json())
                .then(j => done(j))
                .catch(e => done({error: String(e)}));
            """

            detail = driver.execute_async_script(script, job_url_param, str(job_id))
            if isinstance(detail, dict) and detail.get('error'):
                logger.warning(f"jobs/careersite detail API error for {job_id}: {detail.get('error')}")
                return None
            return detail if isinstance(detail, dict) else None
        except Exception as e:
            logger.warning(f"Error fetching detail API for job {source.get('id')}: {str(e)}")
            return None

    def _build_job_record(self, source, detail):
        """Normalize listing/detail payloads into standard job schema."""
        try:
            merged = {}
            merged.update(source or {})
            merged.update(detail or {})

            cfg = merged.get('jobConfigurationData') if isinstance(merged.get('jobConfigurationData'), dict) else {}

            job_id = merged.get('id')
            title = (merged.get('jobTitle') or merged.get('Requisition Title') or '').strip()
            if not title:
                return None

            location = (merged.get('location') or merged.get('Location') or cfg.get('Location') or '').strip()
            city, state, country = self.parse_location(location)

            job_url_slug = merged.get('jobUrl') or source.get('jobUrl')
            if job_url_slug:
                if '?id=' in job_url_slug:
                    apply_url = f"{self.base_url}/flipkart/jobview/{job_url_slug}"
                else:
                    apply_url = f"{self.base_url}/flipkart/jobview/{job_url_slug}?id={job_id}"
            else:
                apply_url = self.url

            description = (
                merged.get('longDescription')
                or merged.get('mediumDescriptionWithoutHtml')
                or cfg.get('Description')
                or merged.get('Description')
                or ''
            )
            description = self._strip_html(description).strip()[:12000]

            experience_level = (
                merged.get('experienceUIField')
                or cfg.get('Years Of Exp')
                or self._format_experience(merged.get('minYrsOfExperience'), merged.get('maxYrsOfExperience'))
            )

            posted_date = self._format_timestamp(merged.get('modifiedDate') or merged.get('createdDate'))

            return {
                'external_id': self.generate_external_id(str(job_id), self.company_name),
                'company_name': self.company_name,
                'title': title,
                'description': description,
                'location': location,
                'city': city,
                'state': state,
                'country': country,
                'employment_type': (merged.get('jobType') or merged.get('employeeType') or '').strip(),
                'department': (merged.get('departmentName') or merged.get('DepartmentName') or '').strip(),
                'apply_url': apply_url,
                'posted_date': posted_date,
                'job_function': (merged.get('jobFunction') or merged.get('skillSet') or merged.get('metaKeywords') or cfg.get('Skills Required') or '').strip(),
                'experience_level': (experience_level or '').strip(),
                'salary_range': self._format_salary(merged.get('minJobSalary'), merged.get('maxJobSalary')),
                'remote_type': '',
                'status': 'active'
            }
        except Exception as e:
            logger.warning(f"Error normalizing Flipkart job record: {str(e)}")
            return None

    def _fetch_job_page_details(self, driver, job_url):
        """Open jobview page and parse rich fields displayed in the UI."""
        details = {}
        original_window = None
        
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open(arguments[0], '_blank');", job_url)
            driver.switch_to.window(driver.window_handles[-1])
            time.sleep(4)

            # Sometimes a cookie notice overlays content.
            try:
                cookie_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Continue')]")
                if cookie_btns:
                    driver.execute_script("arguments[0].click();", cookie_btns[0])
                    time.sleep(0.5)
            except Exception:
                pass

            # Parse labeled attributes in the job details section.
            attr_rows = driver.find_elements(By.CSS_SELECTOR, ".job-view__attribute .row")
            attr_map = {}
            for row in attr_rows:
                try:
                    label_el = row.find_element(By.CSS_SELECTOR, ".attribute-label .attribute-text")
                    value_el = row.find_element(By.CSS_SELECTOR, ".attribute-data")
                    key = label_el.text.strip().rstrip(':')
                    val = self._strip_html(value_el.get_attribute('innerHTML') or '').strip()
                    if key and val:
                        attr_map[key] = val
                except Exception:
                    continue

            # Posted date appears in the page header.
            posted_text = ''
            try:
                posted_el = driver.find_element(By.CSS_SELECTOR, "h2.theme-posted")
                posted_text = posted_el.text.strip()
            except Exception:
                posted_text = ''

            location = attr_map.get('Location', '').strip()
            skills = attr_map.get('Skills Required', '').strip()
            years = attr_map.get('Years Of Exp', '').strip()

            # Build a rich description by combining top narrative sections.
            description_parts = []
            for key in [
                'Job Description',
                'About the Role',
                'About the team',
                'You are Responsible for',
                'To succeed in this role – you should have the following'
            ]:
                value = attr_map.get(key, '').strip()
                if value:
                    description_parts.append(f"{key}: {value}")

            details['description'] = "\n\n".join(description_parts)[:15000] if description_parts else ''
            details['experience_level'] = years
            details['job_function'] = skills
            details['location'] = location
            details['department'] = attr_map.get('Function', '').strip()
            details['posted_date'] = self._parse_posted_text(posted_text)

        except Exception as e:
            logger.debug(f"Error enriching from jobview page {job_url}: {e}")
        finally:
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    if original_window:
                        driver.switch_to.window(original_window)
            except Exception:
                pass

        return details

    def _parse_posted_text(self, posted_text):
        """Convert text like 'Posted 3 months ago' to a best-effort date."""
        if not posted_text:
            return ''
        match = re.search(r'(\d+)\s+(day|days|month|months|year|years)\s+ago', posted_text.lower())
        if not match:
            return ''
        qty = int(match.group(1))
        unit = match.group(2)
        now = datetime.utcnow()
        if 'day' in unit:
            dt = now.timestamp() - (qty * 86400)
        elif 'month' in unit:
            dt = now.timestamp() - (qty * 30 * 86400)
        else:
            dt = now.timestamp() - (qty * 365 * 86400)
        return datetime.utcfromtimestamp(dt).strftime('%Y-%m-%d')

    def _strip_html(self, text):
        """Remove basic HTML tags and collapse whitespace."""
        if not text:
            return ''
        cleaned = re.sub(r'<[^>]+>', ' ', str(text))
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = html.unescape(cleaned)
        return cleaned.strip()

    def _format_timestamp(self, value):
        """Convert epoch milliseconds or timestamp-like values to YYYY-MM-DD."""
        if not value:
            return ''
        try:
            ts = int(value)
            if ts > 10**12:
                ts = ts / 1000
            return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
        except Exception:
            return ''

    def _format_experience(self, min_exp, max_exp):
        """Build readable experience range."""
        if min_exp is None and max_exp is None:
            return ''
        if min_exp is None:
            return f"Up to {max_exp} years"
        if max_exp is None:
            return f"{min_exp}+ years"
        return f"{min_exp}-{max_exp} years"

    def _format_salary(self, min_salary, max_salary):
        """Build salary range string when both values exist."""
        if min_salary in (None, '') and max_salary in (None, ''):
            return ''
        if min_salary in (None, ''):
            return str(max_salary)
        if max_salary in (None, ''):
            return str(min_salary)
        return f"{min_salary} - {max_salary}"
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'
        
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        
        return city, state, 'India'

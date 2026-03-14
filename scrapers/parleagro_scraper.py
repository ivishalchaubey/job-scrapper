import hashlib
import re
import time
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('parleagro_scraper')


class ParleAgroScraper:
    def __init__(self):
        self.company_name = 'Parle Agro'
        self.url = 'https://paplconnectplus.darwinbox.in/ms/candidatev2/main/careers/allJobs'
        self.base_url = 'https://paplconnectplus.darwinbox.in'
        self.india_keywords = [
            'india', 'mumbai', 'delhi', 'bangalore', 'bengaluru',
            'hyderabad', 'chennai', 'pune', 'gurugram', 'gurgaon',
            'noida', 'kolkata', 'ahmedabad', 'jaipur', 'kochi',
            'thiruvananthapuram', 'chandigarh', 'lucknow', 'indore',
            'bhopal', 'ghaziabad', 'khurda', 'mysore', 'tiruchchirappalli',
            'maharashtra', 'karnataka', 'uttar pradesh', 'madhya pradesh',
            'odisha', 'tamil nadu'
        ]

    def setup_driver(self):
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)

            wait = WebDriverWait(driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.jobs-section[id]')))

            page_idx = 1
            while page_idx <= max_pages:
                logger.info(f"Extracting visible jobs batch {page_idx}")
                visible_jobs = self._extract_jobs_from_listing(driver)
                new_jobs = 0

                for job in visible_jobs:
                    job_id = job.get('job_id', '')
                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    # Fetch details from jobDetails page to fill description/experience/posted_date.
                    if job.get('apply_url'):
                        details = self._fetch_job_details(driver, job['apply_url'])
                        self._merge_job_details(job, details)

                    all_jobs.append(job)
                    new_jobs += 1

                logger.info(f"Added {new_jobs} new jobs in batch {page_idx}")

                if page_idx >= max_pages:
                    break

                if not self._click_load_more(driver):
                    logger.info('No more jobs to load')
                    break

                page_idx += 1

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as exc:
            logger.error(f"Error scraping {self.company_name}: {str(exc)}")
            raise

        finally:
            if driver:
                driver.quit()

        return all_jobs

    def _extract_jobs_from_listing(self, driver):
        jobs = []

        data = driver.execute_script(
            """
            const base = window.location.origin;
            const sections = Array.from(document.querySelectorAll('div.jobs-section[id]'));
            return sections.map((section) => {
                const jobId = (section.id || '').trim();
                const title = (section.querySelector('.job-title')?.textContent || '').trim();
                const applyHref = section.querySelector('a.action-btn[href*="/jobDetails/"]')?.getAttribute('href') || '';
                const location = (section.querySelector('.details-section .sub-section img[src*="location"]')?.closest('.sub-section')?.querySelector('span')?.textContent || '').trim();
                const experience = (section.querySelector('.details-section .sub-section img[src*="experience"]')?.closest('.sub-section')?.querySelector('span')?.textContent || '').trim();
                const employeeType = (section.querySelector('.details-section .sub-section img[src*="work-mode"]')?.closest('.sub-section')?.querySelector('span')?.textContent || '').trim();
                const shortDesc = (section.querySelector('.job-description span')?.textContent || '').trim();
                let fullUrl = applyHref;
                if (applyHref && applyHref.startsWith('/')) {
                    fullUrl = base + applyHref;
                }
                return {
                    job_id: jobId,
                    title: title,
                    apply_url: fullUrl,
                    location: location,
                    experience_level: experience,
                    employment_type: employeeType,
                    description: shortDesc
                };
            });
            """
        )

        seen_titles = set()
        for item in data or []:
            title = (item.get('title') or '').strip()
            if not self._is_valid_title(title):
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)

            apply_url = (item.get('apply_url') or '').strip()
            location = (item.get('location') or '').strip()
            if location and not self._is_india_location(location):
                continue

            city, state, country = self.parse_location(location)
            job_id = (item.get('job_id') or '').strip()
            if not job_id:
                job_id = hashlib.md5((apply_url or title).encode()).hexdigest()[:12]

            jobs.append({
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'description': (item.get('description') or '').strip(),
                'location': location,
                'city': city,
                'state': state,
                'country': country or 'India',
                'employment_type': (item.get('employment_type') or '').strip(),
                'department': '',
                'apply_url': apply_url or self.url,
                'posted_date': '',
                'job_function': '',
                'experience_level': (item.get('experience_level') or '').strip(),
                'salary_range': '',
                'remote_type': '',
                'status': 'active',
                'job_id': job_id,
            })

        return jobs

    def _click_load_more(self, driver):
        try:
            old_count = len(driver.find_elements(By.CSS_SELECTOR, 'div.jobs-section[id]'))
            load_more = driver.find_element(By.XPATH, "//div[contains(@class, 'load-more-section') and contains(., 'Load More Jobs')]")
            driver.execute_script('arguments[0].scrollIntoView({block: "center"});', load_more)
            driver.execute_script('arguments[0].click();', load_more)

            for _ in range(25):
                time.sleep(0.2)
                new_count = len(driver.find_elements(By.CSS_SELECTOR, 'div.jobs-section[id]'))
                if new_count > old_count:
                    return True
            return False
        except Exception:
            return False

    def _fetch_job_details(self, driver, job_url):
        details = {}
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open(arguments[0], '_blank');", job_url)
            driver.switch_to.window(driver.window_handles[-1])

            wait = WebDriverWait(driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.details-container')))

            title = self._safe_text(driver, By.CSS_SELECTOR, 'div.header-section .title')
            location = self._safe_text(driver, By.CSS_SELECTOR, 'div.header-section img[src*="location"] + span')
            experience = self._safe_text(driver, By.CSS_SELECTOR, 'div.header-section img[src*="experience"] + span span, div.header-section img[src*="experience"] + span')
            employee_type = self._safe_text(driver, By.CSS_SELECTOR, 'div.header-section img[src*="work-mode"] + span span, div.header-section img[src*="work-mode"] + span')

            # Pull long-form job description from details box.
            jd_text = self._safe_text(driver, By.CSS_SELECTOR, 'div.details-box .jd')
            jd_text = self._clean_description(jd_text)

            snapshot = self._extract_snapshot_fields(driver)

            details = {
                'title': title,
                'location': location or snapshot.get('location', ''),
                'experience_level': experience or snapshot.get('experience', ''),
                'employment_type': employee_type or snapshot.get('employee_type', ''),
                'description': jd_text,
                'department': snapshot.get('department', ''),
                'posted_date': self._format_date(snapshot.get('updated_date', '')),
                'job_id': snapshot.get('job_id', ''),
            }

        except Exception as exc:
            logger.debug(f"Failed detail scrape for {job_url}: {str(exc)}")
        finally:
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(original_window)
            except Exception:
                pass

        return details

    def _extract_snapshot_fields(self, driver):
        result = {
            'updated_date': '',
            'job_id': '',
            'department': '',
            'location': '',
            'experience': '',
            'employee_type': '',
        }

        items = driver.find_elements(By.CSS_SELECTOR, 'div.grid-container .grid-item')
        for item in items:
            try:
                label = (item.find_element(By.CSS_SELECTOR, '.label').text or '').strip().lower()
                value = (item.find_element(By.CSS_SELECTOR, '.value, span.value').text or '').strip()
                if not label or not value:
                    continue
                if label == 'updated date':
                    result['updated_date'] = value
                elif label == 'job id':
                    result['job_id'] = value
                elif label == 'department':
                    result['department'] = value
                elif label == 'location':
                    result['location'] = value
                elif label == 'experience':
                    result['experience'] = value
                elif label == 'employee type':
                    result['employee_type'] = value
            except Exception:
                continue
        return result

    def _merge_job_details(self, job, details):
        if not details:
            return

        if details.get('title') and self._is_valid_title(details['title']):
            job['title'] = details['title']

        if details.get('description'):
            job['description'] = details['description'][:6000]

        if details.get('department'):
            job['department'] = details['department']

        if details.get('employment_type'):
            job['employment_type'] = details['employment_type']

        if details.get('experience_level'):
            job['experience_level'] = details['experience_level']

        if details.get('posted_date'):
            job['posted_date'] = details['posted_date']

        location = details.get('location') or job.get('location', '')
        if location:
            job['location'] = location
            city, state, country = self.parse_location(location)
            job['city'] = city
            job['state'] = state
            job['country'] = country or 'India'

        detail_job_id = details.get('job_id', '')
        if detail_job_id:
            job['external_id'] = self.generate_external_id(detail_job_id, self.company_name)

    def _safe_text(self, driver, by, selector):
        try:
            return (driver.find_element(by, selector).text or '').strip()
        except Exception:
            return ''

    def _clean_description(self, text):
        if not text:
            return ''
        cleaned = text.replace('\r', '\n')
        cleaned = re.sub(r'Please\s+enter\s+job\s+descript(?:ion)?', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def _is_valid_title(self, title):
        if not title:
            return False
        lowered = title.strip().lower()
        if len(lowered) < 3 or len(lowered) > 180:
            return False
        blocked = {
            'open jobs', 'filters', 'location', 'department', 'experience',
            'employee type', 'country', 'job tag', 'load more jobs', 'view similar jobs'
        }
        return lowered not in blocked

    def _is_india_location(self, location_text):
        if not location_text:
            return True
        text = location_text.lower()
        if 'indiana' in text:
            return False
        return any(keyword in text for keyword in self.india_keywords)

    def _format_date(self, date_text):
        if not date_text:
            return ''
        date_text = date_text.strip()
        for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_text, fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return ''

    def parse_location(self, location_str):
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',') if p.strip()]
        city = ''
        state = ''
        country = 'India'

        if len(parts) >= 1:
            city = parts[-3] if len(parts) >= 3 else parts[0]
        if len(parts) >= 2:
            state = parts[-2]
        if len(parts) >= 3:
            country = parts[-1]
            if country.upper() == 'IN':
                country = 'India'

        if not country:
            country = 'India'

        return city, state, country
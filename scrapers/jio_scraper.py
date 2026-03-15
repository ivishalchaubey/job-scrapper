import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import hashlib
from datetime import datetime

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('jio_scraper')


class JioScraper:
    def __init__(self):
        self.company_name = "Jio"
        self.base_url = "https://careers.jio.com"
        self.url = "https://careers.jio.com/frmJobCategories.aspx?func=w+cpdiT6wL4=&loc=/wASbQn4xyQ=&expreq=/wASbQn4xyQ=&flag=/wASbQn4xyQ=&poston=6JCGsKeGvVZx6Lxy4pI54VzntXOmB1aj"

    def setup_driver(self):
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape all Jio jobs across all categories, up to max_pages per category."""
        all_jobs = []
        driver = None
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            categories = self._get_categories(driver)
            logger.info(f"Found {len(categories)} categories")

            for cat_name, cat_url in categories:
                logger.info(f"Scraping category: {cat_name}")
                try:
                    cat_jobs = self._scrape_category(driver, cat_name, cat_url, max_pages)
                    logger.info(f"  {len(cat_jobs)} jobs in '{cat_name}'")
                    all_jobs.extend(cat_jobs)
                except Exception as e:
                    logger.error(f"  Error in category '{cat_name}': {e}")
                    continue

            logger.info(f"Total: {len(all_jobs)} jobs scraped from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _get_categories(self, driver):
        """Get all category names and URLs from the main categories page."""
        driver.get(self.url)
        wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.category-list li.list-cont a')))

        categories = []
        items = driver.find_elements(By.CSS_SELECTOR, 'ul.category-list li.list-cont')
        for item in items:
            try:
                link = item.find_element(By.TAG_NAME, 'a')
                href = link.get_attribute('href') or ''
                if not href:
                    continue
                try:
                    name = item.find_element(By.CSS_SELECTOR, 'span[id*="lblfunctional"]').text.strip()
                except Exception:
                    name = link.text.strip().split('\n')[0].strip()
                if name and href:
                    categories.append((name, href))
            except Exception as e:
                logger.warning(f"Error reading category item: {e}")
        return categories

    def _scrape_category(self, driver, cat_name, cat_url, max_pages):
        """Scrape jobs from a category page, paginating up to max_pages."""
        jobs = []
        driver.get(cat_url)
        wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article')))
        except Exception:
            logger.warning(f"No article element found for '{cat_name}'")
            return jobs

        for page_num in range(1, max_pages + 1):
            page_jobs = self._extract_page_jobs(driver, wait)
            logger.info(f"  Page {page_num}: {len(page_jobs)} jobs")

            for job_data in page_jobs:
                if FETCH_FULL_JOB_DETAILS and job_data.get('apply_url'):
                    details = self._fetch_job_details(driver, job_data['apply_url'])
                    for key, value in details.items():
                        if value:
                            job_data[key] = value
                jobs.append(job_data)

            if page_num >= max_pages:
                break
            if not self._go_to_next_page(driver, wait):
                logger.info(f"  No more pages for '{cat_name}' (stopped at page {page_num})")
                break

        return jobs

    def _extract_page_jobs(self, driver, wait):
        """Extract all job entries visible on the current listing page."""
        jobs = []
        try:
            job_links = driver.find_elements(
                By.CSS_SELECTOR,
                'article h2 a[id*="MainContent_lstJoblist_hylUser"]'
            )
            for idx, link in enumerate(job_links):
                try:
                    title = link.text.strip()
                    href = link.get_attribute('href') or ''
                    if not title or not href or len(title) < 3:
                        continue

                    job_id = self._extract_job_id(href, title)
                    location = ''
                    posted_date = ''
                    job_function = ''

                    try:
                        loc_span = driver.find_element(
                            By.CSS_SELECTOR, f'span[id="MainContent_lstJoblist_Label2_{idx}"]'
                        )
                        location = loc_span.text.strip()
                    except Exception:
                        pass

                    try:
                        date_span = driver.find_element(
                            By.CSS_SELECTOR, f'span[id="MainContent_lstJoblist_Label1_{idx}"]'
                        )
                        posted_date = self._parse_date(date_span.text.strip())
                    except Exception:
                        pass

                    try:
                        func_span = driver.find_element(
                            By.CSS_SELECTOR, f'span[id="MainContent_lstJoblist_lblfunctional_{idx}"]'
                        )
                        job_function = func_span.text.strip()
                    except Exception:
                        pass

                    loc = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc['city'],
                        'state': loc['state'],
                        'country': 'India',
                        'employment_type': '',
                        'department': job_function,
                        'apply_url': href,
                        'posted_date': posted_date,
                        'job_function': job_function,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error extracting job at index {idx}: {e}")
        except Exception as e:
            logger.error(f"Error finding job links on page: {e}")
        return jobs

    def _go_to_next_page(self, driver, wait):
        """Click the Next button and wait for the page content to reload."""
        try:
            next_btn = driver.find_element(
                By.CSS_SELECTOR, 'input[id*="DataPager1_ctl00_lnkNext"]'
            )
            if not next_btn.is_enabled():
                return False
            if next_btn.get_attribute('disabled'):
                return False

            old_article = driver.find_element(By.CSS_SELECTOR, 'article')
            next_btn.click()
            WebDriverWait(driver, 15).until(EC.staleness_of(old_article))
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'article'))
            )
            return True
        except Exception as e:
            logger.warning(f"Could not navigate to next page: {e}")
            return False

    def _extract_job_id(self, href, title):
        """Extract stable job ID from jbID URL param or numeric title ID."""
        m = re.search(r'jbID=([^&]+)', href)
        if m:
            return m.group(1)
        m = re.search(r'\(\s*(\d{6,})\s*\)', title)
        if m:
            return m.group(1)
        return hashlib.md5(href.encode()).hexdigest()[:12]

    def _parse_date(self, date_str):
        """Parse '14 Mar 2026' → '2026-03-14'."""
        if not date_str:
            return ''
        try:
            return datetime.strptime(date_str.strip(), '%d %b %Y').strftime('%Y-%m-%d')
        except Exception:
            return ''

    def _fetch_job_details(self, driver, job_url):
        """Fetch extra details from the job description page in a new tab."""
        details = {}
        original_handle = driver.current_window_handle
        try:
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(job_url)
            WebDriverWait(driver, SCRAPE_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.job-details'))
            )

            desc_parts = []
            for span_id, label in [
                ('MainContent_lblSummRole', 'Job Responsibilities'),
                ('MainContent_lblSkill', 'Skills & Competencies'),
            ]:
                try:
                    text = driver.find_element(By.CSS_SELECTOR, f'span#{span_id}').text.strip()
                    if text:
                        desc_parts.append(f"{label}:\n{text}")
                except Exception:
                    pass
            if desc_parts:
                details['description'] = '\n\n'.join(desc_parts)[:5000]

            try:
                exp = driver.find_element(By.CSS_SELECTOR, 'span#MainContent_lblExpReq').text.strip()
                if exp:
                    details['experience_level'] = exp[:200]
            except Exception:
                pass

            try:
                func = driver.find_element(By.CSS_SELECTOR, 'span#MainContent_lblSec').text.strip()
                if func:
                    details['job_function'] = func
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error fetching details from {job_url}: {e}")
        finally:
            try:
                driver.close()
                driver.switch_to.window(original_handle)
            except Exception:
                try:
                    driver.switch_to.window(driver.window_handles[0])
                except Exception:
                    pass
        return details

    def parse_location(self, location_str):
        """Parse Jio location string into city/state/country dict.

        Examples: 'Hyderabad 13 - Sarojini Devi Road', 'Bhopal 1 - Kolar Road', 'Navsari'
        """
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        # Take the part before ' - ' as the city base, then strip trailing number
        city_part = location_str.split(' - ')[0].strip()
        city = re.sub(r'\s+\d+\s*$', '', city_part).strip()
        result['city'] = city
        return result

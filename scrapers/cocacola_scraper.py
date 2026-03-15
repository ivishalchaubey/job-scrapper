import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import hashlib
from datetime import datetime

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger("cocacola_scraper")


class CocaColaScraper:
    def __init__(self):
        self.company_name = "The Coca-Cola Company"
        self.base_url = "https://careers.coca-colacompany.com"
        self.url = "https://careers.coca-colacompany.com/?store_id=India"

    def setup_driver(self):
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        driver = None
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div#widget-jobsearch-results-list div[role="row"].job')
            ))
            for page_num in range(1, max_pages + 1):
                logger.info(f"Scraping page {page_num}")
                page_jobs = self._extract_page_jobs(driver)
                logger.info(f"  Page {page_num}: {len(page_jobs)} jobs")
                for job_data in page_jobs:
                    if FETCH_FULL_JOB_DETAILS and job_data.get("apply_url") != self.url:
                        details = self._fetch_job_details(driver, job_data["apply_url"])
                        for key, value in details.items():
                            if value:
                                job_data[key] = value
                    all_jobs.append(job_data)
                if page_num >= max_pages:
                    break
                if not self._go_to_next_page(driver, wait):
                    logger.info(f"No more pages after page {page_num}")
                    break
            logger.info(f"Total: {len(all_jobs)} jobs scraped from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_page_jobs(self, driver):
        jobs = []
        try:
            rows = driver.find_elements(
                By.CSS_SELECTOR,
                'div#widget-jobsearch-results-list div[role="row"].job'
            )
            for row in rows:
                try:
                    title_link = row.find_element(By.CSS_SELECTOR, "div.jobTitle a")
                    title = title_link.text.strip()
                    href = title_link.get_attribute("href") or ""
                    if not title or not href:
                        continue
                    if href.startswith("/"):
                        href = self.base_url + href
                    row_classes = row.get_attribute("class") or ""
                    import re as _re
                    m = _re.search(r"jobid-(\d+)", row_classes)
                    if m:
                        job_id = m.group(1)
                    else:
                        m2 = _re.search(r"/job/(\d+)/", href)
                        job_id = m2.group(1) if m2 else hashlib.md5(href.encode()).hexdigest()[:12]
                    cells = row.find_elements(By.CSS_SELECTOR, 'div.job-innerwrap div[role="cell"]')
                    city = cells[1].text.strip() if len(cells) > 1 else ""
                    country = cells[2].text.strip() if len(cells) > 2 else "India"
                    location = f"{city}, {country}" if city else country
                    jobs.append({
                        "external_id": self.generate_external_id(job_id, self.company_name),
                        "company_name": self.company_name,
                        "title": title,
                        "description": "",
                        "location": location,
                        "city": city,
                        "state": "",
                        "country": country or "India",
                        "employment_type": "",
                        "department": "",
                        "apply_url": href,
                        "posted_date": "",
                        "job_function": "",
                        "experience_level": "",
                        "salary_range": "",
                        "remote_type": "",
                        "status": "active"
                    })
                except Exception as e:
                    logger.error(f"Error extracting job row: {e}")
        except Exception as e:
            logger.error(f"Error finding job rows: {e}")
        return jobs

    def _go_to_next_page(self, driver, wait):
        try:
            items = driver.find_elements(
                By.CSS_SELECTOR, "nav#widget-jobsearch-results-pages ul.pagination-ul li"
            )
            if not items:
                return False
            next_link = None
            for li in items:
                try:
                    a = li.find_element(By.TAG_NAME, "a")
                    label = (a.get_attribute("aria-label") or "").lower()
                    cls = (li.get_attribute("class") or "").lower()
                    if "next" in label or "next" in cls:
                        next_link = a
                        break
                except Exception:
                    continue
            if not next_link:
                return False
            first_row = driver.find_element(
                By.CSS_SELECTOR, 'div#widget-jobsearch-results-list div[role="row"].job'
            )
            next_link.click()
            WebDriverWait(driver, 15).until(EC.staleness_of(first_row))
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div#widget-jobsearch-results-list div[role="row"].job')
            ))
            return True
        except Exception as e:
            logger.warning(f"Could not navigate to next page: {e}")
            return False

    def _fetch_job_details(self, driver, job_url):
        details = {}
        original_handle = driver.current_window_handle
        try:
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(job_url)
            WebDriverWait(driver, SCRAPE_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.job_info"))
            )
            for info_div in driver.find_elements(By.CSS_SELECTOR, "div.job_info"):
                try:
                    text = info_div.text.strip()
                    if text.startswith("Job Type:"):
                        val = text.replace("Job Type:", "").strip().lower()
                        if "full" in val:
                            details["employment_type"] = "Full Time"
                        elif "part" in val:
                            details["employment_type"] = "Part Time"
                        elif "intern" in val:
                            details["employment_type"] = "Intern"
                        elif "contract" in val:
                            details["employment_type"] = "Contract"
                    elif text.startswith("Post Date:"):
                        details["posted_date"] = self._parse_date(text.replace("Post Date:", "").strip())
                    elif text.startswith("Location:"):
                        loc_str = text.replace("Location:", "").strip()
                        loc = self.parse_location(loc_str)
                        details["location"] = loc_str
                        details["city"] = loc["city"]
                        details["state"] = loc["state"]
                        details["country"] = loc["country"]
                except Exception:
                    pass
            try:
                text_parts = []
                for td in driver.find_elements(By.CSS_SELECTOR, "div.jd_data div.fusion-text"):
                    cls = td.get_attribute("class") or ""
                    if "apply_top" in cls or "apply_bottom" in cls:
                        continue
                    t = td.text.strip()
                    if t:
                        text_parts.append(t)
                if len(text_parts) > 1:
                    details["description"] = "\n\n".join(text_parts[1:])[:5000]
            except Exception:
                pass
            try:
                apply_btn = driver.find_element(By.CSS_SELECTOR, "a.job_apply_btn")
                apply_href = apply_btn.get_attribute("href") or ""
                if apply_href:
                    details["apply_url"] = apply_href
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

    def _parse_date(self, date_str):
        if not date_str:
            return ""
        try:
            return datetime.strptime(date_str.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
        except Exception:
            return ""

    def parse_location(self, location_str):
        result = {"city": "", "state": "", "country": "India"}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(",")]
        result["city"] = parts[0] if parts else ""
        if len(parts) == 2:
            result["country"] = parts[1]
        elif len(parts) >= 3:
            result["state"] = parts[1]
            result["country"] = parts[-1]
        return result

import hashlib
import re
import time
from datetime import datetime, timedelta

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger("zepto_scraper")

# TalentRecruit embeds an appcareer iframe on both the listing page and each detail page.
_IFRAME_SEL = "iframe[src*='appcareer.talentrecruit.com']"
# Material-icon text nodes that appear in body text and must be ignored.
_ICON_NAMES = {"place", "work", "watch_later", "star", "group", "location_on", "access_time", "business"}


class ZeptoScraper:
    def __init__(self):
        self.company_name = "Zepto"
        self.url = "https://zepto.talentrecruit.com/career-page"

    def setup_driver(self):
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        return hashlib.md5(f"{company}_{job_id}".encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        driver = None
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)

            # Count jobs from the listing iframe
            driver.get(self.url)
            iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _IFRAME_SEL)))
            driver.switch_to.frame(iframe)
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//button[contains(., 'View Details')]")
            ))
            num_jobs = len(driver.find_elements(By.XPATH, "//button[contains(., 'View Details')]"))
            driver.switch_to.default_content()
            logger.info(f"Found {num_jobs} jobs on listing page")

            for idx in range(num_jobs):
                try:
                    job_data = self._scrape_one_job(driver, wait, idx)
                    if job_data:
                        jobs.append(job_data)
                        logger.info(f"Scraped: {job_data['title']} | {job_data.get('location', '')}")
                except Exception as e:
                    logger.debug(f"Job index {idx} failed: {e}")
                    try:
                        driver.switch_to.default_content()
                    except Exception:
                        pass

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return jobs

    def _scrape_one_job(self, driver, wait, idx):
        """Load listing, click View Details for job at idx, parse detail."""
        driver.get(self.url)
        iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _IFRAME_SEL)))
        driver.switch_to.frame(iframe)
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//button[contains(., 'View Details')]")
        ))

        # Grab listing-level title as fallback
        listing_title = ""
        title_nodes = driver.find_elements(By.CSS_SELECTOR, ".job-title")
        if idx < len(title_nodes):
            listing_title = title_nodes[idx].text.strip()

        buttons = driver.find_elements(By.XPATH, "//button[contains(., 'View Details')]")
        if idx >= len(buttons):
            return None
        driver.execute_script("arguments[0].click();", buttons[idx])

        # Click triggers Angular routing at the top-level page
        driver.switch_to.default_content()
        wait.until(lambda d: "/career-page/apply/" in d.current_url)
        apply_url = driver.current_url

        # Detail page also embeds an appcareer iframe - wait for it (Angular renders async)
        detail_iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _IFRAME_SEL)))
        driver.switch_to.frame(detail_iframe)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "section.apply-sec")))

        sec_text = driver.find_element(By.CSS_SELECTOR, "section.apply-sec").text
        parsed = self._parse_apply_sec_text(sec_text)
        driver.switch_to.default_content()

        title = parsed.get("title") or listing_title
        if not self._is_valid_title(title):
            return None

        loc = self.parse_location(parsed.get("location", ""))
        ext_id = parsed.get("job_id") or hashlib.md5(apply_url.encode()).hexdigest()[:12]

        return {
            "external_id": self.generate_external_id(ext_id, self.company_name),
            "company_name": self.company_name,
            "title": title,
            "description": parsed.get("description", "")[:6000],
            "location": parsed.get("location", ""),
            "city": loc["city"],
            "state": loc["state"],
            "country": "India",
            "employment_type": self._normalize_employment_type(
                parsed.get("job_nature") or parsed.get("job_type", "")
            ),
            "department": "",
            "apply_url": apply_url,
            "posted_date": self._parse_posted_date(parsed.get("posted_text", "")),
            "job_function": "",
            "experience_level": parsed.get("experience", ""),
            "salary_range": "",
            "remote_type": parsed.get("remote_type", ""),
            "status": "active",
        }

    def _parse_apply_sec_text(self, body_text):
        """
        Parse TalentRecruit apply-sec body text into structured fields.

        The section body (newline-separated) looks like:
          Apply for Job
          Intern - Design          <- title (first real content line)
          ID 10194
          Posted 13 Days ago
          place                    <- material icon name (ignored)
          Job Location
          Bengaluru
          (Work From Office)
          work
          Job Type
          Permanent
          watch_later
          Job Nature
          Intern
          star
          Experience
          0.00 to 1.00 Years
          Apply for Job
          Job Description
          <description text>
          Skills
          Skill1 ...
        """
        result = {
            "title": "", "job_id": "", "posted_text": "",
            "location": "", "job_type": "", "job_nature": "",
            "experience": "", "description": "", "remote_type": "",
        }
        if not body_text:
            return result

        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        # Remove Material icon names and navigation text
        content = [
            l for l in lines
            if l.lower() not in _ICON_NAMES and l.lower() != "apply for job"
        ]

        if not content:
            return result

        # First content line is the job title
        result["title"] = content[0]

        # Job ID
        for line in content:
            m = re.match(r"^ID\s+(\d+)", line, re.IGNORECASE)
            if m:
                result["job_id"] = m.group(1)
                break

        # Posted date
        for line in content:
            if re.search(r"posted", line, re.IGNORECASE):
                result["posted_text"] = line
                break

        # Field pairs (label line  value line)
        i = 0
        while i < len(content):
            lower = content[i].lower()

            if lower == "job location" and i + 1 < len(content):
                result["location"] = content[i + 1]
                i += 1
                # Optional work-mode note in parentheses on next line
                if i + 1 < len(content) and content[i + 1].startswith("("):
                    note = content[i + 1].lower()
                    if "work from office" in note or "wfo" in note:
                        result["remote_type"] = "On-site"
                    elif "remote" in note:
                        result["remote_type"] = "Remote"
                    elif "hybrid" in note:
                        result["remote_type"] = "Hybrid"
                    i += 1

            elif lower == "job type" and i + 1 < len(content):
                result["job_type"] = content[i + 1]
                i += 1

            elif lower == "job nature" and i + 1 < len(content):
                result["job_nature"] = content[i + 1]
                i += 1

            elif lower == "experience" and i + 1 < len(content):
                result["experience"] = content[i + 1]
                i += 1

            elif lower == "job description":
                desc_lines = []
                j = i + 1
                while j < len(content) and content[j].lower() not in ("skills", "skill"):
                    desc_lines.append(content[j])
                    j += 1
                result["description"] = "\n".join(desc_lines).strip()
                i = j
                continue

            i += 1

        return result

    def _normalize_employment_type(self, raw):
        raw = (raw or "").lower()
        if "intern" in raw:
            return "Intern"
        if "contract" in raw:
            return "Contract"
        if "part" in raw:
            return "Part Time"
        if "full" in raw or "permanent" in raw:
            return "Full Time"
        return ""

    def _is_valid_title(self, title):
        if not title or len(title) < 3 or len(title) > 200:
            return False
        skip = [
            "items per page", "search jobs", "reset filter", "home",
            "about", "contact", "apply for job", "login", "sign in",
        ]
        return not any(s in title.lower() for s in skip)

    def _parse_posted_date(self, text):
        if not text:
            return ""
        text = text.lower()
        if "today" in text:
            return datetime.utcnow().strftime("%Y-%m-%d")
        m = re.search(r"(\d+)\s+day", text)
        if m:
            return (datetime.utcnow() - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
        return ""

    def parse_location(self, location_str):
        result = {"city": "", "state": "", "country": "India"}
        if not location_str:
            return result
        clean = re.sub(r"\(.*?\)", "", location_str).strip()
        parts = [p.strip() for p in clean.split(",")]
        if parts:
            result["city"] = parts[0]
        if len(parts) > 1:
            result["state"] = parts[1]
        return result

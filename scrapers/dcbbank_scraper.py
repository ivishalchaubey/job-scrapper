from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('dcbbank_scraper')

class DCBBankScraper:
    def __init__(self):
        self.company_name = "DCB Bank"
        # DCB Bank migrated from genesis.dcbbank.com (Zwayam) to ZingHR.
        # The old Zwayam portal has a persistent SSL protocol error.
        # The new careers portal is hosted on ZingHR:
        self.url = "https://zingnext.zinghr.com/portal/embed/career-website?CareerClientKey=ASDFQ-BAHDV-QWERM"
        # Fallback: the old URL in case SSL is fixed
        self.legacy_url = 'https://genesis.dcbbank.com/#!/joblist'
        self.company_careers_url = 'https://www.dcb.bank.in/careers'
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from DCB Bank's ZingHR careers portal (Next.js SPA)."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Try ZingHR portal first (new platform)
            logger.info(f"Navigating to ZingHR portal: {self.url}")
            driver.get(self.url)

            # ZingHR is a Next.js SPA -- wait for it to render job cards
            logger.info("Waiting for ZingHR SPA to render job listings...")
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        '[class*="MuiPaper-outlined"], [class*="MuiTypography-subtitle1"], '
                        '[class*="job-listing"], [class*="MuiCard"]'
                    ))
                )
                logger.info("Job listing elements detected")
            except Exception:
                logger.info("Timed out waiting for specific selectors, waiting additional time...")
                time.sleep(10)

            # Additional wait for dynamic content loading
            time.sleep(5)

            # Scroll to trigger any lazy loading
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try to click all job cards to load pagination
            page_count = 0
            while page_count < max_pages:
                try:
                    # ZingHR uses MUI Pagination component
                    next_buttons = driver.find_elements(By.CSS_SELECTOR,
                        'button[aria-label="Go to next page"], '
                        'li.MuiPaginationItem-page + li button, '
                        'button:has(svg[data-testid="NavigateNextIcon"])'
                    )
                    if next_buttons:
                        next_btn = next_buttons[0]
                        if next_btn.is_enabled():
                            driver.execute_script("arguments[0].click();", next_btn)
                            logger.info("Clicked pagination next button")
                            time.sleep(3)
                            page_count += 1
                        else:
                            break
                    else:
                        break
                except Exception:
                    break

            # Extract jobs from the rendered DOM
            jobs = self._extract_jobs_zinghr(driver)

            # If ZingHR returned no jobs, try legacy Zwayam URL as fallback
            if not jobs:
                logger.warning("No jobs found on ZingHR, trying legacy Zwayam URL")
                try:
                    driver.get(self.legacy_url)
                    time.sleep(10)
                    for i in range(3):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(2)
                    jobs = self._extract_jobs_zwayam(driver)
                except Exception as e:
                    logger.warning(f"Legacy Zwayam URL also failed: {str(e)}")

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs_zinghr(self, driver):
        """Extract jobs from ZingHR Next.js career website.

        The ZingHR portal renders job cards using Material-UI components.
        Each card shows: job title, career attributes (tags), and possibly
        location/department info. Clicking a card shows the full description
        in a side panel.
        """
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // ZingHR uses MUI Paper cards with outlined variant for job listings.
                // Structure: MuiPaper-outlined > H6.MuiTypography-subtitle1 (title)
                // Each card sits inside MuiGrid-item with sm-3 or sm-6 sizing.
                // We look for MuiPaper-outlined cards that contain an H6 title.
                var cards = document.querySelectorAll(
                    '[class*="MuiPaper-outlined"]'
                );

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var titleEl = card.querySelector(
                        'h6[class*="MuiTypography-subtitle1"], h6, h5'
                    );
                    if (!titleEl) continue;

                    var title = titleEl.innerText.trim();
                    if (!title || title.length < 3) continue;

                    // Extract metadata from the card text
                    var cardText = card.innerText;
                    var location = '';
                    var posType = '';
                    var postedDate = '';
                    var experience = '';

                    // Position Type
                    var posMatch = cardText.match(/Position Type:\\s*(.+)/i);
                    if (posMatch) posType = posMatch[1].trim();

                    // Posted date
                    var dateMatch = cardText.match(/Posted on\\s+(.+)/i);
                    if (dateMatch) postedDate = dateMatch[1].trim();

                    // Experience
                    var expMatch = cardText.match(/(\\d+\\s*-\\s*\\d+\\s*Years?)/i);
                    if (expMatch) experience = expMatch[1].trim();

                    // Location - look for Location: or Designation: lines
                    var locMatch = cardText.match(/Location:\\s*(.+)/i);
                    if (locMatch) location = locMatch[1].trim().split('\\n')[0];

                    if (!seen[title]) {
                        seen[title] = true;
                        results.push({
                            title: title,
                            href: '',
                            location: location,
                            department: '',
                            experience: experience,
                            positionType: posType,
                            postedDate: postedDate
                        });
                    }
                }

                // Fallback: find H6 elements with MuiTypography-subtitle1 class
                if (results.length === 0) {
                    var headings = document.querySelectorAll(
                        'h6[class*="MuiTypography-subtitle1"]'
                    );
                    for (var i = 0; i < headings.length; i++) {
                        var title = headings[i].innerText.trim();
                        if (title.length > 3 && !seen[title]) {
                            seen[title] = true;
                            results.push({
                                title: title, href: '', location: '',
                                department: '', experience: '',
                                positionType: '', postedDate: ''
                            });
                        }
                    }
                }

                return results;
            """)

            if job_data:
                logger.info(f"ZingHR JS extraction found {len(job_data)} jobs")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '')
                    location = jd.get('location', '')
                    experience = jd.get('experience', '')
                    pos_type = jd.get('positionType', '')
                    posted_date = jd.get('postedDate', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': pos_type,
                        'department': '',
                        'apply_url': self.url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found on ZingHR page")

        except Exception as e:
            logger.error(f"ZingHR JS extraction failed: {e}")

        return jobs

    def _extract_jobs_zwayam(self, driver):
        """Fallback: Extract jobs from legacy Zwayam AngularJS page."""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Zwayam-specific selectors
                var selectors = [
                    '.job-card', '.job-item', '[class*="job-card"]',
                    '[class*="job-item"]', 'div[ng-repeat]', 'tr[ng-repeat]',
                    'li[ng-repeat]', '.ng-scope[class*="job"]'
                ];

                for (var s = 0; s < selectors.length; s++) {
                    var cards = document.querySelectorAll(selectors[s]);
                    if (cards.length > 0) {
                        for (var i = 0; i < cards.length; i++) {
                            var card = cards[i];
                            var title = '';
                            var href = '';
                            var location = '';
                            var department = '';

                            var heading = card.querySelector('h1, h2, h3, h4, h5, a[href*="job"], a[href*="#!/"]');
                            if (heading) {
                                title = heading.innerText.trim().split('\\n')[0].trim();
                                if (heading.tagName === 'A') href = heading.href;
                            }
                            if (!title) {
                                var firstLink = card.querySelector('a');
                                if (firstLink) {
                                    title = firstLink.innerText.trim().split('\\n')[0].trim();
                                    href = firstLink.href;
                                }
                            }

                            var locEl = card.querySelector('[class*="location"]');
                            if (locEl) location = locEl.innerText.trim();

                            var deptEl = card.querySelector('[class*="department"]');
                            if (deptEl) department = deptEl.innerText.trim();

                            if (title && title.length > 2 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({
                                    title: title, href: href,
                                    location: location, department: department
                                });
                            }
                        }
                        if (results.length > 0) break;
                    }
                }

                return results;
            """)

            if job_data:
                logger.info(f"Zwayam extraction found {len(job_data)} jobs")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '')
                    href = jd.get('href', '')
                    location = jd.get('location', '')
                    department = jd.get('department', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5((href or f"{title}_{idx}").encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': department,
                        'apply_url': href if href else self.legacy_url,
                        'posted_date': '',
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

        except Exception as e:
            logger.error(f"Zwayam extraction failed: {e}")

        return jobs

if __name__ == "__main__":
    scraper = DCBBankScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

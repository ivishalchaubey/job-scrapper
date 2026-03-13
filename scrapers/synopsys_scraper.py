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

logger = setup_logger('synopsys_scraper')

class SynopsysScraper:
    def __init__(self):
        self.company_name = "Synopsys"
        self.url = "https://careers.synopsys.com/search-jobs"
        self.fallback_url = 'https://synopsys.avature.net/careers/SearchJobs'
    
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

    def _is_india_job(self, location, title=''):
        """Check if a job is India-based."""
        india_keywords = [
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi', 'hyderabad',
            'chennai', 'pune', 'kolkata', 'gurgaon', 'gurugram', 'noida',
            'ahmedabad', 'new delhi', 'goa'
        ]
        text = (location + ' ' + title).lower()
        return any(kw in text for kw in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Synopsys (Phenom People + Avature SPA)."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Try primary URL with India filter
            india_url = self.url + '?country=India'
            driver.get(india_url)
            time.sleep(12)

            # Wait for Phenom People React SPA to render
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        '[data-ph-at-id], .job-tile, .search-result-item, [class*="job-card"], [class*="search-result"], a[href*="/job/"]'))
                )
            except Exception:
                logger.warning("Timeout on primary URL, trying base URL")
                driver.get(self.url)
                time.sleep(12)

            # Try to apply India location filter via UI
            try:
                # Look for location/country filter dropdown
                filters = driver.find_elements(By.XPATH,
                    '//select[contains(@name,"country") or contains(@id,"country") or contains(@name,"location")]'
                    ' | //button[contains(text(),"Location") or contains(text(),"Country")]'
                    ' | //div[contains(@class,"filter") and (contains(text(),"Location") or contains(text(),"Country"))]')
                if filters:
                    driver.execute_script("arguments[0].click();", filters[0])
                    time.sleep(2)
                    india_option = driver.find_elements(By.XPATH,
                        '//option[contains(text(),"India")]'
                        ' | //li[contains(text(),"India")]'
                        ' | //label[contains(text(),"India")]'
                        ' | //a[contains(text(),"India")]')
                    if india_option:
                        driver.execute_script("arguments[0].click();", india_option[0])
                        logger.info("Applied India location filter")
                        time.sleep(5)
            except Exception:
                logger.info("Could not apply location filter, will filter results manually")

            # Scroll to trigger lazy loading
            for i in range(8):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Paginate
            all_jobs = []
            for page in range(max_pages):
                page_jobs = self._extract_jobs_js(driver)
                if not page_jobs:
                    break
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if not self._go_to_next_page(driver):
                    break
                time.sleep(5)

            jobs = all_jobs

            # If no jobs found, try fallback Avature URL
            if not jobs:
                logger.info("No jobs from primary URL, trying Avature fallback")
                driver.get(self.fallback_url)
                time.sleep(12)
                for i in range(5):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                jobs = self._extract_jobs_js(driver)

            logger.info(f"Successfully scraped {len(jobs)} India jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs_js(self, driver):
        """Extract jobs from Phenom/Avature SPA using JavaScript."""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Phenom People specific selectors
                var phenomCards = document.querySelectorAll('[data-ph-at-id*="job"], [data-ph-id*="job"], .job-tile, .job-card, .search-result-item');
                if (phenomCards.length > 0) {
                    for (var i = 0; i < phenomCards.length; i++) {
                        var card = phenomCards[i];
                        var title = '';
                        var href = '';
                        var location = '';
                        var department = '';
                        var date = '';

                        var titleEl = card.querySelector('[data-ph-at-id*="title"], [data-ph-id*="title"], h2, h3, .job-title, [class*="job-title"], [class*="jobTitle"]');
                        if (titleEl) title = titleEl.innerText.trim().split('\\n')[0].trim();

                        var linkEl = card.querySelector('a[href*="/job/"], a[href*="/requisition"], a[href]');
                        if (linkEl) href = linkEl.href;
                        if (!title && linkEl) title = linkEl.innerText.trim().split('\\n')[0].trim();

                        var locEl = card.querySelector('[data-ph-at-id*="location"], [class*="location"], [class*="Location"]');
                        if (locEl) location = locEl.innerText.trim();

                        var deptEl = card.querySelector('[data-ph-at-id*="department"], [data-ph-at-id*="category"], [class*="department"], [class*="category"]');
                        if (deptEl) department = deptEl.innerText.trim();

                        var dateEl = card.querySelector('[data-ph-at-id*="date"], [class*="date"], [class*="posted"]');
                        if (dateEl) date = dateEl.innerText.trim();

                        if (title && title.length > 2 && !seen[title + href]) {
                            seen[title + href] = true;
                            results.push({title: title, href: href, location: location, department: department, date: date});
                        }
                    }
                }

                // Strategy 2: Avature-specific selectors
                if (results.length === 0) {
                    var avatureCards = document.querySelectorAll('[class*="search-result"], [class*="SearchResult"], [class*="job-result"], [class*="jobResult"]');
                    if (!avatureCards.length) {
                        avatureCards = document.querySelectorAll('div[class*="job-card"], div[class*="jobCard"], div[class*="job-listing"], li[class*="job"]');
                    }
                    for (var i = 0; i < avatureCards.length; i++) {
                        var card = avatureCards[i];
                        var heading = card.querySelector('h2, h3, h4, a[href*="/job"], a[href*="Job"], [class*="title"]');
                        var title = heading ? heading.innerText.trim().split('\\n')[0].trim() : '';
                        var href = '';
                        if (heading && heading.tagName === 'A') href = heading.href;
                        if (!href) {
                            var link = card.querySelector('a[href]');
                            if (link) href = link.href;
                        }
                        var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                        var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                        var dateEl = card.querySelector('[class*="date"], [class*="posted"]');
                        if (title && title.length > 2 && !seen[title + href]) {
                            seen[title + href] = true;
                            results.push({
                                title: title,
                                href: href,
                                location: locEl ? locEl.innerText.trim() : '',
                                department: deptEl ? deptEl.innerText.trim() : '',
                                date: dateEl ? dateEl.innerText.trim() : ''
                            });
                        }
                    }
                }

                // Strategy 3: Taleo-style table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('tr.data-row, tr.dataRow, table tbody tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        var titleLink = row.querySelector('a.jobTitle-link, a[href*="/job/"], a[href*="/requisition"]');
                        if (!titleLink) {
                            var firstLink = row.querySelector('a[href]');
                            if (firstLink) titleLink = firstLink;
                        }
                        if (!titleLink) continue;
                        var title = titleLink.innerText.trim();
                        var url = titleLink.href || '';
                        if (!title || title.length < 3 || seen[url || title]) continue;
                        seen[url || title] = true;
                        var location = '';
                        var locTd = row.querySelector('td[class*="location"], [class*="Location"]');
                        if (locTd) location = locTd.innerText.trim();
                        results.push({title: title, href: url, location: location, department: '', date: ''});
                    }
                }

                // Strategy 4: Generic links with job-related hrefs
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/job/"], a[href*="/requisition"], a[href*="SearchJobs"], a[href*="/position"]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim().split('\\n')[0].trim();
                        var href = links[i].href;
                        if (text.length > 3 && text.length < 200 && !seen[href]) {
                            if (href.includes('login') || href.includes('sign-in')) continue;
                            seen[href] = true;
                            var parent = links[i].closest('div, li, tr');
                            var loc = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl) loc = locEl.innerText.trim();
                            }
                            results.push({title: text, href: href, location: loc, department: '', date: ''});
                        }
                    }
                }

                return results;
            """)

            if job_data:
                logger.info(f"JS extraction found {len(job_data)} jobs")
                seen_urls = set()
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '').strip()
                    href = jd.get('href', '').strip()
                    location = jd.get('location', '').strip()
                    department = jd.get('department', '').strip()
                    date = jd.get('date', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if href in seen_urls:
                        continue
                    if href:
                        seen_urls.add(href)

                    # Filter for India jobs
                    if location and not self._is_india_job(location):
                        continue

                    if href and href.startswith('/'):
                        href = f"https://careers.synopsys.com{href}"

                    job_id = hashlib.md5((href or f"{title}_{idx}").encode()).hexdigest()[:12]
                    if href and '/job/' in href:
                        parts = href.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location if location else 'India',
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': department,
                        'apply_url': href if href else self.url,
                        'posted_date': date,
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
        except Exception as e:
            logger.error(f"JS extraction failed: {e}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to the next page of results."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a.next'),
                (By.CSS_SELECTOR, 'a[title="Next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
                (By.CSS_SELECTOR, 'li.next a'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] a[class*="next"]'),
                (By.CSS_SELECTOR, '[data-ph-at-id*="next"]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

if __name__ == "__main__":
    scraper = SynopsysScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

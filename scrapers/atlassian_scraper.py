from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

try:
    import requests
except ImportError:
    requests = None

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('atlassian_scraper')

class AtlassianScraper:
    def __init__(self):
        self.company_name = "Atlassian"
        self.url = "https://www.atlassian.com/company/careers/all-jobs?team=&location=India&search="
        self.base_url = 'https://www.atlassian.com'
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Atlassian jobs from custom SPA. Try API first, then Selenium."""
        all_jobs = []

        # Strategy 1: Try the Atlassian careers API directly
        if requests is not None:
            try:
                api_jobs = self._scrape_via_api()
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("API method returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.error(f"API method failed: {str(e)}, falling back to Selenium")

        # Strategy 2: Selenium-based scraping
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self):
        """Try to fetch jobs from Atlassian's internal API."""
        jobs = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.atlassian.com/company/careers/all-jobs',
        }

        # Known Atlassian API endpoints
        api_urls = [
            'https://www.atlassian.com/endpoint/careers/listings?location=India',
            'https://www.atlassian.com/api/careers/jobs?location=India',
            'https://www.atlassian.com/company/careers/api/jobs?location=India',
        ]

        for api_url in api_urls:
            try:
                response = requests.get(api_url, headers=headers, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    job_list = None
                    if isinstance(data, list):
                        job_list = data
                    elif isinstance(data, dict):
                        for key in ['jobs', 'positions', 'data', 'results', 'listings']:
                            if key in data and isinstance(data[key], list):
                                job_list = data[key]
                                break

                    if job_list and len(job_list) > 0:
                        logger.info(f"Found {len(job_list)} jobs from API: {api_url}")
                        for idx, item in enumerate(job_list):
                            job = self._parse_api_job(item, idx)
                            if job:
                                jobs.append(job)
                        if jobs:
                            return jobs
            except Exception as e:
                logger.debug(f"API endpoint {api_url} failed: {str(e)}")
                continue

        return jobs

    def _parse_api_job(self, item, idx):
        """Parse a single job from API response."""
        if not isinstance(item, dict):
            return None

        title = (item.get('title', '') or item.get('name', '') or
                 item.get('job_title', '') or '').strip()
        if not title or len(title) < 3:
            return None

        location = (item.get('location', '') or item.get('city', '') or '').strip()
        if isinstance(location, list) and location:
            location = ', '.join(location) if all(isinstance(l, str) for l in location) else str(location[0])

        # Filter for India
        loc_check = (str(location) + ' ' + str(item.get('country', ''))).lower()
        india_cities = ['india', 'bangalore', 'bengaluru', 'mumbai', 'delhi', 'hyderabad',
                        'chennai', 'pune', 'gurgaon', 'remote']
        if location and not any(c in loc_check for c in india_cities):
            return None

        job_id = str(item.get('id', '') or item.get('jobId', '') or f"atlassian_api_{idx}")
        apply_url = item.get('url', '') or item.get('apply_url', '') or item.get('link', '') or ''
        if apply_url and apply_url.startswith('/'):
            apply_url = f"{self.base_url}{apply_url}"
        if not apply_url:
            apply_url = self.url

        department = str(item.get('department', '') or item.get('team', '') or item.get('category', '') or '')
        employment_type = str(item.get('employment_type', '') or item.get('type', '') or '')

        loc_data = self.parse_location(location)

        return {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': str(item.get('description', '') or '')[:3000],
            'location': location or 'India',
            'city': loc_data.get('city', ''),
            'state': loc_data.get('state', ''),
            'country': loc_data.get('country', 'India'),
            'employment_type': employment_type,
            'department': department,
            'apply_url': apply_url,
            'posted_date': str(item.get('posted_date', '') or item.get('date', '') or ''),
            'job_function': '',
            'experience_level': str(item.get('experience_level', '') or ''),
            'salary_range': '',
            'remote_type': str(item.get('remote_type', '') or item.get('workType', '') or ''),
            'status': 'active'
        }

    def _scrape_via_selenium(self, max_pages):
        """Selenium-based scraping for Atlassian custom SPA."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")
            driver.get(self.url)

            # Wait for job listings to render
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'div[class*="job"], a[class*="job"], table[class*="job"], '
                        'div[class*="listing"], div[class*="career"], div[class*="opening"]'
                    ))
                )
                logger.info("Job listings detected")
            except Exception as e:
                logger.warning(f"Timeout waiting for job listings: {str(e)}, using fallback wait")
                time.sleep(10)

            # Scroll to load all dynamic content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try to click "Show More" / "Load All" if present
            for _ in range(10):
                try:
                    load_more = driver.find_element(
                        By.XPATH,
                        '//button[contains(text(), "Show more")] | '
                        '//button[contains(text(), "Load more")] | '
                        '//button[contains(text(), "View more")] | '
                        '//a[contains(text(), "Show more")]'
                    )
                    if load_more.is_displayed() and load_more.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", load_more)
                        time.sleep(2)
                    else:
                        break
                except Exception:
                    break

            scraped_ids = set()
            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                page_jobs = self._extract_jobs_from_dom(driver, scraped_ids)
                all_jobs.extend(page_jobs)
                logger.info(f"Page {current_page}: found {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if current_page < max_pages and page_jobs:
                    if not self._go_to_next_page(driver):
                        break
                    time.sleep(3)
                elif not page_jobs:
                    break

                current_page += 1

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during Selenium scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _extract_jobs_from_dom(self, driver, scraped_ids):
        """Extract jobs from DOM for Atlassian's custom SPA."""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Atlassian job list items (typically links in a grid/list)
                var cards = document.querySelectorAll(
                    'a[href*="/company/careers/detail/"], a[href*="/careers/"], ' +
                    'div[class*="job-card"], div[class*="jobCard"], ' +
                    'div[class*="job-listing"], div[class*="career-listing"], ' +
                    'tr[class*="job"], li[class*="job"], ' +
                    'div[class*="opening"], div[class*="position"]'
                );

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var title = '';
                    var url = '';
                    var location = '';
                    var department = '';

                    // Title
                    var titleEl = card.querySelector(
                        'h2, h3, h4, [class*="title"], [class*="name"], [class*="heading"]'
                    );
                    if (titleEl) title = titleEl.innerText.trim().split('\\n')[0];

                    // URL
                    if (card.tagName === 'A') {
                        url = card.href || '';
                        if (!title) title = card.innerText.trim().split('\\n')[0];
                    } else {
                        var link = card.querySelector('a[href]');
                        if (link) {
                            url = link.href || '';
                            if (!title) title = link.innerText.trim().split('\\n')[0];
                        }
                    }

                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (url && seen[url]) continue;

                    // Location
                    var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                    if (locEl) location = locEl.innerText.trim();
                    if (!location) {
                        var text = card.innerText || '';
                        var cities = ['Bangalore', 'Bengaluru', 'Mumbai', 'Delhi', 'Hyderabad',
                                      'Chennai', 'Pune', 'India', 'Remote'];
                        var lines = text.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            for (var k = 0; k < cities.length; k++) {
                                if (lines[j].indexOf(cities[k]) !== -1) {
                                    location = lines[j].trim();
                                    break;
                                }
                            }
                            if (location) break;
                        }
                    }

                    // Department / Team
                    var deptEl = card.querySelector('[class*="team"], [class*="department"], [class*="category"]');
                    if (deptEl) department = deptEl.innerText.trim();

                    if (url) seen[url] = true;
                    results.push({title: title, url: url || '', location: location, department: department});
                }

                // Strategy 2: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tr, tbody tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        if (row.querySelector('th')) continue;
                        var link = row.querySelector('a[href]');
                        if (!link) continue;
                        var title = link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (!title || title.length < 3 || seen[href]) continue;
                        if (href) seen[href] = true;
                        var tds = row.querySelectorAll('td');
                        var loc = tds.length >= 2 ? tds[1].innerText.trim() : '';
                        var dept = tds.length >= 3 ? tds[2].innerText.trim() : '';
                        results.push({title: title, url: href, location: loc, department: dept});
                    }
                }

                // Strategy 3: Generic link detection
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href*="career"], a[href*="job"], a[href*="detail"]');
                    var jobKeywords = ['engineer', 'manager', 'developer', 'analyst', 'designer',
                                       'architect', 'lead', 'specialist', 'principal', 'director',
                                       'head', 'intern', 'scientist', 'product', 'program'];
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var text = link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (text.length < 5 || text.length > 200 || seen[href]) continue;
                        var lower = text.toLowerCase();
                        var isJob = false;
                        for (var j = 0; j < jobKeywords.length; j++) {
                            if (lower.indexOf(jobKeywords[j]) !== -1) { isJob = true; break; }
                        }
                        if (!isJob) continue;
                        if (href) seen[href] = true;
                        results.push({title: text, url: href, location: '', department: ''});
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} potential jobs")
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/detail/' in url:
                        parts = url.split('/detail/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0].split('?')[0]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location or 'India',
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'employment_type': '',
                        'department': department,
                        'apply_url': url or self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                    scraped_ids.add(ext_id)
            else:
                logger.warning("JS extraction returned no results")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs from DOM: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to the next page."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            next_selectors = [
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Show more")]'),
                (By.XPATH, '//button[contains(text(), "Load more")]'),
                (By.XPATH, '//button[contains(text(), "View more")]'),
                (By.CSS_SELECTOR, 'a.next, button.next'),
                (By.CSS_SELECTOR, '[class*="pagination"] button:last-child'),
            ]

            for sel_type, sel_val in next_selectors:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except Exception:
                    continue

            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            if parts[1] in ['IN', 'IND', 'India']:
                result['country'] = 'India'
            else:
                result['state'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result

if __name__ == "__main__":
    scraper = AtlassianScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

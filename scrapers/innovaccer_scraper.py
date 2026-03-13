import requests
import hashlib
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import os

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('innovaccer_scraper')

class InnovaccerScraper:
    def __init__(self):
        self.company_name = "Innovaccer"
        # Webflow + Finsweet -- CMS items are in the HTML
        self.url = "https://innovaccer.com/careers/jobs#view-jobs"
        self.base_url = 'https://innovaccer.com'
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        # Primary method: requests + BeautifulSoup (Webflow CMS items are in HTML)
        try:
            bs4_jobs = self._scrape_via_requests()
            if bs4_jobs:
                logger.info(f"Requests/BS4 method returned {len(bs4_jobs)} jobs")
                return bs4_jobs
            else:
                logger.warning("Requests/BS4 returned 0 jobs, falling back to Selenium")
        except Exception as e:
            logger.error(f"Requests/BS4 failed: {str(e)}, falling back to Selenium")

        # Fallback: Selenium
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_requests(self):
        """Scrape Innovaccer jobs using requests + BeautifulSoup (Webflow CMS)."""
        all_jobs = []
        scraped_ids = set()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        # Fetch the careers page
        page_url = 'https://innovaccer.com/careers/jobs'
        logger.info(f"Fetching: {page_url}")

        try:
            response = requests.get(page_url, headers=headers, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            return all_jobs

        soup = BeautifulSoup(response.text, 'html.parser')

        # Strategy 1: Webflow/Finsweet CMS -- div.job-info-wrapper with 5 child columns
        # (title link, department, location, type, apply link)
        job_wrappers = soup.select('div.job-info-wrapper')

        if job_wrappers:
            logger.info(f"Found {len(job_wrappers)} job-info-wrapper elements")
            for wrapper in job_wrappers:
                try:
                    job_data = self._parse_job_wrapper(wrapper, scraped_ids)
                    if job_data:
                        all_jobs.append(job_data)
                except Exception as e:
                    logger.error(f"Error parsing job wrapper: {str(e)}")
                    continue
        else:
            logger.info("No job-info-wrapper found, trying alternative selectors")
            # Strategy 2: Webflow collection items
            collection_items = soup.select('[class*="collection-item"], [class*="job-item"], [class*="job-card"]')
            if not collection_items:
                # Strategy 3: Any div with job-related classes
                collection_items = soup.select('div[class*="job"], div[class*="career"], div[class*="opening"]')

            logger.info(f"Found {len(collection_items)} collection items")
            for item in collection_items:
                try:
                    job_data = self._parse_collection_item(item, scraped_ids)
                    if job_data:
                        all_jobs.append(job_data)
                except Exception as e:
                    logger.error(f"Error parsing collection item: {str(e)}")
                    continue

        logger.info(f"Requests total jobs: {len(all_jobs)}")
        return all_jobs

    def _parse_job_wrapper(self, wrapper, scraped_ids):
        """Parse a div.job-info-wrapper with 5 columns: title link, department, location, type, apply link."""
        children = wrapper.find_all(recursive=False)

        title = ''
        apply_url = ''
        department = ''
        location = ''
        employment_type = ''

        # The wrapper has child elements as columns
        # Column 1: title link
        title_link = wrapper.select_one('a[href*="/careers/"], a[href*="/jobs/"], a[href]')
        if title_link:
            title = title_link.get_text(strip=True)
            href = title_link.get('href', '')
            if href and href.startswith('/'):
                apply_url = f"{self.base_url}{href}"
            elif href and href.startswith('http'):
                apply_url = href
            else:
                apply_url = f"{self.base_url}/{href}" if href else ''

        if not title or len(title) < 3:
            return None

        # Try to extract department, location, type from child divs
        text_children = []
        for child in children:
            text = child.get_text(strip=True)
            if text and text != title and len(text) > 0:
                text_children.append(text)

        # Typical layout: [title, department, location, type, "Apply"/"View"]
        # Skip the title (already extracted) and the "Apply" button
        non_title = [t for t in text_children if t != title and t.lower() not in ('apply', 'view', 'apply now')]

        if len(non_title) >= 1:
            department = non_title[0]
        if len(non_title) >= 2:
            location = non_title[1]
        if len(non_title) >= 3:
            employment_type = non_title[2]

        # If we have an "Apply" link that differs from the title link, use it
        apply_link = wrapper.select_one('a[href*="apply"], a[class*="apply"], a:last-of-type')
        if apply_link and apply_link != title_link:
            href = apply_link.get('href', '')
            if href and href.startswith('/'):
                apply_url = f"{self.base_url}{href}"
            elif href and href.startswith('http'):
                apply_url = href

        if not apply_url:
            apply_url = self.url

        # Extract job ID
        job_id = hashlib.md5((apply_url or title).encode()).hexdigest()[:12]
        if '/careers/' in apply_url or '/jobs/' in apply_url:
            path_part = apply_url.split('/')[-1].split('?')[0].split('#')[0]
            if path_part:
                job_id = path_part

        ext_id = self.generate_external_id(job_id, self.company_name)
        if ext_id in scraped_ids:
            return None
        scraped_ids.add(ext_id)

        loc_data = self.parse_location(location)
        return {
            'external_id': ext_id,
            'company_name': self.company_name, 'title': title,
            'apply_url': apply_url, 'location': location,
            'department': department, 'employment_type': employment_type,
            'description': '',
            'posted_date': '', 'city': loc_data.get('city', ''),
            'state': loc_data.get('state', ''),
            'country': loc_data.get('country', 'India'),
            'job_function': department, 'experience_level': '', 'salary_range': '',
            'remote_type': '', 'status': 'active'
        }

    def _parse_collection_item(self, item, scraped_ids):
        """Parse a Webflow collection item for job data."""
        link = item.select_one('a[href*="/careers/"], a[href*="/jobs/"], a[href]')
        if not link:
            return None

        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            return None

        href = link.get('href', '')
        if href and href.startswith('/'):
            apply_url = f"{self.base_url}{href}"
        elif href and href.startswith('http'):
            apply_url = href
        else:
            apply_url = self.url

        # Extract location
        location = ''
        loc_el = item.select_one('[class*="location"], [class*="Location"]')
        if loc_el:
            location = loc_el.get_text(strip=True)

        # Extract department
        department = ''
        dept_el = item.select_one('[class*="department"], [class*="team"], [class*="category"]')
        if dept_el:
            department = dept_el.get_text(strip=True)

        # Extract type
        employment_type = ''
        type_el = item.select_one('[class*="type"], [class*="employment"]')
        if type_el:
            employment_type = type_el.get_text(strip=True)

        job_id = hashlib.md5((apply_url or title).encode()).hexdigest()[:12]
        ext_id = self.generate_external_id(job_id, self.company_name)
        if ext_id in scraped_ids:
            return None
        scraped_ids.add(ext_id)

        loc_data = self.parse_location(location)
        return {
            'external_id': ext_id,
            'company_name': self.company_name, 'title': title,
            'apply_url': apply_url, 'location': location,
            'department': department, 'employment_type': employment_type,
            'description': '',
            'posted_date': '', 'city': loc_data.get('city', ''),
            'state': loc_data.get('state', ''),
            'country': loc_data.get('country', 'India'),
            'job_function': department, 'experience_level': '', 'salary_range': '',
            'remote_type': '', 'status': 'active'
        }

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: Scrape Innovaccer jobs using Selenium."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")
            driver.get(self.url)

            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'div.job-info-wrapper, a[href*="/careers/"], div[class*="job-card"]'
                    ))
                )
                logger.info("Job listings detected")
            except Exception:
                logger.warning("Timeout waiting for listings, using fallback wait")
                time.sleep(10)

            # Scroll to trigger Finsweet/Webflow lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            scraped_ids = set()
            page_jobs = self._extract_jobs_selenium(driver, scraped_ids)
            all_jobs.extend(page_jobs)

            # Webflow sites are typically single-page for job listings
            # Try "Load more" if available
            for page in range(1, max_pages):
                if not self._load_more(driver):
                    break
                more_jobs = self._extract_jobs_selenium(driver, scraped_ids)
                if not more_jobs:
                    break
                all_jobs.extend(more_jobs)
                logger.info(f"After load more {page}: {len(more_jobs)} new jobs (total: {len(all_jobs)})")

            logger.info(f"Total jobs scraped via Selenium: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error during Selenium scraping: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs_selenium(self, driver, scraped_ids):
        """Extract jobs from Webflow page using JavaScript."""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: div.job-info-wrapper (Webflow/Finsweet CMS)
                var wrappers = document.querySelectorAll('div.job-info-wrapper');
                for (var i = 0; i < wrappers.length; i++) {
                    var wrapper = wrappers[i];
                    var links = wrapper.querySelectorAll('a[href]');
                    if (links.length === 0) continue;

                    var titleLink = links[0];  // First link is typically the title
                    var title = titleLink.innerText.trim();
                    var url = titleLink.href || '';
                    if (!title || title.length < 3 || seen[url]) continue;
                    seen[url] = true;

                    // Extract text from child divs for columns
                    var children = wrapper.children;
                    var texts = [];
                    for (var j = 0; j < children.length; j++) {
                        var t = children[j].innerText.trim();
                        if (t && t !== title && t.toLowerCase() !== 'apply' && t.toLowerCase() !== 'apply now') {
                            texts.push(t);
                        }
                    }

                    var department = texts.length > 0 ? texts[0] : '';
                    var location = texts.length > 1 ? texts[1] : '';
                    var type = texts.length > 2 ? texts[2] : '';

                    // Use the last link as apply URL if different
                    var applyUrl = url;
                    if (links.length > 1) {
                        var lastLink = links[links.length - 1];
                        if (lastLink.href && lastLink.href !== url) {
                            applyUrl = lastLink.href;
                        }
                    }

                    results.push({title: title, url: applyUrl || url, location: location, department: department, type: type});
                }

                // Strategy 2: Collection items
                if (results.length === 0) {
                    var items = document.querySelectorAll('[class*="collection-item"], [class*="job-item"], [class*="job-card"]');
                    for (var i = 0; i < items.length; i++) {
                        var item = items[i];
                        var link = item.querySelector('a[href]');
                        if (!link) continue;
                        var title = link.innerText.trim().split('\\n')[0];
                        var url = link.href || '';
                        if (!title || title.length < 3 || seen[url]) continue;
                        seen[url] = true;

                        var locEl = item.querySelector('[class*="location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var deptEl = item.querySelector('[class*="department"], [class*="team"]');
                        var department = deptEl ? deptEl.innerText.trim() : '';

                        results.push({title: title, url: url, location: location, department: department, type: ''});
                    }
                }

                // Strategy 3: Generic fallback
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href*="/careers/"], a[href*="/jobs/"]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var a = allLinks[i];
                        var href = a.href;
                        if (!href || seen[href] || href.includes('#view-jobs')) continue;
                        seen[href] = true;
                        var text = (a.innerText || '').trim().split('\\n')[0].trim();
                        if (!text || text.length < 3 || text.length > 200) continue;
                        if (/^(Home|About|Careers|View|Apply|Sign|Log)/i.test(text)) continue;
                        results.push({title: text, url: href, location: '', department: '', type: ''});
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    employment_type = jdata.get('type', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': department, 'employment_type': employment_type,
                        'description': '',
                        'posted_date': '', 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': department, 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })
                    scraped_ids.add(ext_id)
            else:
                logger.warning("No jobs found via Selenium JS extraction")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _load_more(self, driver):
        """Try to load more results on Webflow page."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            old_count = driver.execute_script("""
                return document.querySelectorAll('div.job-info-wrapper, [class*="collection-item"]').length;
            """)

            for sel_type, sel_val in [
                (By.XPATH, '//button[contains(text(), "Load more")]'),
                (By.XPATH, '//a[contains(text(), "Load more")]'),
                (By.XPATH, '//button[contains(text(), "Show more")]'),
                (By.CSS_SELECTOR, 'button[class*="load-more"]'),
                (By.CSS_SELECTOR, '[class*="pagination"] [class*="next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        for _ in range(25):
                            time.sleep(0.2)
                            new_count = driver.execute_script("""
                                return document.querySelectorAll('div.job-info-wrapper, [class*="collection-item"]').length;
                            """)
                            if new_count > old_count:
                                break
                        time.sleep(0.5)
                        logger.info("Loaded more results")
                        return True
                except:
                    continue
            return False
        except:
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
            result['country'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result

if __name__ == "__main__":
    scraper = InnovaccerScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

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
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

logger = setup_logger('ea_scraper')


class EAScraper:
    def __init__(self):
        self.company_name = "Electronic Arts"
        # Avature (server-rendered) -- field 8171=10590 is India filter
        self.url = "https://jobs.ea.com/en_US/careers/Home/?8171=%5B10590%5D&8171_format=5683&listFilterMode=1&jobRecordsPerPage=20&"
        self.base_url = 'https://jobs.ea.com'

    def setup_driver(self):
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception:
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        # Primary method: requests + BeautifulSoup (Avature SSR)
        try:
            bs4_jobs = self._scrape_via_requests(max_pages)
            if bs4_jobs:
                logger.info(f"Requests/BS4 method returned {len(bs4_jobs)} jobs")
                return bs4_jobs
            else:
                logger.warning("Requests/BS4 returned 0 jobs, falling back to Selenium")
        except Exception as e:
            logger.error(f"Requests/BS4 failed: {str(e)}, falling back to Selenium")

        # Fallback: Selenium
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_requests(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape EA jobs using requests + BeautifulSoup (Avature SSR)."""
        all_jobs = []
        scraped_ids = set()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        session = requests.Session()
        session.headers.update(headers)

        for page in range(max_pages):
            # Avature pagination: append &page=N or use offset param
            page_url = self.url
            if page > 0:
                separator = '&' if '?' in page_url else '?'
                page_url = f"{page_url}{separator}page={page + 1}"

            logger.info(f"Fetching page {page + 1}: {page_url}")

            try:
                response = session.get(page_url, timeout=30)
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Request failed for page {page + 1}: {str(e)}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            page_jobs = self._parse_html(soup, scraped_ids)

            if not page_jobs:
                logger.info(f"No jobs found on page {page + 1}, stopping")
                break

            all_jobs.extend(page_jobs)
            logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

        logger.info(f"Requests total jobs: {len(all_jobs)}")
        return all_jobs

    def _parse_html(self, soup, scraped_ids):
        """Parse Avature SSR HTML for job listings."""
        jobs = []

        # Strategy 1: li.sort__item--job with a.link.link_result
        job_items = soup.select('li.sort__item--job, li.sort__item')
        if not job_items:
            # Strategy 2: article-based listings
            job_items = soup.select('article.article--result, article[class*="article"]')
        if not job_items:
            # Strategy 3: Any link with JobDetail
            job_items = soup.select('a[href*="JobDetail"]')

        logger.info(f"Found {len(job_items)} raw job items in HTML")

        for item in job_items:
            try:
                # Extract link
                if item.name == 'a':
                    link_el = item
                else:
                    link_el = item.select_one('a.link.link_result, a[href*="JobDetail"], a[href*="/job/"], h3 a, a')

                if not link_el:
                    continue

                title = link_el.get_text(strip=True).split('\n')[0].strip()
                href = link_el.get('href', '')

                if not title or len(title) < 3 or len(title) > 200:
                    continue
                # Skip non-job links
                if any(kw in title.lower() for kw in ['sign in', 'log in', 'apply', 'save', 'share']):
                    continue

                # Build full URL
                if href and href.startswith('/'):
                    href = f"{self.base_url}{href}"
                elif href and not href.startswith('http'):
                    href = f"{self.base_url}/{href}"

                if not href:
                    continue

                # Extract location
                location = ''
                loc_el = item.select_one('[class*="location"], span[class*="loc"]')
                if loc_el:
                    location = loc_el.get_text(strip=True)

                # If no location found, check subtitle/meta text
                if not location:
                    subtitle_el = item.select_one('.article__header__text__subtitle, [class*="subtitle"], [class*="meta"]')
                    if subtitle_el:
                        sub_text = subtitle_el.get_text(strip=True)
                        # Check if it contains Indian location markers
                        india_markers = ['India', 'Mumbai', 'Bangalore', 'Bengaluru', 'Hyderabad',
                                         'Delhi', 'Chennai', 'Pune', 'Gurgaon', 'Gurugram', 'Noida']
                        for marker in india_markers:
                            if marker in sub_text:
                                # Extract location portion
                                parts = sub_text.split('\u2022')
                                location = parts[0].strip() if parts else sub_text
                                break

                # Extract job ID from URL
                job_id = hashlib.md5((href or title).encode()).hexdigest()[:12]
                if 'JobDetail' in href:
                    parts = href.split('/')
                    candidate = parts[-1].split('?')[0]
                    if candidate:
                        job_id = candidate

                ext_id = self.generate_external_id(job_id, self.company_name)
                if ext_id in scraped_ids:
                    continue

                loc_data = self.parse_location(location)
                jobs.append({
                    'external_id': ext_id,
                    'company_name': self.company_name, 'title': title,
                    'apply_url': href, 'location': location,
                    'department': '', 'employment_type': '', 'description': '',
                    'posted_date': '', 'city': loc_data.get('city', ''),
                    'state': loc_data.get('state', ''),
                    'country': loc_data.get('country', 'India'),
                    'job_function': '', 'experience_level': '', 'salary_range': '',
                    'remote_type': '', 'status': 'active'
                })
                scraped_ids.add(ext_id)

            except Exception as e:
                logger.error(f"Error parsing job item: {str(e)}")
                continue

        return jobs

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: Scrape EA jobs using Selenium."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")
            driver.get(self.url)

            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'article.article--result, li.sort__item--job, a[href*="JobDetail"]'
                    ))
                )
                logger.info("Job listings detected")
            except Exception:
                logger.warning("Timeout waiting for listings, using fallback wait")
                time.sleep(15)

            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            for page in range(max_pages):
                page_jobs = self._extract_jobs_selenium(driver)
                if not page_jobs:
                    break
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if not self._go_to_next_page(driver):
                    break
                time.sleep(5)

            logger.info(f"Total jobs scraped via Selenium: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error during Selenium scraping: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs_selenium(self, driver):
        jobs = []

        try:
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Avature article cards
                var articles = document.querySelectorAll('article.article--result');
                for (var i = 0; i < articles.length; i++) {
                    var art = articles[i];
                    var titleLink = art.querySelector('h3 a, a.article__header__focusable, a.link');
                    if (!titleLink) continue;
                    var title = titleLink.innerText.trim();
                    var url = titleLink.href || '';
                    if (!title || title.length < 3 || seen[url]) continue;
                    seen[url] = true;
                    var subtitle = art.querySelector('.article__header__text__subtitle');
                    var locText = '';
                    if (subtitle) {
                        var parts = subtitle.innerText.trim().split('\\u2022');
                        if (parts.length > 0) locText = parts[0].trim();
                    }
                    results.push({title: title, url: url, location: locText, date: ''});
                }

                // Strategy 2: Sort list items
                if (results.length === 0) {
                    var sortItems = document.querySelectorAll('li.sort__item--job, li.sort__item');
                    for (var i = 0; i < sortItems.length; i++) {
                        var item = sortItems[i];
                        var linkEl = item.querySelector('a.link.link_result, a[href*="JobDetail"], a');
                        if (!linkEl) continue;
                        var title = linkEl.innerText.trim().split('\\n')[0];
                        var url = linkEl.href || '';
                        if (!title || title.length < 3 || seen[url]) continue;
                        seen[url] = true;
                        var locEl = item.querySelector('[class*="location"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        results.push({title: title, url: url, location: location, date: ''});
                    }
                }

                // Strategy 3: JobDetail links
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="JobDetail"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var a = jobLinks[i];
                        var href = a.href;
                        if (!href || seen[href]) continue;
                        seen[href] = true;
                        var text = (a.innerText || '').trim().split('\\n')[0].trim();
                        if (!text || text.length < 3 || text.length > 200) continue;
                        if (/^(View|Apply|Save|Share|Sign|Log)/i.test(text)) continue;
                        var parent = a.closest('li, article, div[class*="result"]');
                        var location = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"]');
                            if (locEl) location = locEl.innerText.trim();
                        }
                        results.push({title: text, url: href, location: location, date: ''});
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if 'JobDetail' in url:
                        parts = url.split('/')
                        candidate = parts[-1].split('?')[0]
                        if candidate:
                            job_id = candidate

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': '', 'employment_type': '', 'description': '',
                        'posted_date': '', 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            for sel_type, sel_val in [
                (By.CSS_SELECTOR, "a[class*='viewMoreResults']"),
                (By.XPATH, "//a[contains(text(), 'View more')]"),
                (By.XPATH, "//button[contains(text(), 'View more')]"),
                (By.CSS_SELECTOR, 'a.paginationNextLink'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
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
    scraper = EAScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

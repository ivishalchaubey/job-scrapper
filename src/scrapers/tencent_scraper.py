from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import sys
from pathlib import Path

try:
    import requests as req_lib
except ImportError:
    req_lib = None

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('tencent_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class TencentScraper:
    def __init__(self):
        self.company_name = 'Tencent'
        self.url = 'https://careers.tencent.com/en-us/search.html?query=at_1,co_7&sc=7'
        self.base_url = 'https://careers.tencent.com'
        self.api_url = 'https://careers.tencent.com/tencentcareer/api/post/Query'

    def setup_driver(self):
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=AppleWebKit/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])

        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Auto-detect failed: {str(e)}, trying explicit path")
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
        # Primary: Tencent GET API
        if req_lib is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("API returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.warning(f"API failed: {str(e)}, falling back to Selenium")

        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        page_size = 20

        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': self.url,
        }

        # Try India first (countryId=7), fall back to all jobs if 0 results
        for country_id, country_name in [('7', 'India'), ('', 'Global')]:
            all_jobs = []
            for page_idx in range(1, max_pages + 1):
                params = {
                    'timestamp': int(time.time() * 1000),
                    'countryId': country_id,
                    'cityId': '',
                    'bgIds': '',
                    'productId': '',
                    'categoryId': '',
                    'parentCategoryId': '',
                    'attrId': '1',
                    'keyword': '',
                    'pageIndex': page_idx,
                    'pageSize': page_size,
                    'language': 'en',
                    'area': 'us',
                }

                try:
                    logger.info(f"Fetching API page {page_idx} for {country_name}")
                    response = req_lib.get(self.api_url, params=params, headers=headers, timeout=30)
                    response.raise_for_status()
                    data = response.json()

                    if data.get('Code') != 200:
                        logger.warning(f"API returned code {data.get('Code')}")
                        break

                    posts = data.get('Data', {}).get('Posts', [])
                    total = data.get('Data', {}).get('Count', 0)

                    if not posts:
                        break

                    logger.info(f"API page {page_idx}: {len(posts)} posts (total: {total})")

                    for post in posts:
                        try:
                            title = post.get('RecruitPostName', '')
                            if not title:
                                continue

                            post_id = str(post.get('PostId', ''))
                            location = post.get('LocationName', '')
                            category = post.get('CategoryName', '')
                            country = post.get('CountryName', '')
                            update_time = post.get('LastUpdateTime', '')

                            apply_url = f"{self.base_url}/en-us/position.html?id={post_id}" if post_id else self.url

                            loc_data = self.parse_location(location)
                            if country:
                                loc_data['country'] = country

                            all_jobs.append({
                                'external_id': self.generate_external_id(post_id or title, self.company_name),
                                'company_name': self.company_name,
                                'title': title,
                                'apply_url': apply_url,
                                'location': location,
                                'department': category,
                                'employment_type': '',
                                'description': '',
                                'posted_date': update_time,
                                'city': loc_data.get('city', ''),
                                'state': loc_data.get('state', ''),
                                'country': loc_data.get('country', ''),
                                'job_function': '',
                                'experience_level': '',
                                'salary_range': '',
                                'remote_type': '',
                                'status': 'active'
                            })
                        except Exception as e:
                            logger.error(f"Error processing post: {str(e)}")
                            continue

                    if len(all_jobs) >= total:
                        break

                except Exception as e:
                    logger.error(f"API request failed at page {page_idx}: {str(e)}")
                    break

            if all_jobs:
                logger.info(f"Found {len(all_jobs)} jobs for {country_name}")
                return all_jobs

        return all_jobs

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")
            driver.get(self.url)
            time.sleep(15)

            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            for page in range(max_pages):
                page_jobs = self._extract_jobs(driver)
                if not page_jobs:
                    break
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if not self._go_to_next_page(driver):
                    break
                time.sleep(5)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver):
        jobs = []
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};
                var items = document.querySelectorAll('.recruit-list .recruit-list-item, li.recruit-list-item');
                for (var i = 0; i < items.length; i++) {
                    var item = items[i];
                    var linkEl = item.querySelector('a[href*="position.html"], a[href]');
                    var titleEl = item.querySelector('h4, h3, .recruit-title, [class*="title"]');
                    if (!titleEl && linkEl) titleEl = linkEl;
                    if (!titleEl) continue;
                    var title = (titleEl.innerText || '').trim().split('\\n')[0].trim();
                    var href = linkEl ? (linkEl.href || '') : '';
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (href && seen[href]) continue;
                    if (href) seen[href] = true;
                    var locEl = item.querySelector('[class*="city"], [class*="location"]');
                    var location = locEl ? locEl.innerText.trim() : '';
                    results.push({title: title, url: href, location: location});
                }
                return results;
            """)

            if js_jobs:
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    if not title:
                        continue
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
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
        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")
        return jobs

    def _go_to_next_page(self, driver):
        try:
            next_clicked = driver.execute_script("""
                var nextBtn = document.querySelector('li.ant-pagination-next:not(.ant-pagination-disabled) a');
                if (nextBtn) { nextBtn.click(); return true; }
                return false;
            """)
            if next_clicked:
                logger.info("Navigated to next page")
                return True
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
    scraper = TencentScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

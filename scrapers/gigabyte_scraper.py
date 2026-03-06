from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from pathlib import Path


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('gigabyte_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

# Words that indicate non-job content (analytics, navigation, product names, etc.)
NON_JOB_KEYWORDS = [
    'cookie', 'privacy', 'analytics', 'tracking', 'subscribe', 'newsletter',
    'sign in', 'sign up', 'log in', 'register', 'add to cart', 'buy now',
    'product', 'motherboard', 'graphics card', 'laptop', 'monitor', 'desktop',
    'geforce', 'radeon', 'amd', 'intel', 'rgb', 'aorus', 'warranty',
    'driver', 'download', 'support', 'contact us', 'about us', 'sitemap',
    'terms of use', 'copyright', 'all rights reserved', 'follow us',
    'facebook', 'twitter', 'youtube', 'instagram', 'linkedin',
    'event description', 'event category', 'event action', 'event label',
    'google analytics', 'gtm', 'pageview', 'click event',
]


class GigabyteScraper:
    def __init__(self):
        self.company_name = 'Gigabyte'
        self.url = 'https://www.gigabyte.com/in/Career/-6'
        self.base_url = 'https://www.gigabyte.com'

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
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception:
            driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

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

    def _is_valid_job_title(self, title):
        """Check if a title looks like a real job posting, not analytics/nav/product content."""
        if not title or len(title) < 3 or len(title) > 200:
            return False
        title_lower = title.lower().strip()
        # Reject if it matches non-job keywords
        for keyword in NON_JOB_KEYWORDS:
            if keyword in title_lower:
                return False
        # Reject very short generic text
        if len(title_lower) < 5:
            return False
        # Reject if it looks like a URL or code
        if title_lower.startswith('http') or title_lower.startswith('www.'):
            return False
        if '{' in title or '}' in title or '<' in title or '>' in title:
            return False
        # Reject email addresses
        if '@' in title:
            return False
        # Reject phone numbers (mostly digits)
        digit_count = sum(1 for c in title if c.isdigit())
        if digit_count > len(title) * 0.5:
            return False
        return True

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            # Gigabyte uses Akamai CDN protection
            driver.get(self.url)
            time.sleep(15)

            # Handle potential Akamai challenge page
            page_source = driver.page_source.lower()
            if 'access denied' in page_source or 'akamai' in page_source:
                logger.warning("Akamai protection detected, waiting and retrying...")
                time.sleep(10)
                driver.refresh()
                time.sleep(10)
                page_source = driver.page_source.lower()
                if 'access denied' in page_source:
                    logger.error("Still blocked by Akamai. Cannot access career page.")
                    return all_jobs

            # Scroll to load content
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

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

                // Only look inside career-specific content areas
                var careerContent = document.querySelector(
                    '[class*="career"], [class*="Career"], [id*="career"], [id*="Career"], ' +
                    '[class*="recruit"], [class*="Recruit"], main, .content, #content'
                );
                if (!careerContent) careerContent = document.body;

                // Strategy 1: Look for structured job listings (tables, lists, cards)
                // within the career content area
                var jobContainers = careerContent.querySelectorAll(
                    'table tbody tr, ' +
                    '[class*="job-item"], [class*="job-listing"], [class*="career-item"], ' +
                    '[class*="vacancy"], [class*="opening"], [class*="position-item"]'
                );

                for (var i = 0; i < jobContainers.length; i++) {
                    var item = jobContainers[i];
                    // Skip header rows
                    if (item.querySelector('th')) continue;

                    var link = item.querySelector('a[href]');
                    var titleEl = item.querySelector('h2, h3, h4, h5, [class*="title"], [class*="name"]');
                    if (!titleEl && link) titleEl = link;
                    if (!titleEl) continue;

                    var title = (titleEl.innerText || '').trim().split('\\n')[0].trim();
                    var href = link ? link.href : '';

                    // Basic validation
                    if (!title || title.length < 5 || title.length > 200) continue;
                    var key = href || title;
                    if (seen[key]) continue;
                    seen[key] = true;

                    var locEl = item.querySelector('[class*="location"], [class*="Location"]');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var deptEl = item.querySelector('[class*="department"], [class*="Department"]');
                    var dept = deptEl ? deptEl.innerText.trim() : '';

                    results.push({
                        title: title,
                        location: location,
                        url: href || '',
                        date: '',
                        department: dept
                    });
                }

                // Strategy 2: Look for headings that are actual job titles
                // (only inside career-specific sections, not the whole page)
                if (results.length === 0) {
                    var careerSections = careerContent.querySelectorAll(
                        '[class*="career-list"], [class*="job-list"], [class*="opening-list"], ' +
                        '[class*="vacancy-list"], [class*="position-list"]'
                    );
                    for (var s = 0; s < careerSections.length; s++) {
                        var section = careerSections[s];
                        var items = section.querySelectorAll('li, div[class*="item"], div[class*="row"]');
                        for (var i = 0; i < items.length; i++) {
                            var item = items[i];
                            var titleEl = item.querySelector('h3, h4, h5, a, [class*="title"]');
                            if (!titleEl) continue;
                            var title = titleEl.innerText.trim().split('\\n')[0].trim();
                            if (!title || title.length < 5 || title.length > 200) continue;
                            var key = title;
                            if (seen[key]) continue;
                            seen[key] = true;
                            var link = item.querySelector('a[href]');
                            var href = link ? link.href : '';
                            results.push({
                                title: title,
                                location: 'India',
                                url: href || '',
                                date: '',
                                department: ''
                            });
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} candidate items, validating...")
                seen_urls = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    date = jdata.get('date', '').strip()
                    department = jdata.get('department', '').strip()

                    # Strict validation to avoid extracting non-job content
                    if not self._is_valid_job_title(title):
                        logger.debug(f"Rejected non-job title: {title[:50]}")
                        continue

                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'employment_type': '',
                        'department': department,
                        'apply_url': url or self.url,
                        'posted_date': date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} valid jobs")
            else:
                logger.info("No valid job listings found (Gigabyte India may have few or no open positions)")

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
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
    scraper = GigabyteScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

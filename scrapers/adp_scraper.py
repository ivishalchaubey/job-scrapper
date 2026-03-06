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
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

logger = setup_logger('adp_scraper')


class ADPScraper:
    def __init__(self):
        self.company_name = 'ADP'
        self.url = 'https://jobs.adp.com/en/jobs/?orderby=0&pagesize=20&page=1&mylocation=India'
        self.base_url = 'https://jobs.adp.com'

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
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Radancy/TalentBrew behind Cloudflare -- wait for challenge to pass
            logger.info("Waiting for Cloudflare challenge to resolve...")
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'a[href*="/en/jobs/"], div[class*="search-result"], li[class*="job"], div[class*="job-card"]'
                    ))
                )
                logger.info("Job listings detected after Cloudflare challenge")
            except Exception:
                logger.warning("Timeout waiting for Cloudflare, trying fallback wait")
                time.sleep(15)

            # Scroll to trigger lazy-loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            for page in range(max_pages):
                page_jobs = self._extract_jobs(driver)
                if not page_jobs:
                    break
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if page < max_pages - 1:
                    if not self._go_to_next_page(driver, page + 2):
                        break

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
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Common navigation/non-job words to filter out
                var navWords = ['home', 'about', 'search', 'sign', 'log', 'back', 'next',
                    'prev', 'jobs', 'career', 'careers', 'corporate', 'contact',
                    'privacy', 'terms', 'cookie', 'legal', 'apply', 'filter',
                    'sort', 'view', 'all', 'more', 'less', 'show', 'hide',
                    'menu', 'close', 'open', 'skip', 'main', 'footer', 'header',
                    'navigation', 'submit', 'reset', 'clear', 'login', 'register',
                    'join', 'talent', 'community', 'explore'];

                function isNavText(text) {
                    if (!text || text.length < 5) return true;
                    var lower = text.toLowerCase().trim();
                    // Single word matches against nav words
                    if (navWords.indexOf(lower) !== -1) return true;
                    // Two-word or short nav phrases
                    if (/^(all jobs|search jobs|sign in|log in|view all|see all|show all|find jobs|saved jobs|my jobs|job alerts|job search)$/i.test(lower)) return true;
                    return false;
                }

                // Check if a URL points to a specific job page (not the listing page)
                function isJobDetailUrl(href) {
                    if (!href) return false;
                    // ADP job detail URLs have a slug after /en/jobs/ like /en/jobs/some-job-title/123456
                    var match = href.match(/\\/en\\/jobs\\/([^/?#]+)/);
                    if (match && match[1]) {
                        // Must have a non-empty slug that's not just a page param
                        var slug = match[1];
                        if (slug.length > 2 && slug !== 'results' && slug !== 'search') return true;
                    }
                    return false;
                }

                // Strategy 1: Radancy/TalentBrew job cards
                var cards = document.querySelectorAll(
                    'li[class*="job-item"], div[class*="search-result"], ' +
                    'div[class*="job-card"], li[class*="search-result"], ' +
                    'li.job-info, div.job-info, section[class*="job"]'
                );
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var linkEl = card.querySelector('a[href*="/en/jobs/"], a[href*="/job/"]');
                    if (!linkEl) continue;
                    var href = linkEl.href;
                    if (!href || seen[href] || !isJobDetailUrl(href)) continue;
                    seen[href] = true;

                    var titleEl = card.querySelector('h2, h3, h4, [class*="title"], [class*="job-name"]');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title || isNavText(title)) {
                        title = linkEl.innerText.trim().split('\\n')[0];
                    }
                    if (!title || title.length > 200 || isNavText(title)) continue;

                    var locEl = card.querySelector('[class*="location"], [class*="Location"], span[class*="loc"]');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var deptEl = card.querySelector('[class*="department"], [class*="category"], [class*="function"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';

                    var dateEl = card.querySelector('[class*="date"], [class*="posted"]');
                    var date = dateEl ? dateEl.innerText.trim() : '';

                    results.push({title: title, url: href, location: location, department: department, date: date});
                }

                // Strategy 2: LD+JSON structured data (Google for Jobs markup)
                if (results.length === 0) {
                    var ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (var s = 0; s < ldScripts.length; s++) {
                        try {
                            var ld = JSON.parse(ldScripts[s].textContent);
                            var items = [];
                            if (Array.isArray(ld)) items = ld;
                            else if (ld['@type'] === 'JobPosting') items = [ld];
                            else if (ld.itemListElement) items = ld.itemListElement.map(function(e) { return e.item || e; });

                            for (var j = 0; j < items.length; j++) {
                                var item = items[j];
                                if (item['@type'] !== 'JobPosting') continue;
                                var t = item.title || item.name || '';
                                var u = item.url || '';
                                if (!t || !u || seen[u]) continue;
                                seen[u] = true;
                                var loc = '';
                                if (item.jobLocation) {
                                    var jl = item.jobLocation;
                                    if (jl.address) {
                                        loc = (jl.address.addressLocality || '') +
                                              (jl.address.addressRegion ? ', ' + jl.address.addressRegion : '') +
                                              (jl.address.addressCountry ? ', ' + jl.address.addressCountry : '');
                                    }
                                }
                                results.push({title: t, url: u, location: loc, department: '', date: item.datePosted || ''});
                            }
                        } catch(e) {}
                    }
                }

                // Strategy 3: Direct job detail links (only links to specific job pages)
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="/en/jobs/"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var a = jobLinks[i];
                        var href = a.href;
                        if (!href || seen[href] || !isJobDetailUrl(href)) continue;
                        seen[href] = true;

                        var text = (a.innerText || '').trim().split('\\n')[0].trim();
                        if (!text || text.length > 200 || isNavText(text)) continue;

                        var location = '';
                        var parent = a.closest('li, div[class*="job"], div[class*="result"], article, tr, section');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl && locEl !== a) location = locEl.innerText.trim();
                        }
                        results.push({title: text, url: href, location: location, department: '', date: ''});
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
                    department = jdata.get('department', '').strip()
                    date = jdata.get('date', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Extract job ID from URL
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if '/en/jobs/' in url:
                        parts = url.split('/en/jobs/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    # Filter for India-based jobs
                    if location and 'india' not in location.lower() and not any(
                        city in location for city in [
                            'Mumbai', 'Bengaluru', 'Bangalore', 'Hyderabad', 'Delhi',
                            'Chennai', 'Pune', 'Kolkata', 'Gurgaon', 'Gurugram', 'Noida'
                        ]
                    ):
                        continue

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': department, 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': department, 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
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

    def _go_to_next_page(self, driver, next_page_num):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            old_first = driver.execute_script("""
                var card = document.querySelector('a[href*="/en/jobs/"]');
                return card ? card.innerText.substring(0, 50) : '';
            """)

            # Method 1: Update URL page param directly (Radancy pagination)
            try:
                next_url = f"https://jobs.adp.com/en/jobs/?orderby=0&pagesize=20&page={next_page_num}&mylocation=India"
                driver.get(next_url)
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((
                            By.CSS_SELECTOR,
                            'a[href*="/en/jobs/"], div[class*="search-result"], li[class*="job"]'
                        ))
                    )
                except Exception:
                    time.sleep(5)

                new_first = driver.execute_script("""
                    var card = document.querySelector('a[href*="/en/jobs/"]');
                    return card ? card.innerText.substring(0, 50) : '';
                """)
                if new_first and new_first != old_first:
                    logger.info(f"Navigated to page {next_page_num} via URL")
                    return True
                elif not new_first:
                    logger.info("No jobs on next page")
                    return False
            except Exception as e:
                logger.warning(f"URL navigation failed: {str(e)}")

            # Method 2: Click next button
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'li.next a'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] [class*="next"] a'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        for _ in range(20):
                            time.sleep(0.2)
                            new_first = driver.execute_script("""
                                var card = document.querySelector('a[href*="/en/jobs/"]');
                                return card ? card.innerText.substring(0, 50) : '';
                            """)
                            if new_first and new_first != old_first:
                                break
                        time.sleep(0.5)
                        logger.info(f"Navigated to page {next_page_num} via button")
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
    scraper = ADPScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

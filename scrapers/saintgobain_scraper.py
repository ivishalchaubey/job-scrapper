# STATUS: BLOCKED - Cloudflare challenge on joinus.saint-gobain.com (tested 2026-02-22)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import re
import os
from pathlib import Path


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('saintgobain_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class SaintGobainScraper:
    def __init__(self):
        self.company_name = 'Saint-Gobain'
        self.url = 'https://joinus.saint-gobain.com/en'
        self.base_url = 'https://joinus.saint-gobain.com'
        # Search URL filtered to India (country code 'ind')
        self._search_url = 'https://joinus.saint-gobain.com/en/search-offers?query=&country=ind'

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
        # Extra anti-detection flags for Cloudflare
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        chrome_options.add_argument('--disable-site-isolation-trials')
        chrome_options.add_argument('--allow-running-insecure-content')
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

    def _setup_undetected_driver(self):
        """Try to use undetected_chromedriver for better Cloudflare bypass."""
        try:
            import undetected_chromedriver as uc
            options = uc.ChromeOptions()
            if HEADLESS_MODE:
                options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-web-security')
            options.add_argument('--disable-features=IsolateOrigins,site-per-process')
            driver = uc.Chrome(options=options, use_subprocess=True)
            logger.info("Using undetected_chromedriver for Cloudflare bypass")
            return driver
        except ImportError:
            logger.info("undetected_chromedriver not available, using standard Selenium")
            return None
        except Exception as e:
            logger.warning(f"undetected_chromedriver failed: {str(e)}, falling back to standard Selenium")
            return None

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _wait_for_cloudflare(self, driver, max_wait=50):
        """Wait for Cloudflare challenge to resolve. Returns True if page loaded successfully."""
        start = time.time()
        while time.time() - start < max_wait:
            try:
                title = driver.title.lower()
                body_text = driver.execute_script(
                    'return document.body ? document.body.innerText.substring(0, 500) : ""'
                )
                # Cloudflare challenge indicators
                if 'just a moment' in title or 'checking your browser' in body_text.lower():
                    logger.info(f"Cloudflare challenge active, waiting... ({int(time.time() - start)}s)")
                    time.sleep(5)
                    continue
                # If we get past the challenge page
                if 'saint-gobain' in title.lower() or 'join us' in title.lower() or len(body_text) > 200:
                    logger.info(f"Cloudflare challenge resolved after {int(time.time() - start)}s")
                    return True
            except Exception:
                time.sleep(3)
                continue
            time.sleep(3)
        logger.warning(f"Cloudflare challenge did not resolve within {max_wait}s")
        return False

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        # Strategy 1: Try undetected_chromedriver first
        driver = self._setup_undetected_driver()
        if driver:
            try:
                jobs = self._scrape_with_driver(driver, max_pages)
                if jobs:
                    return jobs
            except Exception as e:
                logger.error(f"undetected_chromedriver scraping failed: {str(e)}")
            finally:
                try:
                    driver.quit()
                except:
                    pass

        # Strategy 2: Standard Selenium with enhanced anti-detection + retries
        for attempt in range(3):
            driver = None
            try:
                driver = self.setup_driver()
                logger.info(f"Attempt {attempt + 1}/3: Starting {self.company_name} scraping")
                jobs = self._scrape_with_driver(driver, max_pages)
                if jobs:
                    return jobs
                logger.warning(f"Attempt {attempt + 1}: No jobs found, retrying...")
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} error: {str(e)}")
            finally:
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
            # Wait before retry
            if attempt < 2:
                time.sleep(10)

        logger.info(f"Total jobs scraped: {len(all_jobs)}")
        return all_jobs

    def _scrape_with_driver(self, driver, max_pages):
        """Core scraping logic with a given driver instance."""
        all_jobs = []

        # Load the search page filtered to India
        logger.info(f"Loading search page: {self._search_url}")
        driver.get(self._search_url)

        # Wait for Cloudflare challenge to resolve (up to 50 seconds)
        if not self._wait_for_cloudflare(driver, max_wait=50):
            # Try the main URL as fallback
            logger.info("Trying main URL as fallback...")
            driver.get(self.url)
            if not self._wait_for_cloudflare(driver, max_wait=45):
                logger.error("Could not bypass Cloudflare challenge")
                return []

        # Extra wait for SPA content to render
        time.sleep(10)

        # Scroll to trigger lazy loading
        for _ in range(5):
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
        return all_jobs

    def _extract_jobs(self, driver):
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

                // Strategy 1: Saint-Gobain specific - links matching /en/{country}/{type}/p/{id}/{id}/{title}
                var sgLinks = document.querySelectorAll('a[href*="/en/ind/"], a[href*="/en/usa/"], a[href*="/en/fra/"], a[href*="/en/deu/"]');
                if (sgLinks.length === 0) {
                    // Broader: any link with /p/ pattern (job detail pages)
                    sgLinks = document.querySelectorAll('a[href*="/p/"]');
                }
                for (var i = 0; i < sgLinks.length; i++) {
                    var el = sgLinks[i];
                    var href = el.href || '';
                    // Filter to actual job links (pattern: /en/{country}/{type}/p/{id}/{id}/{slug})
                    if (!href.match(/\\/en\\/[a-z]{3}\\/[a-z]+\\/p\\/\\d+\\/\\d+\\//)) continue;
                    var title = (el.innerText || '').trim().split('\\n')[0].trim();
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (seen[href]) continue;
                    seen[href] = true;
                    var location = '';
                    var parent = el.closest('li, div, article, tr, section');
                    if (parent) {
                        var locEl = parent.querySelector('[class*="location"], [class*="Location"], [class*="city"], [class*="country"]');
                        if (locEl && locEl !== el) location = locEl.innerText.trim();
                    }
                    var dateEl = parent ? parent.querySelector('[class*="date"], [class*="Date"]') : null;
                    var date = dateEl ? dateEl.innerText.trim() : '';
                    results.push({title: title, location: location, url: href, date: date});
                }

                // Strategy 2: Job card selectors (generic career platform patterns)
                if (results.length === 0) {
                    var cards = document.querySelectorAll('[class*="job-card"], [class*="jobCard"], [class*="search-result"], [class*="searchResult"]');
                    if (cards.length === 0) cards = document.querySelectorAll('[class*="offer-card"], [class*="offerCard"], [class*="job-listing"], [class*="position-card"]');
                    if (cards.length === 0) cards = document.querySelectorAll('li[class*="job"], div[class*="job-item"], article[class*="job"], article[class*="offer"]');

                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var titleEl = card.querySelector('.job-title, [class*="job-title"], [class*="jobTitle"], [class*="offer-title"], h2, h3, h4, [class*="title"]');
                        var locEl = card.querySelector('.job-location, [class*="location"], [class*="Location"]');
                        var linkEl = card.tagName === 'A' ? card : card.querySelector('a[href]');

                        var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                        if (!title && linkEl) title = linkEl.innerText.trim().split('\\n')[0];
                        var location = locEl ? locEl.innerText.trim() : '';
                        var href = linkEl ? linkEl.href : '';

                        if (title && title.length > 2 && title.length < 200 && href && !seen[href]) {
                            if (!href.includes('login') && !href.includes('sign-in') && !href.includes('javascript:')) {
                                seen[href] = true;
                                var dateEl = card.querySelector('[class*="date"], [class*="Date"]');
                                var date = dateEl ? dateEl.innerText.trim() : '';
                                results.push({title: title, location: location, url: href, date: date});
                            }
                        }
                    }
                }

                // Strategy 3: Direct job links with various URL patterns
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="/job/"], a[href*="/job-"], a[href*="/jobs/"], a[href*="/jb/"], a[href*="/position/"], a[href*="/vacancy/"], a[href*="/career/"], a[href*="/opening/"], a[href*="/requisition/"], a[href*="/annonce/"], a[href*="/offer/"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var el = jobLinks[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var url = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (url.includes('login') || url.includes('sign-in') || url.includes('javascript:')) continue;
                        if (seen[url]) continue;
                        seen[url] = true;
                        var location = '';
                        var parent = el.closest('li, div[class*="job"], div[class*="offer"], article, tr, div[class*="result"]');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl && locEl !== el) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: url, location: location, date: ''});
                    }
                }

                // Strategy 4: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr.dataRow, table tr[class*="job"]');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        var link = row.querySelector('a[href]');
                        if (!link) continue;
                        var title = link.innerText.trim().split('\\n')[0];
                        var href = link.href || '';
                        if (!title || title.length < 3 || !href || seen[href]) continue;
                        seen[href] = true;
                        var locTd = row.querySelector('td:nth-child(2), [class*="location"]');
                        var location = locTd ? locTd.innerText.trim() : '';
                        results.push({title: title, url: href, location: location, date: ''});
                    }
                }

                // Strategy 5: Generic fallback - any link that looks like a job posting
                if (results.length === 0) {
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var href = link.href || '';
                        var text = (link.innerText || '').trim();
                        if (text.length > 5 && text.length < 200 && href.length > 10) {
                            if ((href.includes('/job') || href.includes('/position') || href.includes('/career') || href.includes('/opening') || href.includes('/vacancy') || href.includes('/offer') || href.match(/\\/p\\/\\d+\\/\\d+\\//)) && !seen[href]) {
                                if (!href.includes('login') && !href.includes('sign-in') && !href.includes('javascript:') && !href.includes('#')) {
                                    seen[href] = true;
                                    results.push({title: text.split('\\n')[0].trim(), url: href, location: '', date: ''});
                                }
                            }
                        }
                    });
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
                    date = jdata.get('date', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Extract job ID from Saint-Gobain URL pattern: /en/{country}/{type}/p/{id1}/{id2}/{slug}
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    sg_match = re.search(r'/p/(\d+)/(\d+)/', url)
                    if sg_match:
                        job_id = sg_match.group(2)
                    elif url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': '', 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except: pass

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
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] a[class*="next"]'),
                (By.CSS_SELECTOR, '[class*="pagination"] button[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="load-more"]'),
                (By.XPATH, '//button[contains(text(), "Load more")]'),
                (By.XPATH, '//button[contains(text(), "Show more")]'),
                (By.XPATH, '//a[contains(text(), "Suivant")]'),
                (By.XPATH, '//a[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'nav[aria-label*="pagination"] a:last-child'),
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
        if not location_str: return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1: result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str: result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = SaintGobainScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

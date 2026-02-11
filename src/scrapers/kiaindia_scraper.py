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

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('kiaindia_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class KiaIndiaScraper:
    def __init__(self):
        self.company_name = 'Kia India'
        self.url = 'https://career.kiaindia.net/kiaindia/'
        self.base_url = 'https://career.kiaindia.net'

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
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(15)

            for _ in range(5):
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
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Kia India custom portal - card/opening selectors
                var cards = document.querySelectorAll('[class*="opening"], [class*="vacancy"], [class*="job-card"], [class*="jobCard"]');
                if (cards.length === 0) cards = document.querySelectorAll('[class*="job-listing"], [class*="jobListing"], [class*="position-card"], [class*="career-card"]');
                if (cards.length === 0) cards = document.querySelectorAll('li[data-ph-at-id="job-listing"], div[data-ph-at-id="job-listing"]');
                if (cards.length === 0) cards = document.querySelectorAll('a[data-ph-at-id="job-link"]');
                if (cards.length === 0) cards = document.querySelectorAll('li[data-job-id]');

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var titleEl = card.querySelector('h1, h2, h3, h4, h5, .job-title, [class*="job-title"], [class*="jobTitle"], [class*="title"], [class*="designation"]');
                    var locEl = card.querySelector('[class*="location"], [class*="Location"], [class*="city"], [class*="place"]');
                    var linkEl = card.tagName === 'A' ? card : card.querySelector('a[href]');

                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title && linkEl) title = linkEl.innerText.trim().split('\\n')[0];
                    var location = locEl ? locEl.innerText.trim() : '';
                    var href = linkEl ? linkEl.href : '';

                    if (title && title.length > 2 && title.length < 200) {
                        var key = href || title;
                        if (!seen[key]) {
                            if (!href || (!href.includes('login') && !href.includes('sign-in') && !href.includes('javascript:'))) {
                                seen[key] = true;
                                results.push({title: title, location: location, url: href || '', date: ''});
                            }
                        }
                    }
                }

                // Strategy 2: Find "Apply" buttons and walk up to parent container for title/location
                if (results.length === 0) {
                    var applyBtns = document.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
                    for (var i = 0; i < applyBtns.length; i++) {
                        var btn = applyBtns[i];
                        var btnText = (btn.innerText || btn.value || '').trim().toLowerCase();
                        if (!btnText.includes('apply') && !btnText.includes('view') && !btnText.includes('detail')) continue;

                        // Walk up to find the job card container
                        var container = btn.parentElement;
                        for (var depth = 0; depth < 6 && container; depth++) {
                            container = container.parentElement;
                        }
                        if (!container) container = btn.parentElement ? btn.parentElement.parentElement : null;
                        if (!container) continue;

                        // Extract title: look for headings or prominent text
                        var titleEl = container.querySelector('h1, h2, h3, h4, h5, [class*="title"], [class*="designation"], [class*="role"], [class*="name"]');
                        var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                        if (!title) {
                            // Get the first meaningful text line from the container
                            var lines = container.innerText.trim().split('\\n').filter(function(l) {
                                l = l.trim();
                                return l.length > 3 && l.length < 200 && !l.toLowerCase().includes('apply');
                            });
                            if (lines.length > 0) title = lines[0].trim();
                        }
                        if (!title || title.length < 3) continue;

                        var locEl = container.querySelector('[class*="location"], [class*="Location"], [class*="city"], [class*="place"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var linkEl = container.querySelector('a[href]');
                        var href = linkEl ? linkEl.href : '';

                        var key = title;
                        if (seen[key]) continue;
                        seen[key] = true;
                        results.push({title: title, location: location, url: href || '', date: ''});
                    }
                }

                // Strategy 3: Repeating div pattern detection
                // Find div classes that repeat many times (likely job cards)
                if (results.length === 0) {
                    var classCounts = {};
                    var allDivs = document.querySelectorAll('div[class], li[class], article[class]');
                    for (var i = 0; i < allDivs.length; i++) {
                        var cls = allDivs[i].className;
                        if (!cls || typeof cls !== 'string') continue;
                        classCounts[cls] = (classCounts[cls] || 0) + 1;
                    }
                    // Find classes that repeat 5+ times (likely job cards)
                    var candidateClasses = [];
                    for (var cls in classCounts) {
                        if (classCounts[cls] >= 5 && classCounts[cls] <= 200) {
                            candidateClasses.push({cls: cls, count: classCounts[cls]});
                        }
                    }
                    candidateClasses.sort(function(a, b) { return b.count - a.count; });

                    for (var c = 0; c < candidateClasses.length && results.length === 0; c++) {
                        var testCards = document.querySelectorAll('[class="' + candidateClasses[c].cls + '"]');
                        var testResults = [];
                        for (var i = 0; i < testCards.length; i++) {
                            var card = testCards[i];
                            var text = card.innerText.trim();
                            if (text.length < 10 || text.length > 500) continue;
                            var lines = text.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                            if (lines.length < 1) continue;
                            var title = lines[0];
                            if (title.length < 3 || title.length > 200) continue;
                            // Skip nav/header/footer elements
                            if (title.toLowerCase().includes('home') || title.toLowerCase().includes('menu') || title.toLowerCase().includes('copyright')) continue;
                            var linkEl = card.querySelector('a[href]');
                            var href = linkEl ? linkEl.href : '';
                            var location = '';
                            for (var l = 1; l < lines.length; l++) {
                                if (lines[l].length > 3 && lines[l].length < 100 && !lines[l].toLowerCase().includes('apply')) {
                                    location = lines[l];
                                    break;
                                }
                            }
                            testResults.push({title: title, location: location, url: href || '', date: ''});
                        }
                        if (testResults.length >= 5) {
                            for (var r = 0; r < testResults.length; r++) {
                                var key = testResults[r].title;
                                if (!seen[key]) {
                                    seen[key] = true;
                                    results.push(testResults[r]);
                                }
                            }
                        }
                    }
                }

                // Strategy 4: Direct job links (various URL patterns)
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="/job/"], a[href*="/job-"], a[href*="/jobs/"], a[href*="/jb/"], a[href*="/position/"], a[href*="/vacancy/"], a[href*="/career/"], a[href*="/opening/"], a[href*="/requisition/"], a[href*="/apply"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var el = jobLinks[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var url = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (url.includes('login') || url.includes('sign-in') || url.includes('javascript:')) continue;
                        if (seen[url]) continue;
                        seen[url] = true;
                        var location = '';
                        var parent = el.closest('li, div, article, tr, section');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"], [class*="city"]');
                            if (locEl && locEl !== el) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: url, location: location, date: ''});
                    }
                }

                // Strategy 5: Text content parsing - extract job-like entries from page text
                if (results.length === 0) {
                    var bodyText = document.body ? document.body.innerText : '';
                    var lines = bodyText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                    var jobKeywords = ['manager', 'engineer', 'analyst', 'executive', 'officer', 'lead', 'head', 'specialist', 'associate', 'coordinator', 'developer', 'intern', 'trainee', 'supervisor', 'director', 'senior', 'junior', 'sales', 'marketing', 'hr', 'hrbp', 'finance', 'operations'];
                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i];
                        if (line.length < 5 || line.length > 200) continue;
                        var lineLower = line.toLowerCase();
                        var isJob = false;
                        for (var k = 0; k < jobKeywords.length; k++) {
                            if (lineLower.includes(jobKeywords[k])) { isJob = true; break; }
                        }
                        if (!isJob) continue;
                        // Skip if it looks like a menu/header/filter item
                        if (lineLower.includes('filter') || lineLower.includes('sort') || lineLower.includes('search') || lineLower.includes('menu') || lineLower === 'apply') continue;
                        if (seen[line]) continue;
                        seen[line] = true;
                        // Next non-empty line might be location
                        var location = '';
                        for (var j = i + 1; j < Math.min(i + 4, lines.length); j++) {
                            var nextLine = lines[j];
                            if (nextLine.length > 2 && nextLine.length < 100 && !nextLine.toLowerCase().includes('apply') && !nextLine.toLowerCase().includes('view')) {
                                location = nextLine;
                                break;
                            }
                        }
                        results.push({title: line, location: location, url: '', date: ''});
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
                    date = jdata.get('date', '').strip()

                    if not title or len(title) < 3:
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
                (By.CSS_SELECTOR, 'button[data-ph-at-id="load-more-jobs-button"]'),
                (By.CSS_SELECTOR, 'a[data-ph-at-id="pagination-next-btn"]'),
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
    scraper = KiaIndiaScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

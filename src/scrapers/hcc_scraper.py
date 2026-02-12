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

logger = setup_logger('hcc_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class HCCScraper:
    def __init__(self):
        self.company_name = 'HCC'
        self.url = 'https://www.hccindia.com/career/current-opening'
        self.base_url = 'https://www.hccindia.com'

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
            short_wait = WebDriverWait(driver, 5)
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)
            time.sleep(13)

            # Scroll to load lazy content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Check for iframes
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                logger.info(f"Found {len(iframes)} iframes, checking for job content")
                for iframe in iframes:
                    try:
                        src = iframe.get_attribute('src') or ''
                        iframe_id = iframe.get_attribute('id') or ''
                        logger.info(f"iframe id={iframe_id} src={src[:100]}")
                        if any(kw in src.lower() for kw in ['job', 'career', 'recruit', 'talent', 'opening']):
                            driver.switch_to.frame(iframe)
                            logger.info("Switched to job iframe")
                            time.sleep(5)
                            break
                    except:
                        continue

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
            # Scroll to ensure content is loaded
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Garbage title filter
                function isGarbageTitle(title) {
                    var lower = title.toLowerCase().trim();
                    var garbage = ['careers', 'career', 'jobs', 'home', 'about', 'contact',
                        'current openings', 'current opening', 'current-opening',
                        'browse', 'search', 'apply', 'apply now', 'view all',
                        'address', 'explore', 'newsletter', 'signup', 'subscribe',
                        'connect with us', 'contact us', 'terms', 'privacy',
                        'supplier portal', 'media room', 'investors',
                        'professionals', 'recent graduates', 'working at hcc'];
                    for (var g = 0; g < garbage.length; g++) {
                        if (lower === garbage[g]) return true;
                    }
                    if (lower.startsWith('browse through')) return true;
                    return false;
                }

                // Strategy 1 (PRIORITY): Links with /careers/ in href (HCC pattern: /careers/job-slug)
                var careerLinks = document.querySelectorAll('a[href*="/careers/"], a[href*="/career/"], a[href*="/job/"], a[href*="/jobs/"], a[href*="/opening/"], a[href*="/vacancy/"], a[href*="/position/"]');
                for (var i = 0; i < careerLinks.length; i++) {
                    var el = careerLinks[i];
                    var href = el.href || '';
                    if (!href || seen[href]) continue;
                    // Skip main navigation links (exact career/current-opening page)
                    if (href.endsWith('/career') || href.endsWith('/career/') ||
                        href.endsWith('/careers') || href.endsWith('/careers/') ||
                        href.endsWith('/current-opening') || href.endsWith('/current-opening/')) continue;
                    if (href === window.location.href) continue;
                    if (href.includes('javascript:') || href.includes('#') || href.includes('login')) continue;
                    // Skip /career/ section navigation pages (e.g., /career/professionals, /career/working-at-hcc)
                    // These are career info pages, not job detail pages
                    var pathParts = new URL(href).pathname.split('/').filter(Boolean);
                    if (pathParts.length === 2 && pathParts[0] === 'career') {
                        var subpage = pathParts[1].toLowerCase();
                        if (['professionals', 'recent-graduates', 'working-at-hcc', 'current-opening',
                             'life-at', 'benefits', 'culture', 'values', 'why-join', 'about'].indexOf(subpage) >= 0) continue;
                    }

                    var title = (el.innerText || el.textContent || '').trim().split('\\n')[0].trim();
                    // Remove "[Job Description]" suffix
                    title = title.replace(/\\[Job\\s*Description\\]/gi, '').trim();
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (isGarbageTitle(title)) continue;

                    seen[href] = true;

                    var parent = el.closest('tr, div[class*="row"], div[class*="item"], li, article, div.card, div');
                    var location = '';
                    var dept = '';
                    if (parent) {
                        var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                        if (locEl && locEl !== el) location = locEl.innerText.trim();
                        var deptEl = parent.querySelector('[class*="department"], [class*="Department"]');
                        if (deptEl && deptEl !== el) dept = deptEl.innerText.trim();
                    }
                    results.push({title: title, url: href, location: location, date: '', department: dept, experience: ''});
                }

                // Strategy 2: Job/opening specific divs (only if Strategy 1 found nothing)
                if (results.length === 0) {
                    var jobDivs = document.querySelectorAll('div[class*="job"], div[class*="Job"], div[class*="opening"], div[class*="Opening"], div[class*="vacancy"], div[class*="Vacancy"]');
                    for (var i = 0; i < jobDivs.length; i++) {
                        var div = jobDivs[i];
                        var titleEl = div.querySelector('h2, h3, h4, h5, [class*="title"], [class*="Title"], [class*="designation"], [class*="position"]');
                        if (!titleEl) {
                            var linkEl = div.querySelector('a[href]');
                            if (linkEl) titleEl = linkEl;
                        }
                        if (!titleEl) continue;

                        var title = (titleEl.innerText || titleEl.textContent || '').trim().split('\\n')[0].trim();
                        var linkEl = div.querySelector('a[href]') || titleEl.closest('a');
                        var href = linkEl ? (linkEl.href || '') : '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (isGarbageTitle(title)) continue;
                        if (href && seen[href]) continue;
                        if (href) seen[href] = true;

                        var locEl = div.querySelector('[class*="location"], [class*="Location"], [class*="place"], [class*="city"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var deptEl = div.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="function"]');
                        var dept = deptEl ? deptEl.innerText.trim() : '';
                        var dateEl = div.querySelector('[class*="date"], [class*="Date"], [class*="posted"], time');
                        var date = dateEl ? dateEl.innerText.trim() : '';
                        var expEl = div.querySelector('[class*="experience"], [class*="Experience"], [class*="exp"]');
                        var exp = expEl ? expEl.innerText.trim() : '';

                        results.push({title: title, location: location, url: href, date: date, department: dept, experience: exp});
                    }
                }

                // Strategy 3: Card/accordion layout (common for construction companies)
                if (results.length === 0) {
                    var cards = document.querySelectorAll('div.card, div[class*="card"], div[class*="accordion"], div[class*="panel"], article, div[class*="listing"], div[class*="item"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="Title"], [class*="heading"]');
                        if (!titleEl) continue;
                        var title = titleEl.innerText.trim().split('\\n')[0];
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (isGarbageTitle(title)) continue;

                        var linkEl = card.querySelector('a[href]');
                        var href = linkEl ? (linkEl.href || '') : '';
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        if (href && (href.includes('javascript:') || href.includes('#') || href.includes('login'))) href = '';

                        var locEl = card.querySelector('[class*="location"], [class*="Location"], [class*="place"]');
                        var location = locEl ? locEl.innerText.trim() : '';
                        var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                        var dept = deptEl ? deptEl.innerText.trim() : '';
                        var expEl = card.querySelector('[class*="experience"], [class*="exp"]');
                        var exp = expEl ? expEl.innerText.trim() : '';

                        results.push({title: title, url: href, location: location, date: '', department: dept, experience: exp});
                    }
                }

                // Strategy 4: Table rows (common for corporate career pages)
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        if (row.querySelector('th')) continue;
                        var tds = row.querySelectorAll('td');
                        if (tds.length < 1) continue;

                        var link = row.querySelector('a[href]');
                        var title = '';
                        var href = '';

                        if (link) {
                            title = link.innerText.trim().split('\\n')[0];
                            href = link.href || '';
                        } else if (tds.length >= 1) {
                            title = tds[0].innerText.trim().split('\\n')[0];
                        }

                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (isGarbageTitle(title)) continue;
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;
                        if (href && (href.includes('javascript:') || href.includes('#') || href.includes('login'))) href = '';

                        var location = tds.length >= 2 ? tds[1].innerText.trim() : '';
                        var dept = tds.length >= 3 ? tds[2].innerText.trim() : '';
                        var exp = tds.length >= 4 ? tds[3].innerText.trim() : '';

                        results.push({title: title, url: href, location: location, date: '', department: dept, experience: exp});
                    }
                }

                // Strategy 5: Headings approach for static pages
                if (results.length === 0) {
                    var headings = document.querySelectorAll('h2, h3, h4');
                    for (var i = 0; i < headings.length; i++) {
                        var h = headings[i];
                        var title = h.innerText.trim().split('\\n')[0].trim();
                        if (!title || title.length < 5 || title.length > 200) continue;
                        if (isGarbageTitle(title)) continue;
                        var lower = title.toLowerCase();
                        if (lower.includes('our team') || lower.includes('why join') || lower.includes('benefits')) continue;

                        var linkEl = h.querySelector('a[href]') || (h.nextElementSibling ? h.nextElementSibling.querySelector('a[href*="apply"], a[href*="career"], a[href*="job"]') : null);
                        var href = linkEl ? (linkEl.href || '') : '';
                        var key = href || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        var parent = h.closest('div[class*="item"], div[class*="card"], div[class*="opening"], article, section');
                        var location = '';
                        var dept = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl) location = locEl.innerText.trim();
                            var deptEl = parent.querySelector('[class*="department"]');
                            if (deptEl) dept = deptEl.innerText.trim();
                        }

                        results.push({title: title, url: href, location: location, date: '', department: dept, experience: ''});
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                seen_keys = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    date = jdata.get('date', '').strip()
                    department = jdata.get('department', '').strip()
                    experience = jdata.get('experience', '').strip()

                    if not title or len(title) < 3:
                        continue

                    # Remove "[Job Description]" suffix from titles
                    title = title.replace('[Job Description]', '').strip()

                    # Filter garbage titles (page headings, navigation items)
                    lower_title = title.lower().strip()
                    garbage_patterns = [
                        'careers', 'career', 'home', 'about', 'contact', 'jobs',
                        'current openings', 'current opening', 'browse', 'search',
                        'apply', 'apply now', 'address', 'explore', 'newsletter',
                        'connect with us', 'contact us', 'terms', 'privacy',
                        'supplier portal', 'media room', 'investors',
                        'professionals', 'recent graduates', 'working at hcc'
                    ]
                    if any(lower_title == g for g in garbage_patterns):
                        continue
                    if len(title) > 150:
                        continue

                    key = url or title
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/career/' in url:
                        parts = url.split('/career/')[-1].split('/')
                        if parts[0] and parts[0] != 'current-opening':
                            job_id = parts[0]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': department, 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': experience,
                        'salary_range': '', 'remote_type': '', 'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                    page_url = driver.current_url
                    logger.info(f"Current URL: {page_url}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            next_selectors = [
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a.next'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.XPATH, '//a[contains(text(), ">")]'),
                (By.XPATH, '//a[contains(@title, "Next")]'),
                (By.XPATH, '//a[contains(text(), "Load More")]'),
                (By.XPATH, '//button[contains(text(), "Load More")]'),
            ]

            for sel_type, sel_val in next_selectors:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except:
                    continue

            # JS fallback for next page
            next_clicked = driver.execute_script("""
                var els = document.querySelectorAll('a, button');
                for (var i = 0; i < els.length; i++) {
                    var txt = (els[i].innerText || '').trim().toLowerCase();
                    var ariaLabel = (els[i].getAttribute('aria-label') || '').toLowerCase();
                    if (txt === 'next' || txt === 'next page' || txt === '>' || txt === '>>' || txt === 'load more' || ariaLabel === 'next') {
                        if (els[i].offsetParent !== null) {
                            els[i].click();
                            return true;
                        }
                    }
                }
                return false;
            """)
            if next_clicked:
                logger.info("Navigated to next page via JS fallback")
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
    scraper = HCCScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

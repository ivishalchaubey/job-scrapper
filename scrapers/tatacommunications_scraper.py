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

logger = setup_logger('tatacommunications_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class TataCommunicationsScraper:
    def __init__(self):
        self.company_name = 'Tata Communications'
        self.url = 'https://jobs.tatacommunications.com/'
        self.base_url = 'https://jobs.tatacommunications.com'

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

            # Flutter SPA needs extra time to initialize and render
            driver.get(self.url)
            time.sleep(20)

            # Log page state for debugging
            try:
                title = driver.title
                body_len = driver.execute_script('return document.body ? document.body.innerText.length : 0')
                logger.info(f"Page title: {title}, body text length: {body_len}")
            except:
                pass

            # Scroll extensively to trigger Flutter lazy loading
            for _ in range(8):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            # Try to navigate to a job listings view in the Flutter SPA
            # Flutter apps use hash routing (#/) - try clicking into "All Jobs" or "Search"
            self._navigate_to_jobs(driver)

            # Extract jobs from current page
            page_jobs = self._extract_jobs(driver)
            if page_jobs:
                all_jobs.extend(page_jobs)
                logger.info(f"Found {len(page_jobs)} jobs")

            # Try pagination if we found jobs
            if all_jobs:
                for page in range(1, max_pages):
                    if not self._go_to_next_page(driver):
                        break
                    time.sleep(5)
                    page_jobs = self._extract_jobs(driver)
                    if not page_jobs:
                        break
                    all_jobs.extend(page_jobs)
                    logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

            # If no jobs found via DOM, try text parsing as fallback
            if not all_jobs:
                logger.info("DOM extraction failed, trying text-based parsing")
                all_jobs = self._extract_jobs_from_text(driver)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _navigate_to_jobs(self, driver):
        """Try to navigate to the jobs listing within the Flutter SPA."""
        try:
            # Try clicking elements that might lead to job listings
            clicked = driver.execute_script("""
                // Look for clickable elements with job-related text
                var allEls = document.querySelectorAll('*');
                var targets = ['all jobs', 'view all', 'search jobs', 'job listings', 'open positions', 'browse jobs', 'explore'];
                for (var i = 0; i < allEls.length; i++) {
                    var el = allEls[i];
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text.length > 50) continue;
                    for (var t = 0; t < targets.length; t++) {
                        if (text === targets[t] || text.includes(targets[t])) {
                            el.click();
                            return true;
                        }
                    }
                }
                return false;
            """)
            if clicked:
                logger.info("Clicked job listing navigation element")
                time.sleep(8)
                # Scroll again after navigation
                for _ in range(5):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)
        except Exception as e:
            logger.debug(f"Navigation attempt: {str(e)}")

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

                // Strategy 1: Standard HTML selectors (in case Flutter renders standard elements)
                var cards = document.querySelectorAll('[class*="job-card"], [class*="jobCard"], [class*="job-listing"], [class*="position-card"]');
                if (cards.length === 0) cards = document.querySelectorAll('li[data-ph-at-id="job-listing"], div[data-ph-at-id="job-listing"]');
                if (cards.length === 0) cards = document.querySelectorAll('[class*="opening"], [class*="vacancy"]');

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var titleEl = card.querySelector('h1, h2, h3, h4, h5, [class*="title"], [class*="Title"]');
                    var locEl = card.querySelector('[class*="location"], [class*="Location"], [class*="city"]');
                    var linkEl = card.tagName === 'A' ? card : card.querySelector('a[href]');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title && linkEl) title = linkEl.innerText.trim().split('\\n')[0];
                    var location = locEl ? locEl.innerText.trim() : '';
                    var href = linkEl ? linkEl.href : '';
                    if (title && title.length > 2 && title.length < 200) {
                        var key = href || title;
                        if (!seen[key]) {
                            seen[key] = true;
                            results.push({title: title, location: location, url: href || '', date: ''});
                        }
                    }
                }

                // Strategy 2: Flutter accessibility tree - flt-semantics elements
                if (results.length === 0) {
                    var semNodes = document.querySelectorAll('flt-semantics, flt-semantics-container');
                    if (semNodes.length > 0) {
                        // Flutter renders accessible tree - look for role=link or role=button with job text
                        var roleLinks = document.querySelectorAll('[role="link"], [role="button"], [aria-label]');
                        for (var i = 0; i < roleLinks.length; i++) {
                            var el = roleLinks[i];
                            var label = el.getAttribute('aria-label') || el.innerText || '';
                            label = label.trim();
                            if (label.length < 5 || label.length > 200) continue;
                            // Skip navigation items
                            if (['home', 'menu', 'close', 'back', 'search', 'filter', 'login', 'sign in'].indexOf(label.toLowerCase()) >= 0) continue;
                            if (seen[label]) continue;
                            seen[label] = true;
                            results.push({title: label, location: '', url: '', date: ''});
                        }
                    }
                }

                // Strategy 3: Direct job links (any <a> with href patterns)
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="/job/"], a[href*="/job-"], a[href*="/jobs/"], a[href*="/position/"], a[href*="/vacancy/"], a[href*="/career/"], a[href*="/opening/"], a[href*="/requisition/"]');
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
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl && locEl !== el) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: url, location: location, date: ''});
                    }
                }

                // Strategy 4: Repeating container detection for Flutter HTML renderer
                if (results.length === 0) {
                    var classCounts = {};
                    var allEls = document.querySelectorAll('div[class], span[class], flt-clip[class]');
                    for (var i = 0; i < allEls.length; i++) {
                        var cls = allEls[i].className;
                        if (!cls || typeof cls !== 'string') continue;
                        classCounts[cls] = (classCounts[cls] || 0) + 1;
                    }
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
                            if (title.toLowerCase().includes('home') || title.toLowerCase().includes('menu') || title.toLowerCase().includes('copyright')) continue;
                            var location = '';
                            var jobId = '';
                            for (var l = 0; l < lines.length; l++) {
                                var match = lines[l].match(/Job\\s*ID\\s*[:#]?\\s*(\\d+)/i);
                                if (match) jobId = match[1];
                                if (lines[l].includes('India') || lines[l].includes('Karnataka') || lines[l].includes('Maharashtra') || lines[l].includes('Delhi') || lines[l].includes('Tamil Nadu') || lines[l].includes('Telangana')) {
                                    location = lines[l];
                                }
                            }
                            testResults.push({title: title, location: location, url: '', date: '', jobId: jobId});
                        }
                        if (testResults.length >= 3) {
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

                // Strategy 5: Extract all text blocks that look like job entries
                if (results.length === 0) {
                    // Find text nodes containing "Job ID" pattern
                    var allElements = document.querySelectorAll('*');
                    var jobIdPattern = /Job\\s*ID\\s*[:#]?\\s*(\\d+)/i;
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        if (el.children.length > 3) continue; // Skip containers with too many children
                        var text = (el.innerText || '').trim();
                        if (text.length < 5 || text.length > 300) continue;
                        var match = text.match(jobIdPattern);
                        if (!match) continue;
                        var jobId = match[1];
                        if (seen[jobId]) continue;
                        seen[jobId] = true;

                        // Walk up to find the job card container
                        var container = el;
                        for (var d = 0; d < 5; d++) {
                            if (container.parentElement && container.parentElement.innerText.length < 500) {
                                container = container.parentElement;
                            } else break;
                        }

                        var fullText = container.innerText.trim();
                        var lines = fullText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        var title = '';
                        var location = '';
                        for (var l = 0; l < lines.length; l++) {
                            if (lines[l].match(jobIdPattern)) continue;
                            if (!title && lines[l].length > 3 && lines[l].length < 200 && !lines[l].toLowerCase().includes('apply')) {
                                title = lines[l];
                            }
                            if (lines[l].includes(',') && (lines[l].includes('India') || lines[l].includes('Karnataka') || lines[l].includes('Maharashtra'))) {
                                location = lines[l];
                            }
                        }
                        if (!title) title = 'Job ID ' + jobId;
                        results.push({title: title, location: location, url: '', date: '', jobId: jobId});
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
                    job_id_str = jdata.get('jobId', '').strip()

                    if not title or len(title) < 3:
                        continue

                    dedup_key = job_id_str if job_id_str else title
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = job_id_str if job_id_str else hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/job/' in url:
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
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 1000) : ""')
                    logger.info(f"Page body preview: {body_text[:500]}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _extract_jobs_from_text(self, driver):
        """Fallback: parse page body text for job listings using regex patterns."""
        jobs = []
        try:
            body_text = driver.execute_script('return document.body ? document.body.innerText : ""')
            if not body_text or len(body_text) < 50:
                return jobs

            logger.info(f"Text parsing: body length = {len(body_text)}")
            lines = [l.strip() for l in body_text.split('\n') if l.strip()]

            # Pattern 1: Look for "Job ID" entries
            job_id_pattern = re.compile(r'Job\s*ID\s*[:#]?\s*(\d+)', re.IGNORECASE)
            indian_states = ['Karnataka', 'Maharashtra', 'Delhi', 'Tamil Nadu', 'Telangana',
                           'Uttar Pradesh', 'Gujarat', 'Rajasthan', 'West Bengal', 'Andhra Pradesh',
                           'Kerala', 'Punjab', 'Haryana', 'Madhya Pradesh', 'Bihar', 'Odisha',
                           'Jharkhand', 'Assam', 'Goa', 'Uttarakhand', 'India']

            seen_ids = set()
            i = 0
            while i < len(lines):
                match = job_id_pattern.search(lines[i])
                if match:
                    job_id = match.group(1)
                    if job_id in seen_ids:
                        i += 1
                        continue
                    seen_ids.add(job_id)

                    # Look around for title and location
                    title = ''
                    location = ''
                    context = lines[max(0, i-3):min(len(lines), i+5)]
                    for ctx_line in context:
                        if job_id_pattern.search(ctx_line):
                            continue
                        if any(state in ctx_line for state in indian_states):
                            if not location:
                                location = ctx_line
                        elif not title and len(ctx_line) > 3 and len(ctx_line) < 200:
                            if ctx_line.lower() not in ['apply', 'view', 'details', 'apply now', 'view details']:
                                title = ctx_line

                    if not title:
                        title = f'Job ID {job_id}'

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': self.url, 'location': location,
                        'department': '', 'employment_type': '', 'description': '',
                        'posted_date': '', 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })
                i += 1

            # Pattern 2: If no Job IDs found, try job title keyword matching
            if not jobs:
                job_keywords = ['manager', 'engineer', 'analyst', 'executive', 'lead', 'head',
                              'specialist', 'associate', 'developer', 'architect', 'consultant',
                              'director', 'officer', 'coordinator', 'administrator']
                seen_titles = set()
                for idx, line in enumerate(lines):
                    if len(line) < 5 or len(line) > 200:
                        continue
                    line_lower = line.lower()
                    is_job = any(kw in line_lower for kw in job_keywords)
                    if not is_job:
                        continue
                    # Skip nav/filter items
                    if any(skip in line_lower for skip in ['filter', 'sort', 'search', 'menu', 'home', 'copyright', 'apply now']):
                        continue
                    if line in seen_titles:
                        continue
                    seen_titles.add(line)

                    location = ''
                    for j in range(idx + 1, min(idx + 4, len(lines))):
                        if any(state in lines[j] for state in indian_states):
                            location = lines[j]
                            break

                    job_id = hashlib.md5(line.encode()).hexdigest()[:12]
                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': line,
                        'apply_url': self.url, 'location': location,
                        'department': '', 'employment_type': '', 'description': '',
                        'posted_date': '', 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })

            if jobs:
                logger.info(f"Text parsing found {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"Text parsing error: {str(e)}")
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
    scraper = TataCommunicationsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

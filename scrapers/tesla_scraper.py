# STATUS: BLOCKED - Akamai Bot Manager on tesla.com/careers (tested 2026-02-22)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
from datetime import datetime
from pathlib import Path
import os
import stat

try:
    import requests
except ImportError:
    requests = None

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('tesla_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class TeslaScraper:
    def __init__(self):
        self.company_name = 'Tesla'
        # Tesla uses Akamai Bot Manager which blocks headless Chrome aggressively
        self.url = 'https://www.tesla.com/careers/search/?country=IN'

    def setup_driver(self):
        """Set up Chrome driver with maximum anti-detection for Akamai bypass."""
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        # Short UA in options, full UA via CDP (anti-detection pattern)
        chrome_options.add_argument('--user-agent=AppleWebKit/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.add_argument('--ignore-certificate-errors')
        # Extra stealth flags for Akamai bypass
        chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        chrome_options.add_argument('--disable-site-isolation-trials')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-features=CrossSiteDocumentBlockingIfIsolating')
        chrome_options.add_argument('--disable-features=CrossSiteDocumentBlockingAlways')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-ipc-flooding-protection')
        chrome_options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        driver_path = CHROMEDRIVER_PATH
        driver_path_obj = Path(driver_path)
        if driver_path_obj.name != 'chromedriver':
            parent = driver_path_obj.parent
            actual_driver = parent / 'chromedriver'
            if actual_driver.exists():
                driver_path = str(actual_driver)

        try:
            current_permissions = os.stat(driver_path).st_mode
            os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except:
            pass

        try:
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)

        # Full UA via CDP for anti-detection
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            'userAgent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'acceptLanguage': 'en-US,en;q=0.9',
            'platform': 'macOS',
        })

        # Comprehensive stealth injection before any page loads
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                // Remove webdriver flag
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                delete navigator.__proto__.webdriver;

                // Chrome runtime
                window.chrome = {
                    runtime: {},
                    loadTimes: function() { return {} },
                    csi: function() { return {} },
                };

                // Languages
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                Object.defineProperty(navigator, 'language', {get: () => 'en-US'});

                // Plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        var p = [
                            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                            {name: 'Native Client', filename: 'internal-nacl-plugin'},
                        ];
                        p.length = 3;
                        return p;
                    }
                });

                // Hardware
                Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

                // Permissions
                var origQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = function(p) {
                    return p.name === 'notifications'
                        ? Promise.resolve({state: Notification.permission})
                        : origQuery.call(navigator.permissions, p);
                };
            '''
        })

        return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Tesla careers page with retry and anti-detection."""
        jobs = []
        driver = None

        # Primary method: Try Tesla's internal API directly
        if requests is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("Tesla API returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.warning(f"Tesla API failed: {str(e)}, falling back to Selenium")

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Try loading with retries
            page_loaded = False
            for attempt in range(3):
                try:
                    logger.info(f"Loading Tesla careers (attempt {attempt + 1}/3)...")
                    driver.get(self.url)
                    # Long wait for Akamai JS challenge to resolve
                    time.sleep(15)

                    page_source = driver.page_source
                    title = driver.title

                    # Check if Akamai blocked us
                    if 'Access Denied' in page_source:
                        logger.warning(f"Attempt {attempt + 1}: Akamai Access Denied")
                        if attempt < 2:
                            time.sleep(10)
                            continue
                    elif 'sec-if-cpt-container' in page_source and len(page_source) < 5000:
                        # Akamai JS challenge page - wait for it to resolve
                        logger.info(f"Attempt {attempt + 1}: Akamai challenge detected, waiting...")
                        time.sleep(20)
                        page_source = driver.page_source
                        if 'Access Denied' in page_source or len(page_source) < 5000:
                            logger.warning("Challenge did not resolve")
                            if attempt < 2:
                                time.sleep(10)
                                continue
                        else:
                            page_loaded = True
                            break
                    else:
                        # Page loaded successfully
                        page_loaded = True
                        logger.info(f"Page loaded: title='{title}', source_len={len(page_source)}")
                        break

                except Exception as nav_err:
                    logger.warning(f"Navigation attempt {attempt + 1} failed: {str(nav_err)}")
                    if attempt < 2:
                        time.sleep(5)
                    else:
                        raise

            if not page_loaded:
                logger.error(
                    "Tesla careers page blocked by Akamai Bot Manager. "
                    "This site requires a non-headless browser or specialized anti-bot bypass. "
                    "The URL is correct but Akamai blocks automated access."
                )
                return jobs

            # Wait for dynamic content
            time.sleep(12)

            # Scroll to trigger lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try to detect job listings
            short_wait = WebDriverWait(driver, 8)
            try:
                short_wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "a[href*='/job/'], div[class*='listing'], tr[class*='result'], "
                    "li[class*='job'], [data-testid], article"
                )))
                logger.info("Job listings loaded")
            except:
                logger.warning("Timeout waiting for job listings")

            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")
                page_jobs = self._scrape_page(driver)
                jobs.extend(page_jobs)
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(4)
                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page."""
        try:
            next_page_num = current_page + 1
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            next_page_selectors = [
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'button[aria-label="Go to page {next_page_num}"]'),
                (By.XPATH, '//button[@aria-label="Go to next page"]'),
                (By.XPATH, '//button[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'button.pagination-next'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Clicked next page button")
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver):
        """Scrape jobs from current page using JS-first extraction."""
        jobs = []

        try:
            logger.info("Extracting jobs via JavaScript...")
            time.sleep(3)

            # STRATEGY 1: JavaScript-first extraction for Tesla React SPA
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy A: Tesla-specific selectors
                // Tesla uses React with specific data attributes and class patterns
                var teslaSelectors = [
                    'a[href*="/careers/search/job/"]',
                    'a[href*="/job/"]',
                    'li[class*="result"] a',
                    'div[class*="result"] a',
                    'div[class*="listing"] a',
                    'div[class*="job-card"] a',
                    'a[data-testid]',
                    'div[data-testid] a'
                ];

                for (var s = 0; s < teslaSelectors.length; s++) {
                    var elems = document.querySelectorAll(teslaSelectors[s]);
                    if (elems.length > 0) {
                        for (var i = 0; i < elems.length; i++) {
                            var text = (elems[i].innerText || '').trim();
                            var href = elems[i].href || '';
                            if (text.length < 3 || text.length > 200) continue;
                            var title = text.split('\n')[0].trim();
                            if (!title || title.length < 3) continue;
                            var key = title + '|' + href;
                            if (seen[key]) continue;
                            seen[key] = true;

                            // Get full text from parent for location extraction
                            var fullText = text;
                            var parent = elems[i].closest('li, div[class*="result"], div[class*="listing"], div[class*="card"]');
                            if (parent) fullText = (parent.innerText || '').trim();

                            results.push({
                                title: title,
                                url: href,
                                fullText: fullText,
                                type: 'tesla'
                            });
                        }
                        if (results.length > 0) break;
                    }
                }

                // Strategy B: Generic job link detection
                if (results.length === 0) {
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            var lhref = href.toLowerCase();
                            if (lhref.includes('/job/') || lhref.includes('/careers/search/job/') ||
                                lhref.includes('/Detail/') || lhref.includes('/position/') ||
                                lhref.includes('/requisition/')) {
                                var title = text.split('\n')[0].trim();
                                var key = title + '|' + href;
                                if (seen[key]) return;
                                seen[key] = true;
                                results.push({
                                    title: title,
                                    url: href,
                                    fullText: text,
                                    type: 'link'
                                });
                            }
                        }
                    });
                }

                // Strategy C: Job card elements by class pattern
                if (results.length === 0) {
                    var cardSelectors = [
                        'li[class*="result"]',
                        'li[class*="job"]',
                        'div[class*="listing"]',
                        'div[class*="job-card"]',
                        'article',
                        'div.item-block',
                        'a.item-block',
                    ];
                    for (var s2 = 0; s2 < cardSelectors.length; s2++) {
                        var cards = document.querySelectorAll(cardSelectors[s2]);
                        if (cards.length >= 2) {
                            cards.forEach(function(card) {
                                var text = (card.innerText || '').trim();
                                if (text.length > 10 && text.length < 500) {
                                    var title = text.split('\n')[0].trim();
                                    var link = card.querySelector('a[href]');
                                    var url = link ? link.href : '';
                                    if (link && link.innerText) title = link.innerText.trim().split('\n')[0];
                                    var key = title + '|' + url;
                                    if (seen[key]) return;
                                    seen[key] = true;
                                    results.push({
                                        title: title,
                                        url: url,
                                        fullText: text,
                                        type: 'card'
                                    });
                                }
                            });
                            break;
                        }
                    }
                }

                // Strategy D: Repeated sibling elements pattern
                if (results.length === 0) {
                    var containers = document.querySelectorAll('ul, div[class*="list"], div[class*="result"], section, main');
                    for (var c = 0; c < containers.length; c++) {
                        var children = containers[c].children;
                        if (children.length >= 3 && children.length <= 200) {
                            var hasLinks = 0;
                            for (var j = 0; j < Math.min(children.length, 5); j++) {
                                if (children[j].querySelector('a[href]')) hasLinks++;
                            }
                            if (hasLinks >= 2) {
                                for (var k = 0; k < children.length; k++) {
                                    var ct = (children[k].innerText || '').trim();
                                    if (ct.length < 10 || ct.length > 500) continue;
                                    var cTitle = ct.split('\n')[0].trim();
                                    if (cTitle.length < 3) continue;
                                    var cLink = children[k].querySelector('a[href]');
                                    var cUrl = cLink ? cLink.href : '';
                                    if (cLink && cLink.innerText) cTitle = cLink.innerText.trim().split('\n')[0];
                                    var cKey = cTitle + '|' + cUrl;
                                    if (seen[cKey]) continue;
                                    seen[cKey] = true;
                                    results.push({title: cTitle, url: cUrl, fullText: ct, type: 'sibling'});
                                }
                                if (results.length >= 3) break;
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JavaScript extraction found {len(js_jobs)} potential jobs")
                seen = set()
                for item in js_jobs:
                    title = item.get('title', '')
                    url = item.get('url', '')
                    full_text = item.get('fullText', '')

                    if not title or len(title) < 3 or title in seen:
                        continue

                    # Skip navigation elements
                    exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy',
                               'terms', 'cookie', 'blog', 'menu', 'filter', 'back']
                    if any(w in title.lower() for w in exclude):
                        continue

                    seen.add(title)

                    # Parse location and details
                    location = ''
                    city = ''
                    state = ''
                    employment_type = ''
                    experience = ''

                    if full_text:
                        lines = [l.strip() for l in full_text.split('\n') if l.strip()]
                        for line in lines[1:]:
                            line_lower = line.lower()
                            if not location and any(loc in line_lower for loc in [
                                'mumbai', 'delhi', 'bangalore', 'chennai', 'hyderabad',
                                'kolkata', 'pune', 'gurgaon', 'india', 'noida'
                            ]):
                                location = line
                                city, state, _ = self.parse_location(location)
                            elif not employment_type and any(t in line_lower for t in [
                                'full-time', 'full time', 'part-time', 'part time',
                                'contract', 'intern'
                            ]):
                                employment_type = line

                    # Generate job ID
                    job_id = ''
                    if url:
                        try:
                            parts = url.split('/Detail/')
                            if len(parts) > 1:
                                job_id = parts[1].split('/')[0]
                            else:
                                # Extract from /job/ URL pattern
                                parts = url.split('/job/')
                                if len(parts) > 1:
                                    job_id = parts[1].split('/')[0].split('?')[0]
                        except:
                            pass
                    if not job_id:
                        job_id = hashlib.md5((title + url).encode()).hexdigest()[:12]

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': '',
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job_data)
                    logger.info(f"Extracted: {title}")

            # STRATEGY 2: Selenium selector-based fallback
            if not jobs:
                logger.info("JS extraction found nothing, trying selector-based approach...")
                job_elements = []

                selectors = [
                    "a[href*='/job/']",
                    "a[href*='/Detail/']",
                    "div[class*='listing']",
                    "li[class*='job']",
                    "li[class*='result']",
                    "div.item-block",
                    "a.item-block",
                    "a[href*='/careers/']",
                    "div[class*='job']",
                ]

                for sel in selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, sel)
                        if elements and len(elements) >= 2:
                            job_elements = elements
                            logger.info(f"Found {len(elements)} elements via: {sel}")
                            break
                    except:
                        continue

                for idx, elem in enumerate(job_elements):
                    try:
                        job_url = elem.get_attribute('href') or ''
                        if not job_url:
                            try:
                                link = elem.find_element(By.TAG_NAME, 'a')
                                job_url = link.get_attribute('href') or ''
                            except:
                                pass

                        text = elem.text.strip()
                        if not text or len(text) < 3:
                            continue

                        title = text.split('\n')[0].strip()
                        if not title or len(title) < 3:
                            continue

                        job_id = f"tesla_{idx}"
                        if job_url:
                            try:
                                parts = job_url.split('/')
                                job_id = parts[-1].split('?')[0] or job_id
                            except:
                                pass

                        location = ''
                        city = ''
                        state = ''
                        lines = text.split('\n')
                        for line in lines[1:]:
                            if any(loc in line for loc in ['Mumbai', 'Delhi', 'Bangalore', 'Chennai',
                                                           'Hyderabad', 'Kolkata', 'Pune', 'India']):
                                location = line.strip()
                                city, state, _ = self.parse_location(location)
                                break

                        job_data = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': 'India',
                            'employment_type': '',
                            'department': '',
                            'apply_url': job_url if job_url else self.url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        jobs.append(job_data)
                        logger.info(f"Extracted: {title}")
                    except Exception as e:
                        logger.debug(f"Error extracting element {idx}: {str(e)}")
                        continue

            if not jobs:
                logger.warning(
                    "No jobs extracted. Tesla uses Akamai Bot Manager which blocks "
                    "headless Chrome. The URL is valid but requires non-headless browser access."
                )
                # Log diagnostic info
                try:
                    body = driver.execute_script('return document.body ? document.body.innerText : ""')
                    logger.info(f"Page body (first 300): {body[:300]}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error in _scrape_page: {str(e)}")

        return jobs

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job detail page."""
        details = {}

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(5)

            desc_selectors = [
                (By.CSS_SELECTOR, 'div.job-description'),
                (By.CSS_SELECTOR, 'div[id*="jobdescription"]'),
                (By.CSS_SELECTOR, 'div[class*="description"]'),
                (By.XPATH, '//div[contains(@id, "description")]'),
            ]

            for selector_type, selector_value in desc_selectors:
                try:
                    desc_elem = driver.find_element(selector_type, selector_value)
                    if desc_elem and desc_elem.text.strip():
                        details['description'] = desc_elem.text.strip()[:2000]
                        break
                except:
                    continue

            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass

        return details

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Try Tesla's internal career API to bypass Akamai."""
        all_jobs = []

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://www.tesla.com/careers/search/?country=IN',
            'Origin': 'https://www.tesla.com',
        }

        # Try multiple Tesla API patterns
        api_patterns = [
            # Pattern 1: Tesla career search API
            ('GET', 'https://www.tesla.com/careers/api/search?country=IN&type=3'),
            ('GET', 'https://www.tesla.com/careers/api/search/?country=IN'),
            ('GET', 'https://www.tesla.com/cua-api/careers/search?country=IN&type=3'),
            ('GET', 'https://www.tesla.com/cua-api/careers/search/?country=IN'),
            # Pattern 2: Greenhouse API (Tesla may use Greenhouse)
            ('GET', 'https://boards-api.greenhouse.io/v1/boards/tesla/jobs?location=India'),
            ('GET', 'https://api.greenhouse.io/v1/boards/tesla/jobs?location=India'),
            # Pattern 3: Tesla JSON feed
            ('GET', 'https://www.tesla.com/careers/search/job?country=IN&format=json'),
        ]

        for method, api_url in api_patterns:
            try:
                logger.info(f"Trying Tesla API: {api_url[:80]}...")
                if method == 'GET':
                    response = requests.get(api_url, headers=headers, timeout=30, allow_redirects=True)
                else:
                    response = requests.post(api_url, headers=headers, json={}, timeout=30, allow_redirects=True)

                if response.status_code == 200:
                    try:
                        data = response.json()
                    except:
                        logger.warning(f"API returned non-JSON response")
                        continue

                    # Try various JSON structures
                    items = []
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        for key in ['results', 'jobs', 'data', 'items', 'postings', 'records']:
                            if key in data and isinstance(data[key], list):
                                items = data[key]
                                break
                        if not items and 'count' in data:
                            # May have nested structure
                            for key in data:
                                if isinstance(data[key], list) and len(data[key]) > 0:
                                    items = data[key]
                                    break

                    if items:
                        logger.info(f"Tesla API returned {len(items)} items")
                        for item in items:
                            try:
                                if not isinstance(item, dict):
                                    continue
                                title = item.get('title', '') or item.get('name', '') or item.get('job_title', '') or item.get('jobTitle', '')
                                if not title:
                                    continue

                                location = item.get('location', '') or item.get('locationName', '') or item.get('location_name', '')
                                if isinstance(location, dict):
                                    location = location.get('name', '') or location.get('city', '')

                                job_id = str(item.get('id', '') or item.get('job_id', '') or item.get('requisition_id', ''))
                                if not job_id:
                                    job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                                job_url = item.get('url', '') or item.get('absolute_url', '') or item.get('apply_url', '')
                                if not job_url and job_id:
                                    job_url = f"https://www.tesla.com/careers/search/job/{job_id}"

                                posted_date = item.get('created_at', '') or item.get('posted_date', '') or item.get('updated_at', '')

                                city, state, _ = self.parse_location(location)

                                job_data = {
                                    'external_id': self.generate_external_id(job_id, self.company_name),
                                    'company_name': self.company_name,
                                    'title': title,
                                    'description': item.get('description', '') or item.get('content', ''),
                                    'location': location,
                                    'city': city,
                                    'state': state,
                                    'country': 'India',
                                    'employment_type': item.get('employment_type', '') or item.get('type', ''),
                                    'department': item.get('department', '') or item.get('team', ''),
                                    'apply_url': job_url if job_url else self.url,
                                    'posted_date': posted_date,
                                    'job_function': item.get('category', '') or item.get('function', ''),
                                    'experience_level': '',
                                    'salary_range': '',
                                    'remote_type': '',
                                    'status': 'active'
                                }
                                all_jobs.append(job_data)
                                logger.info(f"API extracted: {title} | {location}")
                            except Exception as e:
                                logger.error(f"Error processing API item: {str(e)}")
                                continue

                        if all_jobs:
                            return all_jobs
                else:
                    logger.warning(f"Tesla API returned status {response.status_code}")
            except Exception as e:
                logger.warning(f"API pattern failed: {str(e)}")
                continue

        # Try Selenium-assisted API approach - use Selenium to get cookies, then hit API
        try:
            logger.info("Trying Selenium-assisted API approach for Tesla")
            driver = self.setup_driver()
            driver.get('https://www.tesla.com/careers/search/?country=IN')
            time.sleep(15)

            # Get cookies from browser
            selenium_cookies = driver.get_cookies()
            cookie_dict = {c['name']: c['value'] for c in selenium_cookies}
            logger.info(f"Got {len(cookie_dict)} cookies from Selenium")

            # Try fetching the page JSON with these cookies
            session = requests.Session()
            for name, value in cookie_dict.items():
                session.cookies.set(name, value)

            # Try the main page URL with JSON accept header
            json_headers = headers.copy()
            json_headers['Accept'] = 'application/json, text/html'

            for api_url in ['https://www.tesla.com/careers/api/search?country=IN',
                           'https://www.tesla.com/cua-api/careers/search?country=IN']:
                try:
                    response = session.get(api_url, headers=json_headers, timeout=30)
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            items = []
                            if isinstance(data, list):
                                items = data
                            elif isinstance(data, dict):
                                for key in ['results', 'jobs', 'data', 'items']:
                                    if key in data and isinstance(data[key], list):
                                        items = data[key]
                                        break
                            if items:
                                logger.info(f"Selenium-assisted API got {len(items)} items")
                                for item in items:
                                    if not isinstance(item, dict):
                                        continue
                                    title = item.get('title', '') or item.get('name', '')
                                    if not title:
                                        continue
                                    location = item.get('location', '')
                                    if isinstance(location, dict):
                                        location = location.get('name', '')
                                    job_id = str(item.get('id', '')) or hashlib.md5(title.encode()).hexdigest()[:12]
                                    job_url = item.get('url', '') or item.get('absolute_url', '')
                                    if not job_url:
                                        job_url = f"https://www.tesla.com/careers/search/job/{job_id}"
                                    city, state, _ = self.parse_location(location)
                                    all_jobs.append({
                                        'external_id': self.generate_external_id(job_id, self.company_name),
                                        'company_name': self.company_name,
                                        'title': title,
                                        'description': '', 'location': location,
                                        'city': city, 'state': state, 'country': 'India',
                                        'employment_type': '', 'department': '',
                                        'apply_url': job_url if job_url else self.url,
                                        'posted_date': '', 'job_function': '',
                                        'experience_level': '', 'salary_range': '',
                                        'remote_type': '', 'status': 'active'
                                    })
                                if all_jobs:
                                    driver.quit()
                                    return all_jobs
                        except:
                            pass
                except:
                    continue

            driver.quit()
        except Exception as e:
            logger.warning(f"Selenium-assisted API failed: {str(e)}")

        return all_jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country."""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'


if __name__ == "__main__":
    scraper = TeslaScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

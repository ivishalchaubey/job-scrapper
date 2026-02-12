from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import traceback
import os
import stat
from datetime import datetime
from pathlib import Path

try:
    import requests as req_lib
except ImportError:
    req_lib = None


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('ibm_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class IBMScraper:
    def __init__(self):
        self.company_name = 'IBM'
        # IBM careers portal with India filter
        self.url = 'https://careers.ibm.com/job-search/?search=india'
        # IBM uses an Elasticsearch-based search API on www-api.ibm.com
        self.api_url = 'https://www-api.ibm.com/search/api/v2'
        self.base_job_url = 'https://careers.ibm.com/careers/JobDetail'
        # Fallback URL for Selenium methods (the new IBM careers search page)
        self.selenium_url = 'https://www.ibm.com/careers/search?q=india'

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

        driver_path = CHROMEDRIVER_PATH
        if not os.path.exists(driver_path):
            logger.warning(f"Fresh chromedriver not found at {driver_path}, trying system chromedriver")
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()
            if 'chromedriver-mac-arm64' in driver_path and not driver_path.endswith('chromedriver'):
                driver_dir = os.path.dirname(driver_path)
                actual_driver = os.path.join(driver_dir, 'chromedriver')
                if os.path.exists(actual_driver):
                    driver_path = actual_driver

        try:
            current_permissions = os.stat(driver_path).st_mode
            os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            logger.warning(f"Could not set permissions on chromedriver: {str(e)}")

        try:
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"Service driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs - try API first, then Selenium-based API interception, then pure Selenium."""
        all_jobs = []

        # Primary method: IBM Careers API via requests
        if req_lib is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("Direct API returned 0 jobs, trying Selenium-based API interception")
            except Exception as e:
                logger.warning(f"Direct API failed: {str(e)}, trying Selenium-based API interception")

        # Secondary method: Use Selenium to intercept XHR and extract job data from rendered page
        try:
            api_jobs = self._scrape_via_selenium_xhr(max_pages)
            if api_jobs:
                logger.info(f"Selenium XHR interception returned {len(api_jobs)} jobs")
                return api_jobs
            else:
                logger.warning("Selenium XHR returned 0 jobs, falling back to pure Selenium")
        except Exception as e:
            logger.warning(f"Selenium XHR failed: {str(e)}, falling back to pure Selenium")

        # Fallback: Selenium-based scraping
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape IBM jobs using the www-api.ibm.com Elasticsearch search API."""
        all_jobs = []
        page_size = 20
        max_results = max_pages * page_size

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Origin': 'https://www.ibm.com',
            'Referer': 'https://www.ibm.com/careers/search?q=india',
        }

        offset = 0
        while offset < max_results:
            try:
                payload = {
                    "appId": "careers",
                    "scopes": ["careers2"],
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "simple_query_string": {
                                        "query": "india",
                                        "fields": [
                                            "keywords^1", "body^1", "url^2",
                                            "description^2", "h1s_content^2",
                                            "title^3", "field_text_01"
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    "from": offset,
                    "size": page_size,
                    "_source": [
                        "url", "title", "description",
                        "field_text_01",     # Job ID
                        "field_keyword_05",  # Location
                        "field_keyword_08",  # Department/Category
                        "field_keyword_17",  # Work type (Remote/Hybrid/Office)
                    ],
                    "sort": [{"_score": {"order": "desc"}}]
                }

                logger.info(f"Fetching IBM API page from={offset}, size={page_size}")
                response = req_lib.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=30,
                )

                if response.status_code != 200:
                    logger.warning(f"IBM API returned status {response.status_code}")
                    break

                data = response.json()
                total = data.get('hits', {}).get('total', {}).get('value', 0)
                hits = data.get('hits', {}).get('hits', [])

                if offset == 0:
                    logger.info(f"IBM API total results: {total}")

                if not hits:
                    logger.info(f"No more jobs at offset {offset}")
                    break

                for hit in hits:
                    source = hit.get('_source', {})
                    job_data = self._parse_api_job(source)
                    if job_data:
                        all_jobs.append(job_data)

                offset += page_size

                # Don't exceed total available
                if offset >= total:
                    break

            except Exception as e:
                logger.error(f"IBM API pagination failed at offset {offset}: {str(e)}")
                break

        logger.info(f"Total jobs from API: {len(all_jobs)}")
        return all_jobs

    def _parse_api_job(self, source):
        """Parse a single job from the IBM Elasticsearch API _source into standard format."""
        if not isinstance(source, dict):
            return None

        title = source.get('title', '')
        if not title or len(title) < 3:
            return None

        # Job ID from field_text_01
        job_id = source.get('field_text_01', '')
        if not job_id:
            job_id = f"ibm_{hashlib.md5(title.encode()).hexdigest()[:12]}"

        # URL - API returns full URLs like https://careers.ibm.com/careers/JobDetail?jobId=88277
        job_url = source.get('url', '')
        if not job_url and job_id:
            job_url = f"{self.base_job_url}?jobId={job_id}"
        if job_url and not job_url.startswith('http'):
            job_url = f"https://careers.ibm.com{job_url}"

        # Location from field_keyword_05
        location = source.get('field_keyword_05', '') or 'India'

        # Department from field_keyword_08
        department = source.get('field_keyword_08', '')

        # Remote type from field_keyword_17 (Remote/Hybrid/Office)
        remote_type = source.get('field_keyword_17', '')

        # Description
        description = (source.get('description', '') or '')[:2000]

        city, state, country = self.parse_location(location)

        return {
            'external_id': self.generate_external_id(str(job_id), self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': description,
            'location': location,
            'city': city,
            'state': state,
            'country': country,
            'employment_type': '',
            'department': department,
            'apply_url': job_url,
            'posted_date': '',
            'job_function': '',
            'experience_level': '',
            'salary_range': '',
            'remote_type': remote_type,
            'status': 'active'
        }

    def _scrape_via_selenium_xhr(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Use Selenium to load IBM careers page, intercept XHR, and extract job data."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()

            # Set up XHR interception before loading the page
            driver.execute_cdp_cmd('Network.enable', {})

            # Install a performance log listener to capture network requests
            logger.info("Loading IBM careers page with XHR interception...")

            # Navigate to the new IBM careers search page (old careers.ibm.com returns 404)
            driver.get(self.selenium_url)

            # Wait for SPA to fully render and make XHR calls
            time.sleep(20)

            # Scroll to trigger lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            # Try to extract job data from the rendered page using JavaScript
            # The IBM page renders jobs even if we can't find the API - extract from DOM
            js_extract = """
                var jobs = [];
                // Try various selectors that IBM might use
                var selectors = [
                    '[data-testid*="job"]',
                    '[class*="job-card"]',
                    '[class*="JobCard"]',
                    '[class*="search-result"]',
                    'article',
                    '.job-listing',
                    '[role="listitem"]',
                    'li[class*="result"]',
                    'div[class*="card"]',
                ];

                for (var i = 0; i < selectors.length; i++) {
                    var cards = document.querySelectorAll(selectors[i]);
                    if (cards.length >= 3) {
                        cards.forEach(function(card) {
                            var links = card.querySelectorAll('a[href]');
                            var title = '';
                            var url = '';
                            var location = '';

                            for (var j = 0; j < links.length; j++) {
                                var link = links[j];
                                var href = link.href || '';
                                var text = (link.innerText || '').trim();
                                if (text.length > 5 && text.length < 200 && href.length > 10) {
                                    if (href.includes('/job/') || href.includes('/job-') || href.includes('JobDetail') || href.includes('jobId')) {
                                        title = text;
                                        url = href;
                                        break;
                                    }
                                }
                            }

                            if (!title) {
                                var headings = card.querySelectorAll('h1, h2, h3, h4, a');
                                for (var k = 0; k < headings.length; k++) {
                                    var t = (headings[k].innerText || '').trim();
                                    if (t.length > 5 && t.length < 200) {
                                        title = t;
                                        if (headings[k].href) url = headings[k].href;
                                        break;
                                    }
                                }
                            }

                            // Find location text
                            var allText = (card.innerText || '').split('\\n');
                            for (var m = 0; m < allText.length; m++) {
                                var line = allText[m].trim();
                                if (line.includes('India') || line.includes('Bangalore') ||
                                    line.includes('Bengaluru') || line.includes('Hyderabad') ||
                                    line.includes('Mumbai') || line.includes('Delhi') ||
                                    line.includes('Pune') || line.includes('Chennai')) {
                                    location = line;
                                    break;
                                }
                            }

                            if (title && title.length > 5) {
                                jobs.push({title: title, url: url || '', location: location || ''});
                            }
                        });
                        if (jobs.length > 0) break;
                    }
                }

                // If no structured cards found, try all links with job-related URLs
                if (jobs.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    var seen = {};
                    allLinks.forEach(function(link) {
                        var text = (link.innerText || '').trim().split('\\n')[0].trim();
                        var href = link.href || '';
                        if (text.length > 5 && text.length < 200 && !seen[text]) {
                            var lhref = href.toLowerCase();
                            if (lhref.includes('/job/') || lhref.includes('/job-') ||
                                lhref.includes('jobdetail') || lhref.includes('reqid') ||
                                lhref.includes('jobid')) {
                                var exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie'];
                                var skip = false;
                                for (var e = 0; e < exclude.length; e++) {
                                    if (text.toLowerCase().includes(exclude[e])) { skip = true; break; }
                                }
                                if (!skip) {
                                    seen[text] = true;
                                    jobs.push({title: text, url: href, location: ''});
                                }
                            }
                        }
                    });
                }

                return jobs;
            """

            js_jobs = driver.execute_script(js_extract)

            if js_jobs:
                logger.info(f"Selenium XHR: extracted {len(js_jobs)} jobs from rendered page")
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    url = job_data.get('url', '')
                    location = job_data.get('location', '') or 'India'

                    if not title or len(title) < 5:
                        continue

                    job_id = f"ibm_{idx}"
                    if url and 'jobId=' in url:
                        job_id = url.split('jobId=')[-1].split('&')[0]
                    elif url and '/job/' in url:
                        job_id = url.split('/job/')[-1].split('?')[0].split('/')[0]
                    elif url:
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    if not url:
                        url = self.url

                    city, state, country = self.parse_location(location)

                    all_jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': '',
                        'apply_url': url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("Selenium XHR: no jobs found in rendered page")

        except Exception as e:
            logger.error(f"Selenium XHR failed: {str(e)}")
            logger.error(traceback.format_exc())
        finally:
            if driver:
                driver.quit()

        logger.info(f"Selenium XHR total: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: scrape IBM jobs using Selenium with extended waits."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting Selenium scrape for {self.company_name}")
            driver = self.setup_driver()

            driver.get(self.selenium_url)

            short_wait = WebDriverWait(driver, 5)

            # Extended SPA rendering wait - IBM pages need longer
            time.sleep(15)

            # Extended scrolling to trigger lazy loading
            for _ in range(8):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            # Short wait with IBM-specific selectors
            try:
                short_wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "a[href*='JobDetail'], a[href*='jobId'], a[href*='/job/'], div.bx--card, div[class*='job-card'], li[class*='result']"
                )))
                logger.info("Job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for job listings: {str(e)}")

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
                    time.sleep(3)

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs via Selenium from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            logger.error(traceback.format_exc())

        finally:
            if driver:
                driver.quit()

        return jobs

    def _go_to_next_page(self, driver, current_page):
        try:
            next_page_selectors = [
                (By.XPATH, '//a[@rel="next"]'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.XPATH, '//button[@aria-label="Next page"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, '.pager-next a'),
                (By.CSS_SELECTOR, '[aria-label*="Next"]'),
                (By.CSS_SELECTOR, 'a[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="next"]'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    try:
                        next_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Clicked next page button")
                    time.sleep(3)
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_page(self, driver):
        jobs = []

        # Scroll to load dynamic content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        # PRIORITY: IBM-specific selectors
        job_links = []
        ibm_priority_selectors = [
            (By.CSS_SELECTOR, 'a[href*="JobDetail"]'),
            (By.CSS_SELECTOR, 'a[href*="jobId"]'),
            (By.CSS_SELECTOR, 'a[href*="/job/"]'),
            (By.CSS_SELECTOR, 'div.bx--card'),
            (By.CSS_SELECTOR, 'div[class*="job-card"]'),
            (By.CSS_SELECTOR, 'li[class*="result"]'),
        ]

        for selector_type, selector_value in ibm_priority_selectors:
            try:
                found_links = driver.find_elements(selector_type, selector_value)
                found_links = [e for e in found_links if e.get_attribute('href') and
                              ('/job/' in (e.get_attribute('href') or '') or 'jobid' in (e.get_attribute('href') or '').lower() or 'JobDetail' in (e.get_attribute('href') or ''))]
                if found_links and len(found_links) >= 1:
                    job_links = found_links
                    logger.info(f"Found {len(job_links)} job links using IBM priority selector: {selector_value}")
                    break
            except Exception:
                continue

        # Secondary selectors
        if not job_links:
            selectors = [
                (By.CSS_SELECTOR, 'a[href*="/careers/job/"]'),
                (By.CSS_SELECTOR, 'a.bx--link[href*="/job/"]'),
                (By.CSS_SELECTOR, '[class*="bx--card"] a'),
                (By.CSS_SELECTOR, '[class*="job-card"] a'),
                (By.CSS_SELECTOR, '[class*="JobCard"] a'),
                (By.CSS_SELECTOR, '[class*="search-result"] a'),
                (By.CSS_SELECTOR, '.bx--search-result a'),
                (By.CSS_SELECTOR, 'article a[href*="/job/"]'),
                (By.CSS_SELECTOR, 'a[href*="jobid"]'),
                (By.CSS_SELECTOR, 'a[href*="job-id"]'),
                (By.CSS_SELECTOR, 'a[href*="careers.ibm.com"]'),
                (By.XPATH, '//a[contains(@href, "job") and (contains(@href, "careers") or contains(@href, "ibm"))]'),
            ]

            for selector_type, selector_value in selectors:
                try:
                    found_links = driver.find_elements(selector_type, selector_value)
                    found_links = [e for e in found_links if e.get_attribute('href') and
                                  ('/job/' in (e.get_attribute('href') or '') or 'jobid' in (e.get_attribute('href') or '').lower() or 'JobDetail' in (e.get_attribute('href') or ''))]
                    if found_links and len(found_links) >= 1:
                        job_links = found_links
                        logger.info(f"Found {len(job_links)} job links using selector: {selector_value}")
                        break
                except Exception:
                    continue

        if not job_links:
            logger.warning("No job links found with selectors, trying broad link search")
            try:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                job_links = [a for a in all_links if a.get_attribute('href') and
                             ('/job/' in (a.get_attribute('href') or '') or 'job-id' in (a.get_attribute('href') or '') or 'JobDetail' in (a.get_attribute('href') or ''))]
                if job_links:
                    logger.info(f"Found {len(job_links)} job links with broad search")
            except Exception:
                pass

        # JS-based link extraction fallback
        if not job_links:
            logger.info("Trying JS-based link extraction fallback")
            js_links = driver.execute_script("""
                var results = [];
                document.querySelectorAll('a[href]').forEach(function(link) {
                    var text = (link.innerText || '').trim();
                    var href = link.href || '';
                    if (text.length > 3 && text.length < 200 && href.length > 10) {
                        var lhref = href.toLowerCase();
                        if (lhref.includes('/job') || lhref.includes('jobdetail') || lhref.includes('jobid') ||
                            lhref.includes('/position') || lhref.includes('/career') ||
                            lhref.includes('/opening') || lhref.includes('/detail') || lhref.includes('/requisition') ||
                            lhref.includes('/vacancy') || lhref.includes('/role')) {
                            results.push({title: text.split('\\n')[0].trim(), url: href});
                        }
                    }
                });
                return results;
            """)
            if js_links:
                seen = set()
                for link_data in js_links:
                    title = link_data.get('title', '')
                    url = link_data.get('url', '')
                    if not title or not url or len(title) < 3 or title in seen:
                        continue
                    exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog']
                    if any(w in title.lower() for w in exclude):
                        continue
                    seen.add(title)
                    job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                if jobs:
                    logger.info(f"JS fallback found {len(jobs)} jobs")

        if not job_links and not jobs:
            logger.warning("Still no job links found")
            return jobs

        # Process each job link
        seen_urls = set()
        for idx, link in enumerate(job_links):
            try:
                job_link = link.get_attribute('href')
                if not job_link or job_link in seen_urls:
                    continue
                seen_urls.add(job_link)

                job_title = link.text.strip()

                if not job_title or len(job_title) < 3:
                    try:
                        parent = link.find_element(By.XPATH, '..')
                        job_title = parent.text.strip().split('\n')[0]
                    except:
                        pass

                if not job_title or len(job_title) < 3:
                    try:
                        title_elem = link.find_element(By.CSS_SELECTOR, 'h3, h2, span, div')
                        job_title = title_elem.text.strip()
                    except:
                        pass

                if not job_title or len(job_title) < 3:
                    continue

                job_id = f"ibm_{idx}"
                try:
                    if 'jobId=' in job_link:
                        job_id = job_link.split('jobId=')[-1].split('&')[0]
                    elif '/careers/job/' in job_link:
                        job_id = job_link.split('/careers/job/')[-1].split('?')[0].split('/')[0]
                    elif '/job/' in job_link:
                        job_id = job_link.split('/job/')[-1].split('?')[0].split('/')[0]
                    elif 'jobid=' in job_link.lower():
                        job_id = job_link.split('jobid=')[-1].split('&')[0]
                    elif '/' in job_link:
                        job_id = job_link.split('/')[-1].split('?')[0]
                except:
                    pass

                location = ""
                city = ""
                state = ""
                try:
                    parent = link.find_element(By.XPATH, '..')
                    parent_text = parent.text
                    lines = parent_text.split('\n')
                    for line in lines:
                        if 'India' in line or any(city_name in line for city_name in [
                            'Mumbai', 'Bangalore', 'Bengaluru', 'Hyderabad', 'Delhi',
                            'Pune', 'Kolkata', 'Chennai', 'Gurgaon', 'Noida', 'Ahmedabad'
                        ]):
                            location = line.strip()
                            city, state, _ = self.parse_location(location)
                            break
                except:
                    pass

                if not location:
                    location = "India"

                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': job_title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': 'India',
                    'employment_type': '',
                    'department': '',
                    'apply_url': job_link,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }

                if FETCH_FULL_JOB_DETAILS and job_link:
                    full_details = self._fetch_job_details(driver, job_link)
                    job_data.update(full_details)

                jobs.append(job_data)

            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                continue

        return jobs

    def _fetch_job_details(self, driver, job_url):
        details = {}
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(job_url)
            time.sleep(3)

            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, '.job-description'),
                    (By.CSS_SELECTOR, '[class*="description"]'),
                    (By.CSS_SELECTOR, '[itemprop="description"]'),
                    (By.CSS_SELECTOR, '[class*="job-details"]'),
                ]
                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        details['description'] = desc_elem.text.strip()[:2000]
                        break
                    except:
                        continue
            except:
                pass

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass

        return details

    def parse_location(self, location_str):
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import stat
from datetime import datetime
from pathlib import Path
import sys

try:
    import requests
except ImportError:
    requests = None

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('qualcomm_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class QualcommScraper:
    def __init__(self):
        self.company_name = 'Qualcomm'
        self.url = 'https://qualcomm.wd5.myworkdayjobs.com/External?locationCountry=bc33aa3152ec42d4995f4791a106ed09'
        self.api_url = 'https://qualcomm.wd5.myworkdayjobs.com/wday/cxs/qualcomm/External/jobs'
        self.base_job_url = 'https://qualcomm.wd5.myworkdayjobs.com/External'
    
    def setup_driver(self):
        """Set up Chrome driver with options"""
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
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Qualcomm Workday careers page - API first, Selenium fallback"""
        all_jobs = []

        # Primary method: Workday API via requests (direct)
        if requests is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("Direct API returned 0 jobs, trying Selenium-assisted API")
            except Exception as e:
                logger.warning(f"Direct API failed: {str(e)}, trying Selenium-assisted API")

            # Secondary method: Use Selenium to get cookies, then hit API
            try:
                api_jobs = self._scrape_via_selenium_api(max_pages)
                if api_jobs:
                    logger.info(f"Selenium-assisted API returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("Selenium-assisted API returned 0 jobs, falling back to pure Selenium")
            except Exception as e:
                logger.warning(f"Selenium-assisted API failed: {str(e)}, falling back to pure Selenium")
        else:
            logger.warning("requests library not available, using Selenium only")

        # Fallback: Selenium-based scraping
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Qualcomm jobs using Workday API directly.
        Try multiple payload formats since Qualcomm's Workday returns 422 on some payloads."""
        all_jobs = []
        limit = 20
        max_results = max_pages * limit

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': self.url,
            'Origin': 'https://qualcomm.wd5.myworkdayjobs.com',
        }

        # Try multiple payload formats - Qualcomm Workday is picky about payload structure
        payload_formats = [
            # Format 1: Empty appliedFacets + searchText "India" (proven for Samsung/Nvidia)
            {
                "appliedFacets": {},
                "limit": limit,
                "offset": 0,
                "searchText": "India"
            },
            # Format 2: locationCountry facet (original)
            {
                "appliedFacets": {
                    "locationCountry": ["bc33aa3152ec42d4995f4791a106ed09"]
                },
                "limit": limit,
                "offset": 0,
                "searchText": ""
            },
            # Format 3: Completely empty appliedFacets with empty search
            {
                "appliedFacets": {},
                "limit": limit,
                "offset": 0,
                "searchText": ""
            },
            # Format 4: Location facet with different key name
            {
                "appliedFacets": {
                    "Location_Country": ["bc33aa3152ec42d4995f4791a106ed09"]
                },
                "limit": limit,
                "offset": 0,
                "searchText": ""
            },
            # Format 5: locations facet (another variant)
            {
                "appliedFacets": {
                    "locations": ["bc33aa3152ec42d4995f4791a106ed09"]
                },
                "limit": limit,
                "offset": 0,
                "searchText": ""
            },
        ]

        # Try each payload format
        working_payload = None
        for idx, payload in enumerate(payload_formats):
            try:
                logger.info(f"Trying API payload format {idx + 1}: searchText='{payload.get('searchText', '')}', facets={list(payload.get('appliedFacets', {}).keys())}")
                response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)

                if response.status_code == 200:
                    data = response.json()
                    total = data.get('total', 0)
                    postings = data.get('jobPostings', [])
                    logger.info(f"Format {idx + 1} succeeded: {len(postings)} postings, total={total}")

                    if postings:
                        working_payload = payload.copy()
                        all_jobs = self._process_api_postings(postings)
                        break
                    elif total == 0:
                        logger.info(f"Format {idx + 1} returned 0 total, trying next format")
                        continue
                else:
                    logger.warning(f"Format {idx + 1} returned status {response.status_code}")
                    continue
            except Exception as e:
                logger.warning(f"Format {idx + 1} failed: {str(e)}")
                continue

        if not working_payload:
            logger.warning("No API payload format worked")
            return all_jobs

        # If we found a working format, paginate through all results
        if all_jobs and working_payload:
            offset = limit
            while offset < max_results:
                working_payload['offset'] = offset
                try:
                    logger.info(f"Fetching API page offset={offset}")
                    response = requests.post(self.api_url, json=working_payload, headers=headers, timeout=30)
                    if response.status_code != 200:
                        break

                    data = response.json()
                    total = data.get('total', 0)
                    postings = data.get('jobPostings', [])

                    if not postings:
                        break

                    new_jobs = self._process_api_postings(postings)
                    all_jobs.extend(new_jobs)
                    logger.info(f"Page offset={offset}: got {len(new_jobs)} jobs (total so far: {len(all_jobs)})")

                    offset += limit
                    if offset >= total:
                        logger.info(f"Fetched all {total} available jobs")
                        break
                except Exception as e:
                    logger.error(f"API pagination failed at offset {offset}: {str(e)}")
                    break

        logger.info(f"Total jobs from API: {len(all_jobs)}")
        return all_jobs

    def _process_api_postings(self, postings):
        """Process Workday API postings into job data format."""
        jobs = []
        for posting in postings:
            try:
                title = posting.get('title', '')
                if not title:
                    continue

                external_path = posting.get('externalPath', '')
                apply_url = f"{self.base_job_url}{external_path}" if external_path else self.url

                location = posting.get('locationsText', '')
                posted_date = posting.get('postedOn', '')

                # Extract job ID from externalPath (e.g., /job/R12345)
                job_id = ''
                if external_path:
                    parts = external_path.strip('/').split('/')
                    if parts:
                        job_id = parts[-1]
                if not job_id:
                    job_id = f"qualcomm_{hashlib.md5(title.encode()).hexdigest()[:12]}"

                # Extract additional info from bulletFields
                bullet_fields = posting.get('bulletFields', [])
                remote_type = ''
                employment_type = ''
                for field in bullet_fields:
                    if isinstance(field, str):
                        if 'On-site' in field or 'Remote' in field or 'Hybrid' in field:
                            remote_type = field
                        elif 'Full' in field or 'Part' in field or 'Contract' in field:
                            employment_type = field

                # Parse location
                city, state, country = self.parse_location(location)

                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': country,
                    'employment_type': employment_type,
                    'department': '',
                    'apply_url': apply_url,
                    'posted_date': posted_date,
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': remote_type,
                    'status': 'active'
                }
                jobs.append(job_data)
                logger.info(f"Added job: {title}")

            except Exception as e:
                logger.error(f"Error processing posting: {str(e)}")
                continue

        return jobs

    def _scrape_via_selenium_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Use Selenium to get Cloudflare cookies, then use requests for API calls."""
        driver = None
        all_jobs = []

        try:
            logger.info("Using Selenium to obtain Cloudflare cookies for API access")
            driver = self.setup_driver()
    
            # Visit the main page to get cookies through Cloudflare
            try:
                driver.get(self.url)
            except Exception:
                pass  # Page may timeout but we still get cookies

            time.sleep(8)  # Wait for Cloudflare challenge

            # Extract cookies from Selenium
            selenium_cookies = driver.get_cookies()
            cookie_dict = {c['name']: c['value'] for c in selenium_cookies}
            logger.info(f"Got {len(cookie_dict)} cookies from Selenium: {list(cookie_dict.keys())}")

            # Also try to get the CSRF token from the page
            csrf_token = None
            try:
                csrf_token = driver.execute_script(
                    "return document.querySelector('meta[name=\"csrf-token\"]')?.content || "
                    "window.csrfToken || null"
                )
            except Exception:
                pass

            driver.quit()
            driver = None

            # Now use requests with the Selenium cookies
            session = requests.Session()
            for name, value in cookie_dict.items():
                session.cookies.set(name, value)

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Referer': self.url,
                'Origin': 'https://qualcomm.wd5.myworkdayjobs.com',
            }
            if csrf_token:
                headers['X-CALYPSO-CSRF-TOKEN'] = csrf_token

            limit = 20
            max_results = max_pages * limit
            offset = 0

            # Try multiple payload formats with cookies
            payload_formats = [
                {"appliedFacets": {}, "limit": limit, "offset": 0, "searchText": "India"},
                {"appliedFacets": {"locationCountry": ["bc33aa3152ec42d4995f4791a106ed09"]}, "limit": limit, "offset": 0, "searchText": ""},
                {"appliedFacets": {}, "limit": limit, "offset": 0, "searchText": ""},
            ]

            working_payload = None
            for pf in payload_formats:
                try:
                    test_resp = session.post(self.api_url, json=pf, headers=headers, timeout=30)
                    if test_resp.status_code == 200:
                        test_data = test_resp.json()
                        if test_data.get('jobPostings'):
                            working_payload = pf.copy()
                            logger.info(f"Selenium-assisted API found working payload: searchText='{pf.get('searchText', '')}'")
                            break
                except:
                    continue

            if not working_payload:
                logger.warning("No payload format worked with Selenium cookies")
                return all_jobs

            while offset < max_results:
                working_payload['offset'] = offset

                logger.info(f"Selenium-assisted API: fetching offset={offset}")
                response = session.post(self.api_url, json=working_payload, headers=headers, timeout=30)

                if response.status_code != 200:
                    logger.warning(f"Selenium-assisted API returned {response.status_code}")
                    break

                data = response.json()
                total = data.get('total', 0)
                postings = data.get('jobPostings', [])

                if not postings:
                    break

                logger.info(f"Got {len(postings)} postings (total: {total})")

                for posting in postings:
                    try:
                        title = posting.get('title', '')
                        if not title:
                            continue

                        external_path = posting.get('externalPath', '')
                        apply_url = f"{self.base_job_url}{external_path}" if external_path else self.url
                        location = posting.get('locationsText', '')
                        posted_date = posting.get('postedOn', '')

                        job_id = ''
                        if external_path:
                            parts = external_path.strip('/').split('/')
                            if parts:
                                job_id = parts[-1]
                        if not job_id:
                            job_id = f"qualcomm_{hashlib.md5(title.encode()).hexdigest()[:12]}"

                        bullet_fields = posting.get('bulletFields', [])
                        remote_type = ''
                        employment_type = ''
                        for field in bullet_fields:
                            if isinstance(field, str):
                                if 'On-site' in field or 'Remote' in field or 'Hybrid' in field:
                                    remote_type = field
                                elif 'Full' in field or 'Part' in field or 'Contract' in field:
                                    employment_type = field

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
                            'employment_type': employment_type,
                            'department': '',
                            'apply_url': apply_url,
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        })
                    except Exception as e:
                        logger.error(f"Error processing posting: {str(e)}")
                        continue

                offset += limit
                if offset >= total:
                    break

        except Exception as e:
            logger.error(f"Selenium-assisted API failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            if driver:
                driver.quit()

        logger.info(f"Selenium-assisted API total: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: scrape Qualcomm jobs using Selenium."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting Selenium scrape for {self.company_name}")
            driver = self.setup_driver()
    
            try:
                driver.get(self.url)
            except Exception as e:
                error_msg = str(e).lower()
                if 'dns' in error_msg or 'name or service not known' in error_msg or \
                   'err_name_not_resolved' in error_msg or 'neterror' in error_msg or \
                   'unreachable' in error_msg or 'connectionrefused' in error_msg:
                    logger.error(f"DNS/Network error loading {self.url}: {str(e)}")
                    logger.error("The Workday URL may be incorrect or the site may be down.")
                    return jobs
                raise

            # Wait for Workday job listings to load
            time.sleep(12)  # Workday takes longer to load

            # Scroll to trigger lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                # Scrape current page
                page_jobs = self._scrape_page(driver)
                jobs.extend(page_jobs)

                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(5)  # Wait for Workday to load next page

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs via Selenium from {self.company_name}")

        except Exception as e:
            error_msg = str(e).lower()
            if 'dns' in error_msg or 'name or service not known' in error_msg or \
               'err_name_not_resolved' in error_msg or 'neterror' in error_msg:
                logger.error(f"DNS/Network error for {self.company_name}: {str(e)}")
            else:
                logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs
    
    def _go_to_next_page(self, driver, current_page):
        """Navigate to next page in Workday"""
        try:
            next_page_num = current_page + 1

            # Scroll to pagination
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Workday pagination selectors
            next_selectors = [
                (By.XPATH, f'//button[@aria-label="{next_page_num}"]'),
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'button[data-uxi-widget-type="page"][aria-label="{next_page_num}"]'),
                (By.XPATH, '//button[@aria-label="next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="next"]'),
            ]

            for selector_type, selector_value in next_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    logger.info(f"Navigated to page {next_page_num}")
                    return True
                except:
                    continue

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scrape_page(self, driver):
        """Scrape jobs from current Workday page using JS-first + Selenium fallback"""
        jobs = []
        wait = WebDriverWait(driver, 5)
        time.sleep(3)

        # STRATEGY 1: JavaScript-first extraction for Workday
        # Workday's DOM uses specific data-automation-id attributes
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Workday specific selectors
                // List items with data-automation-id
                var listItems = document.querySelectorAll('li[data-automation-id="listItem"]');
                if (listItems.length === 0) {
                    // Fallback: search results list
                    var searchList = document.querySelector('ul[aria-label="Search Results"]');
                    if (searchList) listItems = searchList.querySelectorAll('li');
                }
                if (listItems.length === 0) {
                    // Broader: any li in the main content area
                    listItems = document.querySelectorAll('section[data-automation-id="jobResults"] li, div[data-automation-id="jobResults"] li');
                }

                if (listItems.length > 0) {
                    for (var i = 0; i < listItems.length; i++) {
                        var li = listItems[i];
                        var text = (li.innerText || '').trim();
                        if (text.length < 10) continue;

                        // Find the job title link
                        var titleLink = li.querySelector('a[data-automation-id="jobTitle"]') ||
                                       li.querySelector('a[href*="/job/"]') ||
                                       li.querySelector('a');
                        if (!titleLink) continue;

                        var title = (titleLink.getAttribute('aria-label') || titleLink.innerText || '').trim();
                        var url = titleLink.href || '';
                        if (!title || title.length < 3) continue;
                        title = title.split('\n')[0].trim();

                        var key = title + '|' + url;
                        if (seen[key]) continue;
                        seen[key] = true;

                        // Extract metadata from text lines
                        var lines = text.split('\n');
                        var location = '';
                        var remoteType = '';
                        var postedDate = '';
                        var jobId = '';

                        for (var j = 0; j < lines.length; j++) {
                            var line = lines[j].trim();
                            if (!line) continue;

                            // Job ID (REQ pattern)
                            if (line.match(/^REQ/) && line.length < 15) {
                                jobId = line;
                            }
                            // Location (city, state format or contains India)
                            else if (line.includes(',') && line.length < 100 &&
                                     (line.includes('India') || line.match(/Hyderabad|Bangalore|Chennai|Mumbai|Delhi|Noida|Pune|Gurgaon|Gurugram/i))) {
                                location = line;
                            }
                            // Remote type
                            else if (line.match(/^(On-site|Remote|Hybrid)$/i)) {
                                remoteType = line;
                            }
                            // Posted date
                            else if (line.includes('Posted') || line.includes('ago')) {
                                postedDate = line.replace('Posted', '').trim();
                            }
                        }

                        results.push({
                            title: title,
                            url: url,
                            location: location,
                            remoteType: remoteType,
                            postedDate: postedDate,
                            jobId: jobId
                        });
                    }
                }

                // Fallback: links with /job/ pattern
                if (results.length === 0) {
                    document.querySelectorAll('a[href*="/job/"]').forEach(function(link) {
                        var text = (link.innerText || link.getAttribute('aria-label') || '').trim();
                        var href = link.href || '';
                        if (text.length < 3 || text.length > 200) return;
                        var title = text.split('\n')[0].trim();
                        var key = title + '|' + href;
                        if (seen[key]) return;
                        seen[key] = true;
                        results.push({title: title, url: href, location: '', remoteType: '', postedDate: '', jobId: ''});
                    });
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} Workday jobs")
                seen_ids = set()
                for jl in js_jobs:
                    title = jl.get('title', '').strip()
                    url = jl.get('url', '').strip()
                    if not title:
                        continue

                    # Extract job ID
                    job_id = jl.get('jobId', '')
                    if not job_id and url and '/job/' in url:
                        job_id = url.split('/job/')[-1].split('/')[0].split('?')[0]
                    if not job_id:
                        job_id = f"qualcomm_{hashlib.md5(title.encode()).hexdigest()[:12]}"

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in seen_ids:
                        continue
                    seen_ids.add(ext_id)

                    location = jl.get('location', '')
                    city, state, country = self.parse_location(location)

                    job_data = {
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': '',
                        'apply_url': url if url else self.url,
                        'posted_date': jl.get('postedDate', ''),
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': jl.get('remoteType', ''),
                        'status': 'active'
                    }
                    jobs.append(job_data)
                    logger.info(f"Extracted: {title} | {location}")

                if jobs:
                    return jobs

        except Exception as e:
            logger.error(f"JS extraction error: {str(e)}")

        # STRATEGY 2: Selenium selector-based extraction
        # Workday job listing selectors
        workday_selectors = [
            (By.CSS_SELECTOR, 'li[data-automation-id="listItem"]'),
            (By.CSS_SELECTOR, 'li.css-1q2dra3'),
            (By.CSS_SELECTOR, 'ul li[class*="job"]'),
            (By.XPATH, '//ul[@aria-label="Search Results"]/li'),
            (By.CSS_SELECTOR, 'a[href*="/job"]'),
            (By.CSS_SELECTOR, 'div[class*="job-card"]'),
            (By.CSS_SELECTOR, 'li[class*="job"]'),
        ]

        job_cards = []
        for selector_type, selector_value in workday_selectors:
            try:
                wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                job_cards = driver.find_elements(selector_type, selector_value)
                if job_cards and len(job_cards) > 0:
                    logger.info(f"Found {len(job_cards)} jobs using selector: {selector_value}")
                    break
            except:
                continue

        if not job_cards:
            # Link-based fallback for Workday
            logger.warning("No job cards found, trying link-based fallback")
            try:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                seen_urls = set()
                for link in all_links:
                    try:
                        href = link.get_attribute('href') or ''
                        text = link.text.strip()
                        if not text or len(text) < 3 or href in seen_urls:
                            continue
                        if '/job/' in href or '/External/' in href:
                            seen_urls.add(href)
                            job_id = href.split('/')[-1].split('?')[0] or f"qualcomm_{len(jobs)}"
                            job_data = {
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name,
                                'title': text,
                                'description': '',
                                'location': '',
                                'city': '',
                                'state': '',
                                'country': 'India',
                                'employment_type': '',
                                'department': '',
                                'apply_url': href,
                                'posted_date': '',
                                'job_function': '',
                                'experience_level': '',
                                'salary_range': '',
                                'remote_type': '',
                                'status': 'active'
                            }
                            jobs.append(job_data)
                            logger.info(f"Fallback found job: {text}")
                    except:
                        continue
            except:
                pass

        # JS-based link extraction fallback
        if not jobs:
            logger.info("Trying JS-based link extraction fallback")
            try:
                js_links = driver.execute_script("""
                    var results = [];
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            var lhref = href.toLowerCase();
                            if (lhref.includes('/job') || lhref.includes('/position') || lhref.includes('/career') ||
                                lhref.includes('/opening') || lhref.includes('/detail') || lhref.includes('/vacancy') ||
                                lhref.includes('/role') || lhref.includes('/requisition') || lhref.includes('/apply')) {
                                results.push({title: text.split('\\n')[0].trim(), url: href});
                            }
                        }
                    });
                    return results;
                """)
                if js_links:
                    seen = set()
                    exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq']
                    for link_data in js_links:
                        title = link_data.get('title', '')
                        url = link_data.get('url', '')
                        if not title or not url or len(title) < 3 or title in seen:
                            continue
                        if any(w in title.lower() for w in exclude):
                            continue
                        seen.add(title)
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '', 'location': '', 'city': '', 'state': '',
                            'country': 'India', 'employment_type': '', 'department': '',
                            'apply_url': url, 'posted_date': '', 'job_function': '',
                            'experience_level': '', 'salary_range': '', 'remote_type': '', 'status': 'active'
                        })
                    if jobs:
                        logger.info(f"JS fallback found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"JS fallback error: {str(e)}")

            return jobs

        for idx, card in enumerate(job_cards):
            try:
                card_text = card.text
                if not card_text or len(card_text) < 10:
                    continue

                # Extract job title (usually a link)
                job_title = ""
                job_link = ""

                try:
                    title_link = card.find_element(By.TAG_NAME, 'a')
                    job_title = title_link.get_attribute('aria-label') or title_link.text.strip()
                    job_link = title_link.get_attribute('href')
                except:
                    # Fallback to first line
                    job_title = card_text.split('\n')[0].strip()

                if not job_title or len(job_title) < 3:
                    continue

                # Extract Job ID (like REQ... or from URL)
                job_id = ""
                lines = card_text.split('\n')
                for line in lines:
                    line_stripped = line.strip()
                    if line_stripped.startswith('REQ') and len(line_stripped) < 15:
                        job_id = line_stripped
                        break

                if not job_id:
                    # Try to extract from URL
                    if job_link and '/job/' in job_link:
                        job_id = job_link.split('/job/')[-1].split('/')[0]
                    else:
                        job_id = f"qualcomm_{hashlib.md5(job_title.encode()).hexdigest()[:12]}"

                # Extract location and work type
                location = ""
                city = ""
                state = ""
                remote_type = ""
                posted_date = ""

                for line in lines:
                    line_stripped = line.strip()

                    # Location (city, state format)
                    if ',' in line_stripped and len(line_stripped.split(',')) >= 2:
                        parts = line_stripped.split(',')
                        if len(parts[1].strip()) <= 3 or 'India' in line_stripped:
                            location = line_stripped
                            city = parts[0].strip()
                            state = parts[1].strip()

                    # Work type
                    if 'On-site' in line_stripped:
                        remote_type = 'On-site'
                    elif 'Remote' in line_stripped:
                        remote_type = 'Remote'
                    elif 'Hybrid' in line_stripped:
                        remote_type = 'Hybrid'

                    # Posted date
                    if 'Posted' in line_stripped:
                        posted_date = line_stripped.replace('Posted', '').strip()

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
                    'apply_url': job_link if job_link else self.url,
                    'posted_date': posted_date,
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': remote_type,
                    'status': 'active'
                }

                # Fetch full details if enabled
                if FETCH_FULL_JOB_DETAILS and job_link and job_link != self.url:
                    full_details = self._fetch_job_details(driver, job_link)
                    job_data.update(full_details)

                jobs.append(job_data)
                logger.info(f"Successfully added job: {job_title}")

            except Exception as e:
                logger.error(f"Error extracting job {idx}: {str(e)}")
                continue

        return jobs
    
    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}
        
        try:
            # Open job in new tab
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            
            driver.get(job_url)
            time.sleep(4)
            
            # Extract job description
            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div[data-automation-id="jobPostingDescription"]'),
                    (By.XPATH, '//div[contains(@class, "jobDescription")]'),
                    (By.XPATH, '//h2[contains(text(), "Description")]/following-sibling::div'),
                ]
                
                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        if desc_elem and desc_elem.text.strip():
                            details['description'] = desc_elem.text.strip()[:2000]
                            logger.debug(f"Extracted description using selector: {selector_value}")
                            break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"Error extracting description: {str(e)}")
            
            # Extract employment type
            try:
                emp_type_elem = driver.find_element(By.CSS_SELECTOR, 'dd[data-automation-id="timeType"]')
                details['employment_type'] = emp_type_elem.text.strip()
            except:
                pass
            
            # Close tab and return to search results
            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            # Make sure we return to original window
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass
        
        return details
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'
        
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        
        return city, state, 'India'

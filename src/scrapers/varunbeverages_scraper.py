from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('varunbeverages_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class VarunBeveragesScraper:
    def __init__(self):
        self.company_name = 'Varun Beverages'
        # Oracle HCM Cloud platform
        self.url = 'https://rjcorphcm-iacbiz.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs?location=India&locationId=300000000489931&locationLevel=country&mode=location'

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
            service = Service(CHROMEDRIVER_PATH)
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
        driver = None
        all_jobs = []

        # Try Oracle HCM REST API first (faster and more reliable)
        if requests is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("API returned 0 jobs, falling back to Selenium")
            except Exception as e:
                logger.warning(f"API failed: {str(e)}, falling back to Selenium")

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Oracle HCM Cloud is slow to render - wait 15s
            time.sleep(15)

            wait = WebDriverWait(driver, 10)
            short_wait = WebDriverWait(driver, 5)

            # Wait for Oracle HCM specific elements
            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "span.job-tile__title, div.job-tile__header-container, div.search-jobs-root-container, div.job-list-item__content"
                )))
                logger.info("Oracle HCM elements detected")
            except:
                logger.warning("Timeout waiting for Oracle HCM listings, proceeding anyway")

            jobs = self._scrape_page(driver, short_wait)
            all_jobs.extend(jobs)

            # Try pagination - Oracle HCM uses "Show More" or numbered pages
            if all_jobs:
                for page in range(2, max_pages + 1):
                    try:
                        # Look for "Show More" or "Next" or numbered pagination
                        show_more = None
                        for sel in ['button[data-qa="show-more"]', 'a[data-qa="show-more"]', 'button.show-more',
                                    'a.show-more', 'button[aria-label="Show More Jobs"]',
                                    'button[aria-label="Next"]', 'a[aria-label="Next"]']:
                            try:
                                show_more = driver.find_element(By.CSS_SELECTOR, sel)
                                if show_more.is_displayed():
                                    break
                                show_more = None
                            except:
                                continue

                        if not show_more:
                            logger.info("No more pages available")
                            break

                        driver.execute_script("arguments[0].scrollIntoView();", show_more)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", show_more)
                        logger.info(f"Clicked show more/next for page {page}")
                        time.sleep(5)

                        new_jobs = self._scrape_page(driver, short_wait)
                        # Only add jobs not already seen
                        existing_ids = {j['external_id'] for j in all_jobs}
                        new_unique = [j for j in new_jobs if j['external_id'] not in existing_ids]
                        if not new_unique:
                            logger.info("No new jobs found on this page")
                            break
                        all_jobs.extend(new_unique)
                        logger.info(f"Page {page}: found {len(new_unique)} new jobs")
                    except Exception as e:
                        logger.info(f"Pagination ended: {str(e)}")
                        break

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()

    def _scrape_page(self, driver, wait):
        jobs = []
        scraped_ids = set()

        try:
            # Scroll to load dynamic content - Oracle HCM needs aggressive scrolling
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Strategy 1: Oracle HCM - span.job-tile__title (primary selector from DOM analysis)
            job_titles = []
            try:
                job_titles = driver.find_elements(By.CSS_SELECTOR, 'span.job-tile__title')
                if job_titles:
                    logger.info(f"Found {len(job_titles)} jobs using span.job-tile__title")
            except:
                pass

            if job_titles:
                for idx, title_elem in enumerate(job_titles):
                    try:
                        title = title_elem.text.strip()
                        if not title or len(title) < 3:
                            continue

                        # Navigate up to find the parent container for more info
                        job_url = ""
                        location = ""
                        description = ""

                        # Try to get the parent anchor/link
                        try:
                            parent_container = title_elem.find_element(By.XPATH, './ancestor::div[contains(@class, "job-tile__header-container")]')
                            try:
                                link_elem = parent_container.find_element(By.TAG_NAME, 'a')
                                job_url = link_elem.get_attribute('href') or ''
                            except:
                                pass
                        except:
                            pass

                        # Try clicking the title to find the link
                        if not job_url:
                            try:
                                link_elem = title_elem.find_element(By.XPATH, './ancestor::a')
                                job_url = link_elem.get_attribute('href') or ''
                            except:
                                pass

                        # Try parent's parent for link
                        if not job_url:
                            try:
                                parent = title_elem.find_element(By.XPATH, './..')
                                link = parent.find_element(By.TAG_NAME, 'a')
                                job_url = link.get_attribute('href') or ''
                            except:
                                pass

                        # Try to find associated job-list-item__content for description
                        try:
                            # Go up to the job list item level
                            list_item = title_elem.find_element(By.XPATH, './ancestor::div[contains(@class, "job-list-item")]')
                            try:
                                desc_elem = list_item.find_element(By.CSS_SELECTOR, 'p.job-list-item__description')
                                description = desc_elem.text.strip()[:500]
                            except:
                                pass
                            # Try location from list item
                            try:
                                loc_text = list_item.text
                                for line in loc_text.split('\n'):
                                    line_s = line.strip()
                                    if any(c in line_s for c in ['India', 'Mumbai', 'Delhi', 'Noida', 'Gurgaon', 'Bangalore', 'Gurugram', 'Greater Noida']):
                                        if line_s != title:
                                            location = line_s
                                            break
                            except:
                                pass
                        except:
                            pass

                        job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
                        if job_url:
                            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

                        job_data = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'apply_url': job_url if job_url else self.url,
                            'location': location,
                            'department': '',
                            'employment_type': '',
                            'description': description,
                            'posted_date': '',
                            'city': '',
                            'state': '',
                            'country': 'India',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        job_data.update(self.parse_location(location))

                        if job_data['external_id'] not in scraped_ids:
                            jobs.append(job_data)
                            scraped_ids.add(job_data['external_id'])
                            logger.info(f"Extracted: {title} | {location}")
                    except Exception as e:
                        logger.error(f"Error extracting job {idx}: {str(e)}")
                        continue
                return jobs

            # Strategy 2: div.job-tile__header-container elements
            header_containers = []
            try:
                header_containers = driver.find_elements(By.CSS_SELECTOR, 'div.job-tile__header-container')
                if header_containers:
                    logger.info(f"Found {len(header_containers)} job containers using div.job-tile__header-container")
            except:
                pass

            if header_containers:
                for idx, container in enumerate(header_containers):
                    try:
                        title = ""
                        try:
                            title_elem = container.find_element(By.CSS_SELECTOR, 'span.job-tile__title')
                            title = title_elem.text.strip()
                        except:
                            title = container.text.strip().split('\n')[0]

                        if not title or len(title) < 3:
                            continue

                        job_url = ""
                        try:
                            link = container.find_element(By.TAG_NAME, 'a')
                            job_url = link.get_attribute('href') or ''
                        except:
                            pass

                        job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
                        if job_url:
                            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

                        job_data = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'apply_url': job_url if job_url else self.url,
                            'location': '',
                            'department': '',
                            'employment_type': '',
                            'description': '',
                            'posted_date': '',
                            'city': '',
                            'state': '',
                            'country': 'India',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }

                        if job_data['external_id'] not in scraped_ids:
                            jobs.append(job_data)
                            scraped_ids.add(job_data['external_id'])
                            logger.info(f"Extracted: {title}")
                    except Exception as e:
                        logger.error(f"Error extracting container {idx}: {str(e)}")
                return jobs

            # Strategy 3: div.job-list-item__content elements
            list_items = []
            try:
                list_items = driver.find_elements(By.CSS_SELECTOR, 'div.job-list-item__content')
                if list_items:
                    logger.info(f"Found {len(list_items)} items using div.job-list-item__content")
            except:
                pass

            if list_items:
                for idx, item in enumerate(list_items):
                    try:
                        title = item.text.strip().split('\n')[0]
                        if not title or len(title) < 3:
                            continue

                        description = ""
                        try:
                            desc = item.find_element(By.CSS_SELECTOR, 'p.job-list-item__description')
                            description = desc.text.strip()[:500]
                        except:
                            pass

                        job_url = ""
                        try:
                            link = item.find_element(By.TAG_NAME, 'a')
                            job_url = link.get_attribute('href') or ''
                        except:
                            pass

                        job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
                        job_data = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'apply_url': job_url if job_url else self.url,
                            'location': '',
                            'department': '',
                            'employment_type': '',
                            'description': description,
                            'posted_date': '',
                            'city': '',
                            'state': '',
                            'country': 'India',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }

                        if job_data['external_id'] not in scraped_ids:
                            jobs.append(job_data)
                            scraped_ids.add(job_data['external_id'])
                            logger.info(f"Extracted: {title}")
                    except Exception as e:
                        logger.error(f"Error {idx}: {str(e)}")
                return jobs

            # Strategy 4: Generic link/element fallback for Oracle HCM
            logger.info("Trying generic Oracle HCM fallback selectors")
            job_elements = []
            fallback_selectors = [
                "a[href*='/jobs/']",
                "[data-route*='job']",
                "[role='listitem']",
                "li[class*='job-card']",
                "[class*='requisition']",
                "[class*='job-card']",
                "[class*='search-result']",
            ]

            for selector in fallback_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Found {len(elements)} elements using fallback: {selector}")
                        break
                except:
                    continue

            for idx, elem in enumerate(job_elements, 1):
                try:
                    job = self._extract_job(elem, driver, wait, idx)
                    if job and job['external_id'] not in scraped_ids:
                        jobs.append(job)
                        scraped_ids.add(job['external_id'])
                        logger.info(f"Extracted: {job.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"Error {idx}: {str(e)}")

            # Strategy 5: JavaScript extraction - comprehensive Oracle HCM
            if not jobs:
                logger.info("Trying JavaScript extraction for Oracle HCM")
                js_jobs = driver.execute_script("""
                    var results = [];
                    var seen = {};

                    // Oracle HCM selectors (multiple variants)
                    var titleSelectors = [
                        'span.job-tile__title',
                        'h2.job-card__title', 'h3.job-card__title',
                        'a.job-card-link', 'a[data-qa="job-title"]',
                        'div.job-card__title', 'span[class*="job-title"]',
                        'h2[class*="title"]', 'a[href*="/jobs/"]'
                    ];

                    for (var s = 0; s < titleSelectors.length; s++) {
                        var elems = document.querySelectorAll(titleSelectors[s]);
                        if (elems.length > 0) {
                            for (var i = 0; i < elems.length; i++) {
                                var title = (elems[i].innerText || elems[i].textContent || '').trim();
                                if (title.length < 3 || title.length > 200) continue;
                                title = title.split('\n')[0].trim();
                                var link = '';
                                if (elems[i].tagName === 'A') {
                                    link = elems[i].href || '';
                                } else {
                                    var parent = elems[i].closest('a') || elems[i].parentElement;
                                    if (parent && parent.tagName === 'A') {
                                        link = parent.href || '';
                                    } else {
                                        var aTag = parent ? parent.querySelector('a[href]') : null;
                                        if (aTag) link = aTag.href || '';
                                    }
                                }
                                var key = title;
                                if (seen[key]) continue;
                                seen[key] = true;

                                // Try to find location from parent container
                                var location = '';
                                var container = elems[i].closest('[class*="job-card"], [class*="job-tile"], [class*="job-list"], [role="listitem"], li');
                                if (container) {
                                    var text = container.innerText || '';
                                    var lines = text.split('\n');
                                    for (var j = 0; j < lines.length; j++) {
                                        var line = lines[j].trim();
                                        if (line !== title && line.match(/India|Mumbai|Delhi|Noida|Gurgaon|Bangalore|Greater Noida|Gurugram/i)) {
                                            location = line;
                                            break;
                                        }
                                    }
                                }
                                results.push({title: title, url: link, location: location});
                            }
                            if (results.length > 0) break;
                        }
                    }

                    // Fallback: any link with /jobs/ in the path
                    if (results.length === 0) {
                        document.querySelectorAll('a[href]').forEach(function(link) {
                            var text = (link.innerText || '').trim();
                            var href = link.href || '';
                            if (text.length > 3 && text.length < 200 && href.length > 10) {
                                if (href.includes('/job') || href.includes('/requisition')) {
                                    var key = text;
                                    if (seen[key]) return;
                                    seen[key] = true;
                                    results.push({title: text.split('\n')[0].trim(), url: href, location: ''});
                                }
                            }
                        });
                    }

                    // Fallback: find repeated elements that look like job cards
                    if (results.length === 0) {
                        var containers = document.querySelectorAll('ul, div[class*="list"], div[class*="result"], section');
                        for (var c = 0; c < containers.length; c++) {
                            var children = containers[c].children;
                            if (children.length >= 2 && children.length <= 200) {
                                var validCount = 0;
                                for (var k = 0; k < Math.min(children.length, 5); k++) {
                                    var ct = (children[k].innerText || '').trim();
                                    if (ct.length > 10 && ct.length < 500 && children[k].querySelector('a[href]')) validCount++;
                                }
                                if (validCount >= 2) {
                                    for (var m = 0; m < children.length; m++) {
                                        var cText = (children[m].innerText || '').trim();
                                        if (cText.length < 5 || cText.length > 500) continue;
                                        var cTitle = cText.split('\n')[0].trim();
                                        if (cTitle.length < 3) continue;
                                        var cLink = children[m].querySelector('a[href]');
                                        var cUrl = cLink ? cLink.href : '';
                                        if (cLink && cLink.innerText) cTitle = cLink.innerText.trim().split('\n')[0];
                                        var cKey = cTitle;
                                        if (seen[cKey]) continue;
                                        seen[cKey] = true;
                                        results.push({title: cTitle, url: cUrl, location: ''});
                                    }
                                    if (results.length >= 2) break;
                                }
                            }
                        }
                    }

                    return results;
                """)
                if js_jobs:
                    logger.info(f"JS extraction found {len(js_jobs)} job entries")
                    for idx, jl in enumerate(js_jobs):
                        title = jl.get('title', '').strip()
                        url = jl.get('url', '').strip()
                        if title and len(title) >= 3:
                            job_id = hashlib.md5(f"{title}_{url}".encode()).hexdigest()[:12]
                            job_data = {
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name,
                                'title': title,
                                'apply_url': url if url else self.url,
                                'location': '',
                                'department': '',
                                'employment_type': '',
                                'description': '',
                                'posted_date': '',
                                'city': '',
                                'state': '',
                                'country': 'India',
                                'job_function': '',
                                'experience_level': '',
                                'salary_range': '',
                                'remote_type': '',
                                'status': 'active'
                            }
                            if job_data['external_id'] not in scraped_ids:
                                jobs.append(job_data)
                                scraped_ids.add(job_data['external_id'])
                                logger.info(f"JS Extracted: {title}")

        except Exception as e:
            logger.error(f"Error: {str(e)}")
        return jobs

    def _extract_job(self, job_elem, driver, wait, idx):
        try:
            title = ""
            job_url = ""

            if job_elem.tag_name == 'a':
                title = job_elem.text.strip().split('\n')[0]
                job_url = job_elem.get_attribute('href')
            else:
                for sel in ["span.job-tile__title", "h2 a", "h3 a", "a[href*='/jobs/']", "a"]:
                    try:
                        elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                        title = elem.text.strip()
                        if sel != "span.job-tile__title":
                            job_url = elem.get_attribute('href')
                        if title:
                            break
                    except:
                        continue
                if not job_url:
                    try:
                        link = job_elem.find_element(By.TAG_NAME, 'a')
                        job_url = link.get_attribute('href') or ''
                    except:
                        pass

            if not title:
                title = job_elem.text.strip().split('\n')[0]
            if not title or not job_url:
                return None

            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

            location = ""
            for line in job_elem.text.split('\n')[1:]:
                line_s = line.strip()
                if any(c in line_s for c in ['India', 'Mumbai', 'Delhi', 'Noida', 'Gurgaon', 'Bangalore', 'Greater Noida', 'Gurugram']):
                    location = line_s
                    break

            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': location,
                'department': '',
                'employment_type': '',
                'description': '',
                'posted_date': '',
                'city': '',
                'state': '',
                'country': 'India',
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            if FETCH_FULL_JOB_DETAILS and job_url:
                try:
                    details = self._fetch_details(driver, job_url)
                    if details:
                        job_data.update(details)
                except:
                    pass

            job_data.update(self.parse_location(job_data.get('location', '')))
            return job_data
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return None

    def _fetch_details(self, driver, job_url):
        details = {}
        try:
            original = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(job_url)
            time.sleep(5)

            for sel in [".job-description", "[class*='description']", "main"]:
                try:
                    elem = driver.find_element(By.CSS_SELECTOR, sel)
                    text = elem.text.strip()
                    if text and len(text) > 50:
                        details['description'] = text[:3000]
                        break
                except:
                    continue

            driver.close()
            driver.switch_to.window(original)
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass
        return details

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Try Oracle HCM REST API to fetch jobs directly."""
        all_jobs = []
        # Oracle HCM Cloud REST API endpoint pattern
        base_url = 'https://rjcorphcm-iacbiz.fa.ocs.oraclecloud.com'
        api_url = f'{base_url}/hcmRestApi/resources/latest/recruitingCEJobRequisitions'

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        }

        # Try multiple API patterns for Oracle HCM
        api_patterns = [
            # Pattern 1: REST API
            f'{base_url}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations,flexFieldsFacet.values&finder=findReqs;siteNumber=CX_1,facetsList=LOCATIONS%3BWORK_LOCATIONS%3BWORKPLACE_TYPES%3BTITLES%3BCATEGORIES%3BORGANIZATIONS%3BPOSTING_DATES%3BFLEX_FIELDS,limit=25,locationId=300000000489931,sortBy=POSTING_DATES_DESC',
            # Pattern 2: Search API
            f'{base_url}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber=CX_1,limit=25,locationId=300000000489931,sortBy=POSTING_DATES_DESC',
            # Pattern 3: Simple listing
            f'{base_url}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?limit=25&onlyData=true&finder=findReqs;siteNumber=CX_1,locationId=300000000489931',
        ]

        for api_pattern in api_patterns:
            try:
                logger.info(f"Trying Oracle HCM API: {api_pattern[:100]}...")
                response = requests.get(api_pattern, headers=headers, timeout=30)

                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    if not items:
                        # Try nested structure
                        items = data.get('requisitionList', [])
                    if not items:
                        # Try another nested path
                        for key in data:
                            if isinstance(data[key], list) and len(data[key]) > 0:
                                items = data[key]
                                break

                    if items:
                        logger.info(f"API returned {len(items)} items")
                        for item in items:
                            try:
                                title = item.get('Title', '') or item.get('title', '') or item.get('RequisitionTitle', '')
                                if not title:
                                    continue

                                req_id = str(item.get('Id', '') or item.get('id', '') or item.get('RequisitionId', '') or item.get('RequisitionNumber', ''))
                                location = item.get('PrimaryLocation', '') or item.get('primaryLocation', '') or item.get('Location', '')
                                posted_date = item.get('PostedDate', '') or item.get('postedDate', '')

                                job_url = f"{base_url}/hcmUI/CandidateExperience/en/sites/CX_1/job/{req_id}" if req_id else self.url

                                job_id = req_id if req_id else hashlib.md5(title.encode()).hexdigest()[:12]

                                job_data = {
                                    'external_id': self.generate_external_id(job_id, self.company_name),
                                    'company_name': self.company_name,
                                    'title': title,
                                    'apply_url': job_url,
                                    'location': location,
                                    'department': item.get('Organization', '') or item.get('Department', ''),
                                    'employment_type': item.get('WorkerType', ''),
                                    'description': '',
                                    'posted_date': posted_date,
                                    'city': '',
                                    'state': '',
                                    'country': 'India',
                                    'job_function': item.get('Category', '') or item.get('JobCategory', ''),
                                    'experience_level': '',
                                    'salary_range': '',
                                    'remote_type': item.get('WorkplaceType', ''),
                                    'status': 'active'
                                }
                                job_data.update(self.parse_location(location))
                                all_jobs.append(job_data)
                                logger.info(f"API extracted: {title} | {location}")
                            except Exception as e:
                                logger.error(f"Error processing API item: {str(e)}")
                                continue

                        if all_jobs:
                            return all_jobs
                else:
                    logger.warning(f"API returned status {response.status_code}")
            except Exception as e:
                logger.warning(f"API pattern failed: {str(e)}")
                continue

        return all_jobs

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
    scraper = VarunBeveragesScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

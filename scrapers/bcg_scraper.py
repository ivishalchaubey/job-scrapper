from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
import hashlib
import time
from datetime import datetime
from pathlib import Path
import os
import stat


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('bcg_scraper')

class BCGScraper:
    def __init__(self):
        self.company_name = 'BCG'
        # Filter for India locations
        self.url = 'https://careers.bcg.com/global/en/search-results?rk=page-targeted-jobs-page54-prod-ds-Nusa6pGk&sortBy=Most%20relevant'

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

        driver_path = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

        try:
            if os.path.exists(driver_path):
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external_id using MD5 hash"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Main scraping method"""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            driver.get(self.url)

            # Smart wait for Phenom job listings instead of blind sleep
            try:
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "div.job-title, li[data-ph-at-id='job-listing'], a.apply-btn, div.phs-facet-results"
                )))
                logger.info("Job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for Phenom job listings: {str(e)}")
                time.sleep(5)

            # Quick scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

            # Scrape current page
            wait = WebDriverWait(driver, 5)
            jobs = self._scrape_page(driver, wait)
            all_jobs.extend(jobs)

            # Phenom API fallback if DOM scraping returned 0 jobs
            if not all_jobs:
                logger.info("DOM scraping returned 0 jobs, trying Phenom API approach")
                api_jobs = self._scrape_via_phenom_api(driver)
                all_jobs.extend(api_jobs)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _scrape_page(self, driver, wait):
        """Scrape all jobs from current page"""
        jobs = []
        scraped_ids = set()

        try:
            # Quick scroll to load content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)

            # --- Strategy 1: JavaScript extraction using Phenom DOM selectors ---
            logger.info("Trying JS-based Phenom extraction (div.job-title, a.apply-btn)")
            js_jobs = driver.execute_script("""
                var results = [];

                // Strategy A: Find job titles via div.job-title
                var jobTitles = document.querySelectorAll('div.job-title');
                for (var i = 0; i < jobTitles.length; i++) {
                    var titleDiv = jobTitles[i];
                    var titleSpan = titleDiv.querySelector('span');
                    var title = titleSpan ? titleSpan.innerText.trim() : titleDiv.innerText.trim();
                    if (!title) continue;

                    // Find the closest parent that contains an apply link
                    var parent = titleDiv.closest('li') || titleDiv.closest('div.phs-facet-results') || titleDiv.parentElement;
                    var applyLink = null;
                    var url = '';

                    // Look for apply button near this job title
                    if (parent) {
                        applyLink = parent.querySelector('a.apply-btn') || parent.querySelector('a[href*="/job/"]') || parent.querySelector('a[href*="jobId"]');
                    }
                    // Also check siblings
                    if (!applyLink) {
                        var sibling = titleDiv.nextElementSibling;
                        while (sibling) {
                            if (sibling.tagName === 'A') { applyLink = sibling; break; }
                            var innerA = sibling.querySelector('a.apply-btn') || sibling.querySelector('a[href*="/job/"]');
                            if (innerA) { applyLink = innerA; break; }
                            sibling = sibling.nextElementSibling;
                        }
                    }

                    if (applyLink) {
                        url = applyLink.href || '';
                    }

                    // Extract location from nearby elements
                    var location = '';
                    if (parent) {
                        var locEl = parent.querySelector('[class*="location"], [data-ph-at-job-location-text]');
                        if (locEl) location = locEl.innerText.trim();
                    }

                    // Extract category/department
                    var department = '';
                    if (parent) {
                        var catEl = parent.querySelector('[class*="category"], [data-ph-at-job-category-text]');
                        if (catEl) department = catEl.innerText.trim();
                    }

                    if (title.length > 2) {
                        results.push({title: title, url: url, location: location, department: department});
                    }
                }

                // Strategy B: If no results from job-title divs, try li[data-ph-at-id='job-listing']
                if (results.length === 0) {
                    var listings = document.querySelectorAll('li[data-ph-at-id="job-listing"]');
                    for (var j = 0; j < listings.length; j++) {
                        var li = listings[j];
                        var titleEl = li.querySelector('div.job-title span') || li.querySelector('div.job-title') || li.querySelector('[data-ph-at-job-title-text]');
                        var title2 = titleEl ? titleEl.innerText.trim() : '';
                        var linkEl = li.querySelector('a.apply-btn') || li.querySelector('a[href*="/job/"]') || li.querySelector('a');
                        var url2 = linkEl ? linkEl.href : '';
                        var locEl2 = li.querySelector('[class*="location"], [data-ph-at-job-location-text]');
                        var loc2 = locEl2 ? locEl2.innerText.trim() : '';
                        var catEl2 = li.querySelector('[class*="category"], [data-ph-at-job-category-text]');
                        var cat2 = catEl2 ? catEl2.innerText.trim() : '';
                        if (title2.length > 2) {
                            results.push({title: title2, url: url2, location: loc2, department: cat2});
                        }
                    }
                }

                // Strategy C: Broader search for apply buttons that contain job titles in sr-only spans
                if (results.length === 0) {
                    var applyBtns = document.querySelectorAll('a.apply-btn');
                    for (var k = 0; k < applyBtns.length; k++) {
                        var btn = applyBtns[k];
                        var srSpan = btn.querySelector('.sr-only') || btn.querySelector('span');
                        var title3 = srSpan ? srSpan.innerText.trim() : btn.innerText.trim();
                        // Clean up "Apply for" prefix
                        title3 = title3.replace(/^Apply\\s*(for)?\\s*/i, '').trim();
                        var url3 = btn.href || '';
                        if (title3.length > 2) {
                            results.push({title: title3, url: url3, location: '', department: ''});
                        }
                    }
                }

                return results;
            """)

            if js_jobs and len(js_jobs) > 0:
                logger.info(f"JS Phenom extraction found {len(js_jobs)} jobs")
                seen_titles = set()
                for jdx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3 or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    if not url:
                        url = self.url

                    # Extract job ID from URL
                    job_id = ''
                    if 'jobId=' in url:
                        job_id = url.split('jobId=')[-1].split('&')[0]
                    elif '/job/' in url:
                        job_id = url.split('/job/')[-1].split('/')[0].split('?')[0]
                    if not job_id:
                        job_id = f"bcg_{jdx}_{hashlib.md5((title + url).encode()).hexdigest()[:8]}"

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url,
                        'location': location,
                        'department': department,
                        'employment_type': '',
                        'description': '',
                        'posted_date': '',
                        'city': '',
                        'state': '',
                        'country': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    location_parts = self.parse_location(location)
                    job_data.update(location_parts)

                    if job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job {len(jobs)}: {title}")

                if jobs:
                    return jobs

            # --- Strategy 2: Selenium element-based extraction ---
            logger.info("JS extraction returned 0, trying Selenium element selectors")
            job_elements = []
            selectors = [
                "li[data-ph-at-id='job-listing']",
                "div.job-title",
                "a.apply-btn",
                "a[data-ph-at-id='job-link']",
                "section#search-results-list li",
                ".ph-job-card",
                "div.job-card",
                "[data-ph-at-id='search-results-section'] li",
                "[data-ph-at-job-title-text]",
            ]

            short_wait = WebDriverWait(driver, 5)
            for selector in selectors:
                try:
                    short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Found {len(job_elements)} job listings using selector: {selector}")
                        break
                except:
                    continue

            if not job_elements:
                # Final fallback: JS-based generic link extraction
                logger.info("Trying generic JS link extraction fallback")
                js_links = driver.execute_script("""
                    var results = [];
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var href = links[i].href || '';
                        var text = (links[i].innerText || '').trim();
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            if (href.includes('/job') || href.includes('/position') || href.includes('/career') || href.includes('/opening')) {
                                results.push({title: text.split('\\n')[0].trim(), url: href});
                            }
                        }
                    }
                    return results;
                """)
                if js_links:
                    logger.info(f"Generic JS fallback found {len(js_links)} links")
                    seen_urls = set()
                    for jdx, link_data in enumerate(js_links):
                        title = link_data.get('title', '')
                        url = link_data.get('url', '')
                        if not title or not url or len(title) < 3 or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                        job_data = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'apply_url': url,
                            'location': '',
                            'department': '',
                            'employment_type': '',
                            'description': '',
                            'posted_date': '',
                            'city': '',
                            'state': '',
                            'country': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        location_parts = self.parse_location('')
                        job_data.update(location_parts)
                        jobs.append(job_data)
                if not js_links or not jobs:
                    logger.warning("Could not find job listings with any selector")
                return jobs

            for idx, job_elem in enumerate(job_elements, 1):
                try:
                    job_data = self._extract_job_from_element(job_elem, driver, wait, idx)
                    if job_data and job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job {len(jobs)}: {job_data.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        return jobs

    def _extract_job_from_element(self, job_elem, driver, wait, idx):
        """Extract job data from a job listing element"""
        try:
            # Scroll into view
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", job_elem)
                time.sleep(0.3)
            except Exception as e:
                logger.debug(f"Could not scroll to job {idx}: {str(e)}")

            # Extract job title and URL
            title = ""
            job_url = ""

            tag_name = job_elem.tag_name

            # If the element itself is a div.job-title, extract directly
            elem_class = job_elem.get_attribute('class') or ''
            if 'job-title' in elem_class:
                try:
                    span = job_elem.find_element(By.TAG_NAME, 'span')
                    title = span.text.strip()
                except:
                    title = job_elem.text.strip()
                # Find apply link nearby
                try:
                    parent = job_elem.find_element(By.XPATH, './..')
                    apply_link = parent.find_element(By.CSS_SELECTOR, 'a.apply-btn, a[href*="/job/"]')
                    job_url = apply_link.get_attribute('href')
                except:
                    pass
            elif tag_name == 'a':
                title = job_elem.text.strip()
                # Clean "Apply for" prefix from sr-only spans
                if title.lower().startswith('apply'):
                    title = title.replace('Apply for ', '').replace('Apply ', '').strip()
                job_url = job_elem.get_attribute('href')
            else:
                # Generic element (li, div, etc.)
                title_selectors = [
                    "div.job-title span",
                    "div.job-title",
                    "span.au-target",
                    "[data-ph-at-job-title-text]",
                    "h3 a",
                    "a[href*='/job/']",
                    "a.apply-btn",
                ]

                for selector in title_selectors:
                    try:
                        title_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        text = title_elem.text.strip()
                        href = title_elem.get_attribute('href') or ''
                        if text:
                            title = text
                            if href:
                                job_url = href
                            break
                    except:
                        continue

                if not job_url:
                    try:
                        link = job_elem.find_element(By.CSS_SELECTOR, "a.apply-btn, a[href*='/job/']")
                        job_url = link.get_attribute('href')
                        if not title:
                            sr = link.find_element(By.CSS_SELECTOR, '.sr-only')
                            title = sr.text.strip().replace('Apply for ', '').replace('Apply ', '').strip()
                    except:
                        pass

                if not title:
                    links = job_elem.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        text = link.text.strip()
                        href = link.get_attribute('href')
                        if text and len(text) > 5 and href:
                            title = text
                            job_url = href
                            break

            if not title:
                logger.warning(f"Missing title for job {idx}")
                return None

            if not job_url:
                job_url = self.url

            # Extract job ID from URL
            job_id = ""
            if 'jobId=' in job_url:
                job_id = job_url.split('jobId=')[-1].split('&')[0]
            elif '/job/' in job_url:
                job_id = job_url.split('/job/')[-1].split('/')[0].split('?')[0]
            else:
                job_id = f"bcg_{idx}_{hashlib.md5((title + job_url).encode()).hexdigest()[:8]}"

            # Extract location
            location = ""
            try:
                location_selectors = [
                    "[data-ph-at-job-location-text]",
                    ".job-location",
                    "[class*='location']"
                ]

                for selector in location_selectors:
                    try:
                        loc_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        location = loc_elem.text.strip()
                        if location:
                            break
                    except:
                        continue

                if not location:
                    all_text = job_elem.text
                    if 'India' in all_text:
                        lines = all_text.split('\n')
                        for line in lines:
                            if 'India' in line:
                                location = line.strip()
                                break
            except Exception as e:
                logger.debug(f"Could not extract location: {str(e)}")

            # Extract department/category
            department = ""
            try:
                dept_selectors = [
                    "[data-ph-at-job-category-text]",
                    ".job-category",
                    "[class*='category']"
                ]

                for selector in dept_selectors:
                    try:
                        dept_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        department = dept_elem.text.strip()
                        if department:
                            break
                    except:
                        continue
            except:
                pass

            # Build job data
            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': location,
                'department': department,
                'employment_type': '',
                'description': '',
                'posted_date': '',
                'city': '',
                'state': '',
                'country': '',
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            # Fetch full details if enabled
            if FETCH_FULL_JOB_DETAILS and job_url and job_url != self.url:
                try:
                    logger.info(f"Fetching details for: {title}")
                    details = self._fetch_job_details(driver, job_url)
                    if details:
                        job_data.update(details)
                except Exception as e:
                    logger.warning(f"Could not fetch details for {title}: {str(e)}")

            # Parse location
            location_parts = self.parse_location(job_data.get('location', ''))
            job_data.update(location_parts)

            return job_data

        except Exception as e:
            logger.error(f"Error extracting job data: {str(e)}")
            return None

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job details page"""
        details = {
            'description': '',
            'location': '',
            'department': '',
            'employment_type': '',
            'posted_date': ''
        }

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            detail_wait = WebDriverWait(driver, 5)
            time.sleep(3)

            # Description
            description_selectors = [
                "[data-ph-at-id='jobDescription']",
                "[data-ph-at-id='jobdescription']",
                ".job-description",
                "[class*='job-description']",
                "[class*='description']"
            ]
            for selector in description_selectors:
                try:
                    desc_elem = detail_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    text = desc_elem.text.strip()
                    if text:
                        details['description'] = text[:3000]
                        break
                except Exception:
                    continue

            # Location
            location_selectors = [
                "[data-ph-at-id='jobLocation']",
                "[data-ph-at-id='jobLocationText']",
                ".job-location",
                "[class*='location']"
            ]
            for selector in location_selectors:
                try:
                    loc_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = loc_elem.text.strip()
                    if text:
                        details['location'] = text
                        break
                except Exception:
                    continue

            # Department / Category
            department_selectors = [
                "[data-ph-at-id='jobCategory']",
                "[data-ph-at-id='jobCategoryText']",
                ".job-category",
                "[class*='category']"
            ]
            for selector in department_selectors:
                try:
                    dept_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = dept_elem.text.strip()
                    if text:
                        details['department'] = text
                        break
                except Exception:
                    continue

            # Employment type
            employment_selectors = [
                "[data-ph-at-id='jobType']",
                "[data-ph-at-id='jobTypeText']",
                ".job-type",
                "[class*='job-type']"
            ]
            for selector in employment_selectors:
                try:
                    type_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = type_elem.text.strip()
                    if text:
                        details['employment_type'] = text
                        break
                except Exception:
                    continue

            # Posted date
            posted_selectors = [
                "[data-ph-at-id='jobPostedDate']",
                "[class*='posted']",
                "[class*='date']"
            ]
            for selector in posted_selectors:
                try:
                    date_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = date_elem.text.strip()
                    if text and len(text) < 50:
                        details['posted_date'] = text
                        break
                except Exception:
                    continue

            # Fallback: get main content text if description is still empty
            if not details['description']:
                try:
                    main_content = driver.find_element(By.CSS_SELECTOR, "main, [role='main']")
                    full_text = main_content.text.strip()
                    if full_text:
                        details['description'] = full_text[:3000]
                except Exception:
                    pass

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details from {job_url}: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass

        return details

    def _scrape_via_phenom_api(self, driver):
        """Fallback: Use Phenom People API to fetch job listings"""
        jobs = []
        try:
            # Phenom People platforms expose a /api/jobs endpoint
            # Try multiple API URL patterns
            api_urls = [
                'https://careers.bcg.com/api/jobs?location=India&page=1&limit=100',
                'https://careers.bcg.com/api/jobs?q=&location=India&limit=100',
                'https://careers.bcg.com/global/en/api/jobs?page=1&limit=100',
            ]

            for api_url in api_urls:
                try:
                    logger.info(f"Trying Phenom API: {api_url}")
                    result = driver.execute_script('''
                        var xhr = new XMLHttpRequest();
                        xhr.open('GET', arguments[0], false);
                        xhr.setRequestHeader('Accept', 'application/json');
                        xhr.send();
                        if (xhr.status === 200) {
                            return xhr.responseText;
                        }
                        return null;
                    ''', api_url)

                    if result:
                        import json
                        data = json.loads(result)
                        job_list = []
                        # Phenom API may return jobs in different structures
                        if isinstance(data, dict):
                            job_list = data.get('jobs', data.get('data', data.get('results', [])))
                        elif isinstance(data, list):
                            job_list = data

                        if job_list:
                            logger.info(f"Phenom API returned {len(job_list)} jobs")
                            for idx, job in enumerate(job_list):
                                if isinstance(job, dict):
                                    title = job.get('title', job.get('jobTitle', ''))
                                    location = job.get('location', job.get('city', ''))
                                    department = job.get('category', job.get('department', ''))
                                    job_id = job.get('id', job.get('jobId', job.get('requisitionId', '')))
                                    url = job.get('url', job.get('applyUrl', ''))

                                    if not title or len(title) < 3:
                                        continue

                                    if not job_id:
                                        job_id = f"bcg_api_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

                                    if url and not url.startswith('http'):
                                        url = f"https://careers.bcg.com{url}"

                                    jobs.append({
                                        'external_id': self.generate_external_id(str(job_id), self.company_name),
                                        'company_name': self.company_name,
                                        'title': title,
                                        'apply_url': url if url else self.url,
                                        'location': location if isinstance(location, str) else '',
                                        'department': department,
                                        'employment_type': job.get('type', ''),
                                        'description': '',
                                        'posted_date': job.get('postedDate', ''),
                                        'city': '',
                                        'state': '',
                                        'country': '',
                                        'job_function': '',
                                        'experience_level': '',
                                        'salary_range': '',
                                        'remote_type': '',
                                        'status': 'active'
                                    })
                                    loc_parts = self.parse_location(location if isinstance(location, str) else '')
                                    jobs[-1].update(loc_parts)

                            if jobs:
                                logger.info(f"Phenom API extracted {len(jobs)} jobs")
                                return jobs
                except Exception as api_e:
                    logger.warning(f"API attempt failed: {str(api_e)}")
                    continue

            # If API approach didn't work, try extracting from page source
            if not jobs:
                logger.info("Trying to extract jobs from page source JSON")
                try:
                    page_source = driver.page_source
                    # Phenom often embeds job data in script tags
                    import re
                    json_matches = re.findall(r'"title"\s*:\s*"([^"]+)".*?"url"\s*:\s*"([^"]*)"', page_source)
                    seen = set()
                    for idx, (title, url) in enumerate(json_matches):
                        if title in seen or len(title) < 3 or len(title) > 200:
                            continue
                        # Skip non-job titles
                        skip_words = ['BCG', 'Home', 'Search', 'About', 'Contact', 'Login', 'Cookie']
                        if any(title == w for w in skip_words):
                            continue
                        seen.add(title)
                        if url and not url.startswith('http'):
                            url = f"https://careers.bcg.com{url}"
                        job_id = f"bcg_src_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'apply_url': url if url else self.url,
                            'location': '', 'department': '', 'employment_type': '',
                            'description': '', 'posted_date': '', 'city': '', 'state': '',
                            'country': '', 'job_function': '', 'experience_level': '',
                            'salary_range': '', 'remote_type': '', 'status': 'active'
                        })
                    if jobs:
                        logger.info(f"Page source extraction found {len(jobs)} jobs")
                except Exception as src_e:
                    logger.warning(f"Page source extraction failed: {str(src_e)}")

        except Exception as e:
            logger.error(f"Phenom API fallback error: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        result = {
            'city': '',
            'state': '',
            'country': ''
        }

        if not location_str:
            return result

        # Clean up location string
        location_str = location_str.strip()

        # Common BCG location formats:
        # "Gurgaon, Haryana, India"
        # "Mumbai, India"
        # "Available in 5 locations"

        if 'Available in' in location_str or 'location' in location_str.lower():
            # Multi-location job
            result['country'] = 'India'  # Since we're filtering for India
            return result

        # Try to parse comma-separated location
        parts = [p.strip() for p in location_str.split(',')]

        if len(parts) >= 1:
            result['city'] = parts[0]

        if len(parts) == 3:
            # Format: City, State, Country
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            # Format: City, Country
            result['country'] = parts[1]

        # Default to India if India mentioned
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'

        return result

if __name__ == "__main__":
    scraper = BCGScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

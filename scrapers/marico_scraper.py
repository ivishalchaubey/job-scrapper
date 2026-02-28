from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
from pathlib import Path
import os
import stat


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('marico_scraper')


class MaricoScraper:
    def __init__(self):
        self.company_name = 'Marico'
        self.url = 'https://marico.sensehq.com/careers'

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
        chrome_options.page_load_strategy = 'eager'  # Don't wait for all resources; WebDriverWait handles content detection

        driver_path = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

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
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            driver.get(self.url)

            # Smart wait for SenseHQ React platform to render (instead of blind sleep(15))
            try:
                WebDriverWait(driver, 15).until(
                    lambda d: d.execute_script("""
                        var btns = document.querySelectorAll('a, button');
                        for (var i = 0; i < btns.length; i++) {
                            var t = (btns[i].innerText || '').trim();
                            if (t === 'View Job' || t === 'View job' || t === 'VIEW JOB') return true;
                        }
                        return false;
                    """)
                )
            except:
                time.sleep(5)  # Fallback if View Job buttons not found

            # Single quick scroll to trigger lazy loading (instead of 5 slow scrolls)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

            # SenseHQ uses React + Emotion CSS-in-JS; scrape with JS
            jobs = self._scrape_page(driver)
            all_jobs.extend(jobs)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _scrape_page(self, driver):
        jobs = []
        scraped_ids = set()

        try:
            # --- Strategy 1: JavaScript extraction for SenseHQ (Emotion CSS-in-JS) ---
            # The DOM uses dynamic CSS class names like css-8qk9uv, css-beqgbl etc.
            # Job titles are in spans inside specific container divs.
            # "View Job" buttons use onClick, not href links.
            logger.info("Trying JS-based SenseHQ extraction")
            js_jobs = driver.execute_script("""
                var results = [];

                // SenseHQ/Skillate: Find divs with class css-1lnmtqu (job card containers)
                // Each contains: Title (ID) / Location / Department / View Job
                // Use the body text to parse job blocks between "View Job" markers
                var bodyText = document.body.innerText || '';
                var lines = bodyText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                // Find the start of actual job listings — after the header row "Role" + "Location" + "Department"
                var startIdx = 0;
                for (var si = 0; si < lines.length - 2; si++) {
                    if (lines[si] === 'Role' && lines[si+1] === 'Location' && lines[si+2] === 'Department') {
                        startIdx = si + 3;
                        break;
                    }
                }

                // Parse job blocks: each job has 3 lines (Title, Location, Department) followed by "View Job"
                var currentBlock = [];
                for (var i = startIdx; i < lines.length; i++) {
                    var line = lines[i];
                    if (line === 'View Job' || line === 'View job') {
                        // Process this block — should have exactly 3 lines
                        if (currentBlock.length >= 1) {
                            var title = currentBlock[0] || '';
                            var location = currentBlock.length > 1 ? currentBlock[1] : '';
                            var department = currentBlock.length > 2 ? currentBlock[2] : '';

                            // Extract job ID from title like "Supply Chain Executive (18260)"
                            var jobId = '';
                            var idMatch = title.match(/\\(([0-9]+)\\)$/);
                            if (idMatch) {
                                jobId = idMatch[1];
                                title = title.replace(/\\s*\\([0-9]+\\)$/, '').trim();
                            }

                            if (title && title.length > 2) {
                                results.push({title: title, url: '', location: location, department: department, jobId: jobId});
                            }
                        }
                        currentBlock = [];
                    } else if (line.match(/^(Join Talent|Submit Resume)/) || line.match(/^\\d+ Open Jobs?$/)) {
                        break;  // Stop at footer content
                    } else {
                        currentBlock.push(line);
                    }
                }

                // Deduplicate by title
                var unique = [];
                var seenTitles = new Set();
                for (var u = 0; u < results.length; u++) {
                    if (!seenTitles.has(results[u].title)) {
                        seenTitles.add(results[u].title);
                        unique.push(results[u]);
                    }
                }
                return unique;
            """)

            if js_jobs and len(js_jobs) > 0:
                logger.info(f"JS SenseHQ extraction found {len(js_jobs)} jobs")
                for jdx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if not url:
                        url = self.url

                    job_id = f"marico_{jdx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

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
                        'country': 'India',
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

            # --- Strategy 2: Selenium CSS selector-based extraction ---
            logger.info("JS extraction returned 0, trying Selenium selectors")
            job_elements = []
            selectors = [
                "div.job-card",
                "a[href*='/job-details']",
                "div.job-listing",
                "[class*='job-card']",
                "[class*='job-listing']",
                "a[href*='/careers/']",
                "a[href*='/job/']",
                ".card",
                "article",
            ]

            short_wait = WebDriverWait(driver, 5)
            for selector in selectors:
                try:
                    short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Found {len(job_elements)} listings using selector: {selector}")
                        break
                except:
                    continue

            # Fallback: find links that look like job postings
            if not job_elements:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                job_links = []
                for link in all_links:
                    href = link.get_attribute('href') or ''
                    text = link.text.strip()
                    if ('/careers/' in href or '/jobs/' in href or '/job/' in href or '/job-details' in href or 'sensehq' in href) and text and len(text) > 5:
                        job_links.append(link)
                if job_links:
                    job_elements = job_links
                    logger.info(f"Fallback found {len(job_links)} job links")

            # JavaScript fallback for link extraction
            if not job_elements:
                logger.info("Trying JavaScript fallback for link extraction")
                js_links = driver.execute_script("""
                    var results = [];
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            if (href.includes('/job') || href.includes('/position') || href.includes('/career') || href.includes('/opening') || href.includes('/requisition')) {
                                results.push({title: text.split('\\n')[0].trim(), url: href});
                            }
                        }
                    });
                    return results;
                """)
                if js_links:
                    logger.info(f"JS fallback found {len(js_links)} job links")
                    for jl in js_links:
                        title = jl.get('title', '').strip()
                        url = jl.get('url', '').strip()
                        if title and url:
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
                    return jobs

            if not job_elements:
                logger.warning("Could not find job listings")
                return jobs

            for idx, job_elem in enumerate(job_elements, 1):
                try:
                    job_data = self._extract_job_from_element(job_elem, driver, idx)
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

    def _extract_job_from_element(self, job_elem, driver, idx):
        try:
            title = ""
            job_url = ""

            tag_name = job_elem.tag_name
            if tag_name == 'a':
                title = job_elem.text.strip().split('\n')[0]
                job_url = job_elem.get_attribute('href')
            else:
                title_selectors = [
                    ".job-title a", ".job-title",
                    "a[href*='/job-details']",
                    "h3 a", "h2 a", "h4 a",
                    "[class*='title'] a", "[class*='title']",
                    "a[href*='/careers/']",
                    "a"
                ]
                for selector in title_selectors:
                    try:
                        title_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip()
                        job_url = title_elem.get_attribute('href') or ''
                        if title:
                            break
                    except:
                        continue

                if not job_url:
                    try:
                        link = job_elem.find_element(By.TAG_NAME, 'a')
                        job_url = link.get_attribute('href')
                    except:
                        pass

            if not title:
                text = job_elem.text.strip()
                if text:
                    title = text.split('\n')[0].strip()

            if not title:
                return None

            if not job_url:
                job_url = self.url

            # Extract job ID
            job_id = ""
            if '/careers/' in job_url:
                job_id = job_url.split('/careers/')[-1].split('/')[0].split('?')[0]
            elif '/jobs/' in job_url:
                job_id = job_url.split('/jobs/')[-1].split('/')[0].split('?')[0]
            if not job_id:
                job_id = f"marico_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

            # Extract location
            location = ""
            try:
                all_text = job_elem.text
                lines = all_text.split('\n')
                for line in lines:
                    line_s = line.strip()
                    if any(city in line_s for city in ['Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Pune', 'Hyderabad', 'India']):
                        location = line_s
                        break
            except:
                pass

            # Extract department
            department = ""
            try:
                dept_selectors = ["[class*='department']", "[class*='category']", "[class*='team']"]
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
                'country': 'India',
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            if FETCH_FULL_JOB_DETAILS and job_url and job_url != self.url:
                try:
                    details = self._fetch_job_details(driver, job_url)
                    if details:
                        job_data.update(details)
                except Exception as e:
                    logger.warning(f"Could not fetch details for {title}: {str(e)}")

            location_parts = self.parse_location(job_data.get('location', ''))
            job_data.update(location_parts)

            return job_data

        except Exception as e:
            logger.error(f"Error extracting job data: {str(e)}")
            return None

    def _fetch_job_details(self, driver, job_url):
        details = {}
        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(3)

            desc_selectors = [
                ".job-description",
                "[class*='job-description']",
                "[class*='description']",
                "[class*='detail']",
                "main"
            ]
            for selector in desc_selectors:
                try:
                    desc_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = desc_elem.text.strip()
                    if text and len(text) > 50:
                        details['description'] = text[:3000]
                        break
                except:
                    continue

            type_selectors = ["[class*='employment']", "[class*='job-type']", "[class*='type']"]
            for selector in type_selectors:
                try:
                    type_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = type_elem.text.strip()
                    if text and len(text) < 50:
                        details['employment_type'] = text
                        break
                except:
                    continue

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details from {job_url}: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass

        return details

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result

        location_str = location_str.strip()
        parts = [p.strip() for p in location_str.split(',')]

        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) == 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]

        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'

        return result


if __name__ == "__main__":
    scraper = MaricoScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

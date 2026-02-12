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

logger = setup_logger('loreal_scraper')


class LorealScraper:
    def __init__(self):
        self.company_name = "L'Oreal"
        # India filter: 3_110_3=18031
        self.url = 'https://careers.loreal.com/en_US/jobs/SearchJobs/?3_110_3=18031'

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

            # Wait 12s for custom careers site to load
            time.sleep(12)

            # Try to detect L'Oreal job listings
            try:
                short_wait = WebDriverWait(driver, 10)
                short_wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "section.module--search-jobs, h3.article__header__text__title, div.section--search-jobs, a[href*='JobDetail']"
                )))
                logger.info("Job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for job listings: {str(e)}")

            # Scroll to trigger lazy loading
            for _ in range(4):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                jobs = self._scrape_page(driver)
                all_jobs.extend(jobs)
                logger.info(f"Page {current_page}: found {len(jobs)} jobs")

                if current_page < max_pages:
                    if not self._load_more(driver):
                        break
                    time.sleep(3)
                current_page += 1

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _load_more(self, driver):
        """Click 'View more results' button if available"""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            load_more_selectors = [
                (By.CSS_SELECTOR, "a[class*='viewMoreResults']"),
                (By.XPATH, "//a[contains(text(), 'View more')]"),
                (By.XPATH, "//button[contains(text(), 'View more')]"),
                (By.XPATH, "//a[contains(text(), 'Load more')]"),
                (By.CSS_SELECTOR, ".pagination .next a"),
                (By.CSS_SELECTOR, "a.next"),
            ]

            for selector_type, selector_value in load_more_selectors:
                try:
                    btn = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info("Clicked 'View more results'")
                    return True
                except:
                    continue

            logger.info("No more results to load")
            return False
        except Exception as e:
            logger.error(f"Error loading more results: {str(e)}")
            return False

    def _scrape_page(self, driver):
        jobs = []
        scraped_ids = set()

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # --- Strategy 1: JavaScript extraction for L'Oreal custom careers site ---
            logger.info("Trying JS-based L'Oreal extraction")
            js_jobs = driver.execute_script("""
                var results = [];
                var seenKeys = new Set();

                // Strategy A: Find all JobDetail links (confirmed on page)
                var jobLinks = document.querySelectorAll('a[href*="JobDetail"]');
                for (var i = 0; i < jobLinks.length; i++) {
                    var link = jobLinks[i];
                    var url = link.href || '';
                    if (seenKeys.has(url)) continue;

                    var title = link.innerText.trim();

                    // If the link itself has no text, check parent for title
                    if (!title || title.length < 3) {
                        var parent = link.closest('article') || link.closest('li') || link.closest('div');
                        if (parent) {
                            // Try h3/h2/h4 for title
                            var headings = parent.querySelectorAll('h1, h2, h3, h4, h5');
                            for (var h = 0; h < headings.length; h++) {
                                var hText = headings[h].innerText.trim();
                                if (hText.length > 3 && hText.length < 200) {
                                    title = hText;
                                    break;
                                }
                            }
                        }
                    }

                    // Still no title? Try sibling/parent text
                    if (!title || title.length < 3) {
                        var parentEl = link.parentElement;
                        if (parentEl) {
                            var siblings = parentEl.children;
                            for (var s = 0; s < siblings.length; s++) {
                                var sText = siblings[s].innerText.trim();
                                if (sText.length > 3 && sText.length < 200 && sText !== title) {
                                    title = sText.split(String.fromCharCode(10))[0].trim();
                                    break;
                                }
                            }
                        }
                    }

                    if (!title || title.length < 3) continue;
                    // Clean title - take first line only
                    title = title.split(String.fromCharCode(10))[0].trim();
                    seenKeys.add(url);

                    // Walk up to find container for location info
                    var container = link.closest('article') || link.closest('li') || link.closest('.article');
                    var location = '';
                    var department = '';
                    var postedDate = '';

                    if (container) {
                        var containerText = container.innerText || '';
                        var lines = containerText.split(String.fromCharCode(10));
                        for (var k = 0; k < lines.length; k++) {
                            var line = lines[k].trim();
                            if (!line || line === title || line.length < 3) continue;
                            if (/^(View|Apply|Save|Share|Job ID)/i.test(line)) continue;
                            if (!location && /Mumbai|Delhi|Bangalore|Bengaluru|Chennai|Hyderabad|Pune|Gurugram|Noida|Kolkata|India|IND/i.test(line)) {
                                location = line;
                                continue;
                            }
                            if (!postedDate && /posted|ago|date|day|week|month/i.test(line)) {
                                postedDate = line;
                                continue;
                            }
                            if (!department && line.length < 80 && line.length > 3) {
                                department = line;
                            }
                        }
                    }

                    results.push({
                        title: title,
                        url: url,
                        location: location,
                        department: department,
                        postedDate: postedDate
                    });
                }

                // Strategy B: Find titles via h3.article__header__text__title a (legacy selector)
                if (results.length === 0) {
                    var titleLinks = document.querySelectorAll('h3.article__header__text__title a, h3[class*="article__header"] a, article a[href*="Job"]');
                    for (var j = 0; j < titleLinks.length; j++) {
                        var tLink = titleLinks[j];
                        var tTitle = tLink.innerText.trim();
                        var tUrl = tLink.href || '';
                        if (!tTitle || tTitle.length < 3 || seenKeys.has(tUrl)) continue;
                        seenKeys.add(tUrl);
                        results.push({title: tTitle, url: tUrl, location: '', department: '', postedDate: ''});
                    }
                }

                // Strategy C: All links that look like job listings
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var m = 0; m < allLinks.length; m++) {
                        var a = allLinks[m];
                        var aText = a.innerText.trim();
                        var aHref = a.href || '';
                        if (aText.length > 5 && aText.length < 200 && !seenKeys.has(aHref)) {
                            var lhref = aHref.toLowerCase();
                            if (lhref.indexOf('jobdetail') > -1 || lhref.indexOf('/jobs/') > -1 || lhref.indexOf('/job/') > -1) {
                                seenKeys.add(aHref);
                                results.push({title: aText.split(String.fromCharCode(10))[0].trim(), url: aHref, location: '', department: '', postedDate: ''});
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs and len(js_jobs) > 0:
                logger.info(f"JS L'Oreal extraction found {len(js_jobs)} jobs")
                for jdx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    posted_date = jdata.get('postedDate', '').strip()

                    if not title or len(title) < 3:
                        continue

                    # Extract job ID from URL (e.g., /JobDetail/232009)
                    job_id = ""
                    if url and 'JobDetail' in url:
                        parts = url.split('/')
                        # The numeric ID is usually the last part
                        job_id = parts[-1].split('?')[0]
                    if not job_id:
                        job_id = f"loreal_{jdx}_{hashlib.md5((title + url).encode()).hexdigest()[:8]}"

                    if not url:
                        url = self.url

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url,
                        'location': location,
                        'department': department,
                        'employment_type': '',
                        'description': '',
                        'posted_date': posted_date,
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

            # --- Strategy 2: Selenium element-based extraction ---
            logger.info("JS extraction returned 0, trying Selenium selectors")
            job_elements = []

            # L'Oreal specific selectors - JobDetail links first (confirmed on page)
            selectors = [
                "a[href*='JobDetail']",
                "article a[href*='Job']",
                "h3.article__header__text__title",
                "h3[class*='article__header'] a",
                "section.module--search-jobs article",
                ".article",
                "article",
                "[class*='article__header']",
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

            # Fallback: find all JobDetail links
            if not job_elements:
                all_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='JobDetail']")
                if all_links:
                    job_elements = all_links
                    logger.info(f"Fallback found {len(all_links)} job links")

            if not job_elements:
                # JS-based link extraction as final fallback
                logger.info("Trying JS-based link extraction fallback")
                js_links = driver.execute_script("""
                    var results = [];
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var href = links[i].href || '';
                        var text = (links[i].innerText || '').trim();
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            if (href.includes('/job') || href.includes('/position') || href.includes('/career') || href.includes('/opening') || href.includes('JobDetail')) {
                                results.push({title: text.split('\\n')[0].trim(), url: href});
                            }
                        }
                    }
                    return results;
                """)
                if js_links:
                    logger.info(f"JS fallback found {len(js_links)} links")
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
                            'country': 'India',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        location_parts = self.parse_location('')
                        job_data.update(location_parts)
                        jobs.append(job_data)
                if not jobs:
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
            elem_class = job_elem.get_attribute('class') or ''

            # If the element is an h3 (article header), extract the link inside
            if tag_name == 'h3' and 'article__header' in elem_class:
                try:
                    link = job_elem.find_element(By.TAG_NAME, 'a')
                    title = link.text.strip()
                    job_url = link.get_attribute('href')
                except:
                    title = job_elem.text.strip()
            elif tag_name == 'a':
                title = job_elem.text.strip()
                job_url = job_elem.get_attribute('href')
            else:
                title_selectors = [
                    "h3.article__header__text__title a",
                    "h3[class*='article__header'] a",
                    "h3 a", "h2 a", "h4 a",
                    "a[href*='JobDetail']",
                    ".job-title a",
                    "a"
                ]
                for selector in title_selectors:
                    try:
                        title_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip()
                        job_url = title_elem.get_attribute('href')
                        if title and job_url:
                            break
                    except:
                        continue

            if not title:
                text = job_elem.text.strip()
                if text:
                    title = text.split('\n')[0].strip()

            if not title or not job_url:
                return None

            # Extract job ID from URL (e.g., /JobDetail/232009)
            job_id = ""
            if 'JobDetail' in job_url:
                parts = job_url.split('/')
                for i, part in enumerate(parts):
                    if part == 'JobDetail' and i + 1 < len(parts):
                        # The job ID might be after the title slug
                        job_id = parts[-1].split('?')[0]
                        break
            if not job_id:
                job_id = f"loreal_{idx}_{hashlib.md5(job_url.encode()).hexdigest()[:8]}"

            # Extract location from element text
            location = ""
            try:
                # Walk up to find the full container
                container = job_elem
                for _ in range(4):
                    try:
                        container = container.find_element(By.XPATH, './..')
                    except:
                        break

                all_text = container.text
                lines = all_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if any(city in line for city in ['Mumbai', 'Delhi', 'Bangalore', 'Bengaluru', 'Chennai', 'Hyderabad', 'Pune', 'India', 'Gurugram', 'Noida']):
                        location = line
                        break
            except:
                pass

            # Extract posted date
            posted_date = ""
            try:
                all_text = container.text if container else job_elem.text
                lines = all_text.split('\n')
                for line in lines:
                    if 'Posted' in line:
                        posted_date = line.replace('Posted', '').strip()
                        break
            except:
                pass

            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': location,
                'department': '',
                'employment_type': '',
                'description': '',
                'posted_date': posted_date,
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
                "[class*='jobDescription']",
                ".article__content",
                "[class*='description']",
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

            # Department
            dept_selectors = ["[class*='department']", "[class*='category']", "[class*='expertise']"]
            for selector in dept_selectors:
                try:
                    dept_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = dept_elem.text.strip()
                    if text:
                        details['department'] = text
                        break
                except:
                    continue

            # Employment type
            type_selectors = ["[class*='contract']", "[class*='employment']", "[class*='job-type']"]
            for selector in type_selectors:
                try:
                    type_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = type_elem.text.strip()
                    if text:
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
        # Remove "Posted" date info if present
        if 'Posted' in location_str:
            location_str = location_str.split('Posted')[0].strip()

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
    scraper = LorealScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

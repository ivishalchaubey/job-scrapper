from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('hexaware_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class HexawareTechnologiesScraper:
    def __init__(self):
        self.company_name = 'Hexaware Technologies'
        self.url = 'https://jobs.hexaware.com/#en/sites/CX_1/jobs?mode=location'
        self.job_detail_base_url = 'https://jobs.hexaware.com/#en/sites/CX_1/job'

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

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Hexaware Technologies Oracle HCM Candidate Experience via Selenium"""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Oracle HCM CX is a heavy SPA - needs generous initial wait
            time.sleep(15)

            wait = WebDriverWait(driver, 10)
            short_wait = WebDriverWait(driver, 5)

            # Wait for Oracle HCM specific elements to appear
            try:
                wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "span.job-tile__title, div.job-tile__header-container, "
                    "div.search-jobs-root-container, div.job-list-item__content, "
                    "a[class*='job-card'], div[class*='job-card']"
                )))
                logger.info("Oracle HCM elements detected")
            except Exception:
                logger.warning("Timeout waiting for Oracle HCM listings, proceeding anyway")

            # Scrape first page
            jobs = self._scrape_page(driver, short_wait)
            all_jobs.extend(jobs)

            # Pagination - Oracle HCM uses "Show More" or numbered pages
            if all_jobs:
                for page in range(2, max_pages + 1):
                    try:
                        show_more = None
                        pagination_selectors = [
                            'button[data-qa="show-more"]',
                            'a[data-qa="show-more"]',
                            'button.show-more',
                            'a.show-more',
                            'button[aria-label="Show More Jobs"]',
                            'button[aria-label="Next"]',
                            'a[aria-label="Next"]',
                            'button[class*="show-more"]',
                            'a[class*="show-more"]',
                            'button[class*="load-more"]',
                        ]
                        for sel in pagination_selectors:
                            try:
                                show_more = driver.find_element(By.CSS_SELECTOR, sel)
                                if show_more.is_displayed():
                                    break
                                show_more = None
                            except Exception:
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

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")
            return all_jobs
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()

    def _scrape_page(self, driver, wait):
        """Extract jobs from the current page using multiple strategies"""
        jobs = []
        scraped_ids = set()

        try:
            # Scroll to load dynamic/lazy content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Strategy 1: Oracle HCM - span.job-tile__title (primary selector)
            job_titles = []
            try:
                job_titles = driver.find_elements(By.CSS_SELECTOR, 'span.job-tile__title')
                if job_titles:
                    logger.info(f"Found {len(job_titles)} jobs using span.job-tile__title")
            except Exception:
                pass

            if job_titles:
                for idx, title_elem in enumerate(job_titles):
                    try:
                        title = title_elem.text.strip()
                        if not title or len(title) < 3:
                            continue

                        job_url = ""
                        location = ""
                        description = ""

                        # Try to get link from parent anchor
                        try:
                            parent_container = title_elem.find_element(
                                By.XPATH, './ancestor::div[contains(@class, "job-tile__header-container")]'
                            )
                            try:
                                link_elem = parent_container.find_element(By.TAG_NAME, 'a')
                                job_url = link_elem.get_attribute('href') or ''
                            except Exception:
                                pass
                        except Exception:
                            pass

                        if not job_url:
                            try:
                                link_elem = title_elem.find_element(By.XPATH, './ancestor::a')
                                job_url = link_elem.get_attribute('href') or ''
                            except Exception:
                                pass

                        if not job_url:
                            try:
                                parent = title_elem.find_element(By.XPATH, './..')
                                link = parent.find_element(By.TAG_NAME, 'a')
                                job_url = link.get_attribute('href') or ''
                            except Exception:
                                pass

                        # Try to get location and description from job list item
                        try:
                            list_item = title_elem.find_element(
                                By.XPATH, './ancestor::div[contains(@class, "job-list-item")]'
                            )
                            try:
                                desc_elem = list_item.find_element(By.CSS_SELECTOR, 'p.job-list-item__description')
                                description = desc_elem.text.strip()[:500]
                            except Exception:
                                pass
                            try:
                                loc_text = list_item.text
                                for line in loc_text.split('\n'):
                                    line_s = line.strip()
                                    if any(c in line_s for c in [
                                        'India', 'Mumbai', 'Delhi', 'Noida', 'Gurgaon',
                                        'Bangalore', 'Gurugram', 'Greater Noida', 'Hyderabad',
                                        'Chennai', 'Pune', 'Kolkata', 'Bengaluru'
                                    ]):
                                        if line_s != title:
                                            location = line_s
                                            break
                            except Exception:
                                pass
                        except Exception:
                            pass

                        job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
                        if job_url:
                            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

                        job_data = self._build_job_data(job_id, title, job_url, location, description)
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
            except Exception:
                pass

            if header_containers:
                for idx, container in enumerate(header_containers):
                    try:
                        title = ""
                        try:
                            title_elem = container.find_element(By.CSS_SELECTOR, 'span.job-tile__title')
                            title = title_elem.text.strip()
                        except Exception:
                            title = container.text.strip().split('\n')[0]

                        if not title or len(title) < 3:
                            continue

                        job_url = ""
                        try:
                            link = container.find_element(By.TAG_NAME, 'a')
                            job_url = link.get_attribute('href') or ''
                        except Exception:
                            pass

                        job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
                        if job_url:
                            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

                        job_data = self._build_job_data(job_id, title, job_url, '', '')
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
            except Exception:
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
                        except Exception:
                            pass

                        job_url = ""
                        try:
                            link = item.find_element(By.TAG_NAME, 'a')
                            job_url = link.get_attribute('href') or ''
                        except Exception:
                            pass

                        job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
                        job_data = self._build_job_data(job_id, title, job_url, '', description)
                        if job_data['external_id'] not in scraped_ids:
                            jobs.append(job_data)
                            scraped_ids.add(job_data['external_id'])
                            logger.info(f"Extracted: {title}")
                    except Exception as e:
                        logger.error(f"Error {idx}: {str(e)}")
                return jobs

            # Strategy 4: a[class*="job-card"] or div[class*="job-card"]
            job_cards = []
            card_selectors = [
                "a[class*='job-card']",
                "div[class*='job-card']",
                "a[href*='/job/']",
                "[data-route*='job']",
                "[role='listitem']",
                "li[class*='job-card']",
                "[class*='requisition']",
                "[class*='search-result']",
            ]
            for selector in card_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_cards = elements
                        logger.info(f"Found {len(elements)} elements using fallback: {selector}")
                        break
                except Exception:
                    continue

            for idx, elem in enumerate(job_cards):
                try:
                    job = self._extract_job_from_element(elem, idx)
                    if job and job['external_id'] not in scraped_ids:
                        jobs.append(job)
                        scraped_ids.add(job['external_id'])
                        logger.info(f"Extracted: {job.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"Error {idx}: {str(e)}")

            # Strategy 5: JavaScript extraction - comprehensive Oracle HCM DOM traversal
            if not jobs:
                logger.info("Trying JavaScript extraction for Oracle HCM")
                js_jobs = driver.execute_script("""
                    var results = [];
                    var seen = {};

                    // Oracle HCM selectors (multiple variants across versions)
                    var titleSelectors = [
                        'span.job-tile__title',
                        'h2.job-card__title', 'h3.job-card__title',
                        'a.job-card-link', 'a[data-qa="job-title"]',
                        'div.job-card__title', 'span[class*="job-title"]',
                        'h2[class*="title"]', 'a[href*="/job/"]',
                        'span[class*="title"]'
                    ];

                    for (var s = 0; s < titleSelectors.length; s++) {
                        var elems = document.querySelectorAll(titleSelectors[s]);
                        if (elems.length > 0) {
                            for (var i = 0; i < elems.length; i++) {
                                var title = (elems[i].innerText || elems[i].textContent || '').trim();
                                if (title.length < 3 || title.length > 200) continue;
                                title = title.split('\\n')[0].trim();
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
                                var container = elems[i].closest(
                                    '[class*="job-card"], [class*="job-tile"], [class*="job-list"], [role="listitem"], li'
                                );
                                if (container) {
                                    var text = container.innerText || '';
                                    var lines = text.split('\\n');
                                    for (var j = 0; j < lines.length; j++) {
                                        var line = lines[j].trim();
                                        if (line !== title && line.match(
                                            /India|Mumbai|Delhi|Noida|Gurgaon|Bangalore|Bengaluru|Greater Noida|Gurugram|Hyderabad|Chennai|Pune|Kolkata/i
                                        )) {
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

                    // Fallback: any link with /job in the path
                    if (results.length === 0) {
                        document.querySelectorAll('a[href]').forEach(function(link) {
                            var text = (link.innerText || '').trim();
                            var href = link.href || '';
                            if (text.length > 3 && text.length < 200 && href.length > 10) {
                                if (href.includes('/job') || href.includes('/requisition')) {
                                    var key = text;
                                    if (seen[key]) return;
                                    seen[key] = true;
                                    results.push({title: text.split('\\n')[0].trim(), url: href, location: ''});
                                }
                            }
                        });
                    }

                    // Fallback: find repeated elements that look like job cards
                    if (results.length === 0) {
                        var containers = document.querySelectorAll(
                            'ul, div[class*="list"], div[class*="result"], section'
                        );
                        for (var c = 0; c < containers.length; c++) {
                            var children = containers[c].children;
                            if (children.length >= 2 && children.length <= 200) {
                                var validCount = 0;
                                for (var k = 0; k < Math.min(children.length, 5); k++) {
                                    var ct = (children[k].innerText || '').trim();
                                    if (ct.length > 10 && ct.length < 500 && children[k].querySelector('a[href]'))
                                        validCount++;
                                }
                                if (validCount >= 2) {
                                    for (var m = 0; m < children.length; m++) {
                                        var cText = (children[m].innerText || '').trim();
                                        if (cText.length < 5 || cText.length > 500) continue;
                                        var cTitle = cText.split('\\n')[0].trim();
                                        if (cTitle.length < 3) continue;
                                        var cLink = children[m].querySelector('a[href]');
                                        var cUrl = cLink ? cLink.href : '';
                                        if (cLink && cLink.innerText) cTitle = cLink.innerText.trim().split('\\n')[0];
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
                        loc = jl.get('location', '').strip()
                        if title and len(title) >= 3:
                            job_id = hashlib.md5(f"{title}_{url}".encode()).hexdigest()[:12]
                            job_data = self._build_job_data(job_id, title, url, loc, '')
                            if job_data['external_id'] not in scraped_ids:
                                jobs.append(job_data)
                                scraped_ids.add(job_data['external_id'])
                                logger.info(f"JS Extracted: {title}")

        except Exception as e:
            logger.error(f"Error in _scrape_page: {str(e)}")
        return jobs

    def _extract_job_from_element(self, job_elem, idx):
        """Extract job data from a generic job element"""
        try:
            title = ""
            job_url = ""

            if job_elem.tag_name == 'a':
                title = job_elem.text.strip().split('\n')[0]
                job_url = job_elem.get_attribute('href')
            else:
                for sel in ["span.job-tile__title", "h2 a", "h3 a", "a[href*='/job/']", "a"]:
                    try:
                        elem = job_elem.find_element(By.CSS_SELECTOR, sel)
                        title = elem.text.strip()
                        if sel != "span.job-tile__title":
                            job_url = elem.get_attribute('href')
                        if title:
                            break
                    except Exception:
                        continue
                if not job_url:
                    try:
                        link = job_elem.find_element(By.TAG_NAME, 'a')
                        job_url = link.get_attribute('href') or ''
                    except Exception:
                        pass

            if not title:
                title = job_elem.text.strip().split('\n')[0]
            if not title or len(title) < 3:
                return None

            job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
            if job_url:
                job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

            location = ""
            for line in job_elem.text.split('\n')[1:]:
                line_s = line.strip()
                if any(c in line_s for c in [
                    'India', 'Mumbai', 'Delhi', 'Noida', 'Gurgaon',
                    'Bangalore', 'Gurugram', 'Greater Noida', 'Bengaluru',
                    'Hyderabad', 'Chennai', 'Pune', 'Kolkata'
                ]):
                    location = line_s
                    break

            return self._build_job_data(job_id, title, job_url, location, '')
        except Exception as e:
            logger.error(f"Error extracting element: {str(e)}")
            return None

    def _build_job_data(self, job_id, title, job_url, location, description):
        """Build a standardized job data dictionary"""
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
        if location:
            job_data.update(self.parse_location(location))
        return job_data

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
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
    scraper = HexawareTechnologiesScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']} | {job['apply_url']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

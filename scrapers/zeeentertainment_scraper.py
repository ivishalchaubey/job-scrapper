from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import json
import re

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('zeeentertainment_scraper')

class ZeeEntertainmentScraper:
    def __init__(self):
        self.company_name = "Zee Entertainment Enterprises"
        self.url = "https://zee.sensehq.com/careers"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        driver = None
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)

            # Strategy 1: Extract from __NEXT_DATA__ (Next.js pre-rendered data)
            time.sleep(5)
            next_data_jobs = self._extract_from_next_data(driver)
            if next_data_jobs:
                logger.info(f"__NEXT_DATA__ extraction returned {len(next_data_jobs)} jobs")
                jobs.extend(next_data_jobs)
            else:
                logger.info("__NEXT_DATA__ extraction returned no jobs, falling back to DOM scraping")

                # Strategy 2: Wait for Next.js client-side hydration and scrape DOM
                try:
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((
                            By.CSS_SELECTOR,
                            'div[class*="job"], div[class*="career"], div[class*="position"], '
                            'a[class*="job"], a[href*="/job/"]'
                        ))
                    )
                    logger.info("Job elements detected in DOM")
                except Exception as e:
                    logger.warning(f"DOM element wait timeout: {str(e)}")
                    time.sleep(10)

                # Scroll to load all jobs
                for _ in range(5):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)

                scraped_ids = set()
                page_num = 1

                while page_num <= max_pages:
                    page_jobs = self._extract_jobs_from_dom(driver, scraped_ids)

                    if not page_jobs and page_num == 1:
                        # Try the SenseHQ chatbot/API approach
                        logger.info("Trying alternate SenseHQ job list page...")
                        alternate_urls = [
                            'https://zee.sensehq.com/careers?page=1',
                            'https://zee.sensehq.com/careers/jobs',
                        ]
                        for alt_url in alternate_urls:
                            try:
                                driver.get(alt_url)
                                time.sleep(8)
                                page_jobs = self._extract_jobs_from_dom(driver, scraped_ids)
                                if page_jobs:
                                    logger.info(f"Found jobs at {alt_url}")
                                    break
                            except Exception:
                                continue

                    if not page_jobs:
                        break

                    jobs.extend(page_jobs)
                    logger.info(f"Page {page_num}: {len(page_jobs)} jobs (total: {len(jobs)})")

                    if not self._go_to_next_page(driver):
                        break
                    page_num += 1
                    time.sleep(5)

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return jobs

    def _extract_from_next_data(self, driver):
        """Extract job data from __NEXT_DATA__ script tag (Next.js pre-rendered data)."""
        jobs = []
        try:
            next_data_json = driver.execute_script("""
                var script = document.getElementById('__NEXT_DATA__');
                if (script) {
                    return script.textContent || script.innerText;
                }
                return null;
            """)

            if not next_data_json:
                logger.info("No __NEXT_DATA__ script tag found")
                return jobs

            data = json.loads(next_data_json)
            logger.info("Successfully parsed __NEXT_DATA__ JSON")

            # Navigate the Next.js data structure to find job listings
            # Common paths: props.pageProps.jobs, props.pageProps.data.jobs, etc.
            job_list = self._find_jobs_in_next_data(data)

            if not job_list:
                logger.info("No job list found in __NEXT_DATA__ structure")
                return jobs

            logger.info(f"Found {len(job_list)} jobs in __NEXT_DATA__")
            seen_ids = set()

            for idx, job_item in enumerate(job_list):
                try:
                    title = ''
                    location = ''
                    department = ''
                    apply_url = ''
                    job_id = ''
                    employment_type = ''
                    posted_date = ''
                    experience_level = ''
                    description = ''
                    remote_type = ''

                    # Extract fields from various possible structures
                    if isinstance(job_item, dict):
                        title = (job_item.get('title', '') or job_item.get('name', '') or
                                 job_item.get('jobTitle', '') or job_item.get('position', '') or '').strip()
                        location = (job_item.get('location', '') or job_item.get('locationName', '') or
                                    job_item.get('city', '') or '').strip()
                        if isinstance(location, list):
                            location = ', '.join(str(l) for l in location)
                        department = (job_item.get('department', '') or job_item.get('team', '') or
                                      job_item.get('function', '') or job_item.get('category', '') or '').strip()
                        if isinstance(department, list):
                            department = department[0] if department else ''
                        job_id = str(job_item.get('id', '') or job_item.get('jobId', '') or
                                     job_item.get('requisitionId', '') or '')
                        apply_url = (job_item.get('url', '') or job_item.get('applyUrl', '') or
                                     job_item.get('slug', '') or '').strip()
                        employment_type = (job_item.get('employmentType', '') or
                                           job_item.get('type', '') or '').strip()
                        posted_date = (job_item.get('postedDate', '') or job_item.get('createdAt', '') or
                                       job_item.get('publishedAt', '') or '').strip()
                        experience_level = (job_item.get('experienceLevel', '') or
                                            job_item.get('experience', '') or '').strip()
                        description = (job_item.get('description', '') or
                                       job_item.get('jobDescription', '') or '').strip()
                        if description:
                            description = description[:3000]

                        # Remote type
                        remote_val = job_item.get('remoteType', '') or job_item.get('workType', '') or ''
                        if isinstance(remote_val, str):
                            if 'remote' in remote_val.lower():
                                remote_type = 'Remote'
                            elif 'hybrid' in remote_val.lower():
                                remote_type = 'Hybrid'
                            elif 'onsite' in remote_val.lower() or 'on-site' in remote_val.lower():
                                remote_type = 'On-site'

                    if not title or len(title) < 3:
                        continue

                    if not job_id:
                        job_id = f"zee_nd_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    # Build apply URL if it's a slug
                    if apply_url and not apply_url.startswith('http'):
                        if apply_url.startswith('/'):
                            apply_url = f"https://zee.sensehq.com{apply_url}"
                        else:
                            apply_url = f"https://zee.sensehq.com/careers/{apply_url}"
                    if not apply_url:
                        apply_url = f"https://zee.sensehq.com/careers?jobId={job_id}"

                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': description,
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': apply_url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': experience_level,
                        'salary_range': '',
                        'remote_type': remote_type,
                        'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error parsing __NEXT_DATA__ job item {idx}: {str(e)}")
                    continue

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse __NEXT_DATA__ JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Error extracting from __NEXT_DATA__: {str(e)}")

        return jobs

    def _find_jobs_in_next_data(self, data):
        """Recursively search __NEXT_DATA__ for job list arrays."""
        if isinstance(data, list) and len(data) > 0:
            # Check if this looks like a job list (list of dicts with title-like keys)
            if isinstance(data[0], dict):
                sample = data[0]
                job_keys = {'title', 'name', 'jobTitle', 'position', 'designation'}
                if job_keys.intersection(set(sample.keys())):
                    return data
        elif isinstance(data, dict):
            # Common Next.js paths for page data
            priority_paths = [
                ['props', 'pageProps', 'jobs'],
                ['props', 'pageProps', 'data', 'jobs'],
                ['props', 'pageProps', 'initialData', 'jobs'],
                ['props', 'pageProps', 'jobListings'],
                ['props', 'pageProps', 'openings'],
                ['props', 'pageProps', 'positions'],
                ['props', 'pageProps', 'data', 'openings'],
                ['props', 'pageProps', 'data', 'positions'],
                ['props', 'pageProps', 'data', 'jobListings'],
                ['props', 'pageProps', 'careers'],
                ['props', 'pageProps', 'allJobs'],
            ]

            for path in priority_paths:
                current = data
                found = True
                for key in path:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        found = False
                        break
                if found and isinstance(current, list) and len(current) > 0:
                    return current

            # Recursive search through all dict values
            for key, value in data.items():
                result = self._find_jobs_in_next_data(value)
                if result:
                    return result

        return None

    def _extract_jobs_from_dom(self, driver, scraped_ids):
        """Extract job listings from SenseHQ DOM after client-side rendering."""
        jobs = []
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: SenseHQ-specific job card selectors
                var cardSelectors = [
                    'div[class*="JobCard"], div[class*="job-card"], div[class*="jobCard"]',
                    'div[class*="job-listing"], div[class*="JobListing"]',
                    'div[class*="position-card"], div[class*="PositionCard"]',
                    'a[class*="JobCard"], a[class*="job-card"]',
                    'div[class*="opening-card"], div[class*="OpeningCard"]',
                    'article[class*="job"], article[class*="career"]',
                    '[data-testid*="job"], [data-testid*="career"]'
                ];

                var jobCards = [];
                for (var s = 0; s < cardSelectors.length; s++) {
                    try {
                        var els = document.querySelectorAll(cardSelectors[s]);
                        if (els.length > 0) {
                            jobCards = els;
                            break;
                        }
                    } catch(e) {}
                }

                if (jobCards.length > 0) {
                    for (var i = 0; i < jobCards.length; i++) {
                        var card = jobCards[i];
                        var text = (card.innerText || '').trim();
                        if (text.length < 5) continue;

                        var titleEl = card.querySelector(
                            'h1, h2, h3, h4, [class*="title"], [class*="Title"], [class*="name"]'
                        );
                        var title = titleEl ? titleEl.innerText.trim() : text.split('\\n')[0].trim();
                        if (!title || title.length < 3) continue;

                        var linkEl = card.tagName === 'A' ? card : card.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';

                        var location = '';
                        var department = '';
                        var employment_type = '';

                        var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                        if (locEl) location = locEl.innerText.trim();

                        var deptEl = card.querySelector('[class*="department"], [class*="Department"], [class*="team"]');
                        if (deptEl) department = deptEl.innerText.trim();

                        var typeEl = card.querySelector('[class*="type"], [class*="Type"]');
                        if (typeEl) {
                            var typeText = typeEl.innerText.trim();
                            if (typeText.match(/full|part|contract|intern/i)) {
                                employment_type = typeText;
                            }
                        }

                        // Fallback location from text lines
                        if (!location) {
                            var lines = text.split('\\n');
                            for (var j = 0; j < lines.length; j++) {
                                var line = lines[j].trim();
                                if (line.match(/Mumbai|Pune|Bangalore|Delhi|Noida|India|Hyderabad|Chennai/i)) {
                                    location = line;
                                    break;
                                }
                            }
                        }

                        var key = url || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        results.push({
                            title: title, url: url, location: location,
                            department: department, employment_type: employment_type
                        });
                    }
                }

                // Strategy 2: Links to job detail pages
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll(
                        'a[href*="/job/"], a[href*="/jobs/"], a[href*="/career/"], ' +
                        'a[href*="/position/"], a[href*="jobId="]'
                    );
                    for (var i = 0; i < jobLinks.length; i++) {
                        var link = jobLinks[i];
                        var href = link.href;
                        if (seen[href]) continue;

                        var linkText = link.innerText.trim();
                        if (linkText.length < 5 || linkText.length > 200) continue;
                        var lower = linkText.toLowerCase();
                        if (lower === 'apply' || lower === 'view' || lower === 'more') continue;

                        seen[href] = true;

                        var parent = link.closest('div, li, article');
                        var parentText = parent ? parent.innerText : linkText;
                        var loc = '';
                        var pLines = parentText.split('\\n');
                        for (var j = 0; j < pLines.length; j++) {
                            if (pLines[j].match(/Mumbai|Pune|Bangalore|Delhi|India/i)) {
                                loc = pLines[j].trim();
                                break;
                            }
                        }

                        results.push({
                            title: linkText.split('\\n')[0].trim(),
                            url: href, location: loc,
                            department: '', employment_type: ''
                        });
                    }
                }

                // Strategy 3: Generic text-based extraction
                if (results.length === 0) {
                    // Look for any structured list of items that look like job listings
                    var listItems = document.querySelectorAll('li, div[role="listitem"], div[class*="list-item"]');
                    for (var i = 0; i < listItems.length; i++) {
                        var item = listItems[i];
                        var text = (item.innerText || '').trim();
                        var lines = text.split('\\n');
                        if (lines.length >= 2 && lines[0].length >= 5 && lines[0].length < 150) {
                            var title = lines[0].trim();
                            var linkEl = item.querySelector('a[href]');
                            var url = linkEl ? linkEl.href : '';

                            if (seen[url || title]) continue;
                            seen[url || title] = true;

                            var loc = '';
                            for (var j = 1; j < lines.length; j++) {
                                if (lines[j].match(/Mumbai|Pune|Bangalore|Delhi|India/i)) {
                                    loc = lines[j].trim();
                                    break;
                                }
                            }

                            results.push({
                                title: title, url: url, location: loc,
                                department: '', employment_type: ''
                            });
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"DOM extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    employment_type = jdata.get('employment_type', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    job_id = f"zee_dom_{idx}"
                    if url:
                        id_match = re.search(r'(?:job|position|jobId)[=/]([a-zA-Z0-9_-]+)', url)
                        if id_match:
                            job_id = id_match.group(1)
                        else:
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue
                    scraped_ids.add(ext_id)

                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("DOM extraction found no jobs")
                try:
                    body_preview = driver.execute_script(
                        "return document.body ? document.body.innerText.substring(0, 500) : ''"
                    )
                    logger.info(f"Page preview: {body_preview}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"DOM extraction error: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to next page in SenseHQ careers portal."""
        try:
            clicked = driver.execute_script("""
                var nextSelectors = [
                    'button[aria-label="Next"]', 'a[aria-label="Next"]',
                    'button[class*="next"]', 'a[class*="next"]',
                    '.pagination .next a', 'li.next a',
                    '[class*="pagination"] [class*="next"]',
                    'button:has(svg[class*="chevron-right"])',
                    'button[class*="load-more"]', 'button[class*="show-more"]',
                    'button[class*="loadMore"]', 'a[class*="loadMore"]'
                ];

                for (var i = 0; i < nextSelectors.length; i++) {
                    try {
                        var btn = document.querySelector(nextSelectors[i]);
                        if (btn && btn.offsetParent !== null) {
                            btn.click();
                            return true;
                        }
                    } catch(e) {}
                }

                // Try infinite scroll trigger
                window.scrollTo(0, document.body.scrollHeight);
                return false;
            """)

            if clicked:
                logger.info("Navigated to next page")
                time.sleep(5)
                return True

            logger.info("No next page control found")
            return False
        except Exception as e:
            logger.error(f"Pagination error: {str(e)}")
            return False

if __name__ == "__main__":
    scraper = ZeeEntertainmentScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

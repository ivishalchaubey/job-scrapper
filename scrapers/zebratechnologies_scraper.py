from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import re

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('zebratechnologies_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class ZebraTechnologiesScraper:
    def __init__(self):
        self.company_name = 'Zebra Technologies'
        self.primary_url = 'https://careers.zebra.com/careers'
        self.icims_url = 'https://jobs-zebra.icims.com/jobs/search?pr=1&searchLocation=12781--India&schession=1'
        self.icims_base = 'https://jobs-zebra.icims.com'

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
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception:
            driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Strategy 1: Try iCIMS portal first (server-rendered HTML, more reliable)
            logger.info(f"Strategy 1: Trying iCIMS portal at {self.icims_url}")
            icims_jobs = self._scrape_icims(driver, max_pages)
            if icims_jobs:
                logger.info(f"iCIMS portal returned {len(icims_jobs)} jobs")
                all_jobs.extend(icims_jobs)
            else:
                # Strategy 2: Try primary careers site (custom SPA)
                logger.info(f"Strategy 2: Trying primary site at {self.primary_url}")
                primary_jobs = self._scrape_primary_site(driver, max_pages)
                if primary_jobs:
                    logger.info(f"Primary site returned {len(primary_jobs)} jobs")
                    all_jobs.extend(primary_jobs)
                else:
                    # Strategy 3: Try alternate iCIMS URLs
                    logger.info("Strategy 3: Trying alternate iCIMS URLs...")
                    alternate_urls = [
                        'https://jobs-zebra.icims.com/jobs/search?pr=1&searchLocation=India',
                        'https://jobs-zebra.icims.com/jobs/search?ss=1&searchLocation=12781--India',
                        'https://jobs-zebra.icims.com/jobs/intro',
                    ]
                    for alt_url in alternate_urls:
                        try:
                            logger.info(f"Trying: {alt_url}")
                            driver.get(alt_url)
                            time.sleep(8)
                            alt_jobs = self._extract_icims_jobs(driver, set())
                            if alt_jobs:
                                logger.info(f"Found {len(alt_jobs)} jobs at {alt_url}")
                                all_jobs.extend(alt_jobs)
                                break
                        except Exception as e:
                            logger.warning(f"Alternate URL {alt_url} failed: {str(e)}")
                            continue

            logger.info(f"Successfully scraped {len(all_jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _scrape_icims(self, driver, max_pages):
        """Scrape jobs from iCIMS portal (server-rendered HTML)."""
        jobs = []
        scraped_ids = set()

        try:
            driver.get(self.icims_url)

            # iCIMS portals render server-side HTML, but may have additional JS loading
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        '.iCIMS_JobsTable, .iCIMS_MainWrapper, '
                        'div[class*="job"], div[id*="job"], '
                        'table[class*="job"], #jobSearchResultsGrid'
                    ))
                )
                logger.info("iCIMS page elements detected")
            except Exception as e:
                logger.warning(f"iCIMS page load timeout: {str(e)}")
                time.sleep(8)

            # Scroll to load any lazy elements
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            page_num = 1
            while page_num <= max_pages:
                page_jobs = self._extract_icims_jobs(driver, scraped_ids)

                if not page_jobs:
                    if page_num == 1:
                        logger.warning("No jobs found on iCIMS first page")
                    break

                jobs.extend(page_jobs)
                logger.info(f"iCIMS page {page_num}: {len(page_jobs)} jobs (total: {len(jobs)})")

                if not self._go_to_next_icims_page(driver, page_num):
                    break
                page_num += 1
                time.sleep(5)

        except Exception as e:
            logger.error(f"iCIMS scraping error: {str(e)}")

        return jobs

    def _extract_icims_jobs(self, driver, scraped_ids):
        """Extract job listings from iCIMS HTML DOM."""
        jobs = []
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: iCIMS job table rows
                var tableRows = document.querySelectorAll(
                    '.iCIMS_JobsTable tr, table[class*="job"] tbody tr, ' +
                    '#jobSearchResultsGrid tr, tr[class*="job"]'
                );
                if (tableRows.length > 0) {
                    for (var i = 0; i < tableRows.length; i++) {
                        var row = tableRows[i];
                        var linkEl = row.querySelector('a[href*="jobs/"], a[href*="job/"]');
                        if (!linkEl) continue;

                        var title = linkEl.innerText.trim();
                        var url = linkEl.href;
                        if (!title || title.length < 3 || !url) continue;
                        if (seen[url]) continue;
                        seen[url] = true;

                        var cells = row.querySelectorAll('td');
                        var location = '';
                        var department = '';
                        var posted_date = '';

                        // Parse table cells for metadata
                        for (var j = 0; j < cells.length; j++) {
                            var cellText = cells[j].innerText.trim();
                            if (cellText.match(/India|Pune|Bangalore|Bengaluru|Hyderabad|Chennai|Mumbai|Delhi/i)) {
                                if (!location) location = cellText;
                            }
                            if (cellText.match(/\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}|\\d{4}-\\d{2}-\\d{2}/)) {
                                if (!posted_date) posted_date = cellText;
                            }
                        }

                        results.push({
                            title: title, url: url, location: location,
                            department: department, posted_date: posted_date
                        });
                    }
                }

                // Strategy 2: iCIMS job card/list items
                if (results.length === 0) {
                    var jobCards = document.querySelectorAll(
                        '.iCIMS_JobSearchResult, div[class*="iCIMS_Job"], ' +
                        'div[class*="job-card"], div[class*="job-result"], ' +
                        'div[class*="search-result"], li[class*="job"]'
                    );
                    for (var i = 0; i < jobCards.length; i++) {
                        var card = jobCards[i];
                        var text = (card.innerText || '').trim();
                        if (text.length < 10) continue;

                        var titleEl = card.querySelector(
                            'a[href*="jobs/"], a[href*="job/"], ' +
                            'h2, h3, h4, [class*="title"], [class*="Title"]'
                        );
                        var title = '';
                        var url = '';

                        if (titleEl && titleEl.tagName === 'A') {
                            title = titleEl.innerText.trim();
                            url = titleEl.href;
                        } else if (titleEl) {
                            title = titleEl.innerText.trim();
                            var linkEl = card.querySelector('a[href]');
                            url = linkEl ? linkEl.href : '';
                        } else {
                            title = text.split('\\n')[0].trim();
                            var linkEl = card.querySelector('a[href]');
                            url = linkEl ? linkEl.href : '';
                        }

                        if (!title || title.length < 3) continue;
                        if (seen[url || title]) continue;
                        seen[url || title] = true;

                        var location = '';
                        var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                        if (locEl) location = locEl.innerText.trim();
                        if (!location) {
                            var lines = text.split('\\n');
                            for (var j = 0; j < lines.length; j++) {
                                if (lines[j].match(/India|Pune|Bangalore|Hyderabad|Chennai|Mumbai/i)) {
                                    location = lines[j].trim();
                                    break;
                                }
                            }
                        }

                        var department = '';
                        var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                        if (deptEl) department = deptEl.innerText.trim();

                        results.push({
                            title: title, url: url, location: location,
                            department: department, posted_date: ''
                        });
                    }
                }

                // Strategy 3: All job-related links
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll(
                        'a[href*="/jobs/"], a[href*="/job/"], a[href*="job-id"], ' +
                        'a[href*="icims"]'
                    );
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var href = link.href;
                        var linkText = link.innerText.trim();
                        if (linkText.length < 5 || linkText.length > 200) continue;
                        var lower = linkText.toLowerCase();
                        if (lower === 'apply' || lower === 'view' || lower === 'search' ||
                            lower === 'home' || lower === 'sign in' || lower === 'register') continue;
                        if (seen[href]) continue;
                        seen[href] = true;

                        var parent = link.closest('div, tr, li');
                        var parentText = parent ? parent.innerText : linkText;
                        var loc = '';
                        var pLines = parentText.split('\\n');
                        for (var j = 0; j < pLines.length; j++) {
                            if (pLines[j].match(/India|Pune|Bangalore|Hyderabad|Chennai|Mumbai/i)) {
                                loc = pLines[j].trim();
                                break;
                            }
                        }

                        results.push({
                            title: linkText.split('\\n')[0].trim(),
                            url: href, location: loc,
                            department: '', posted_date: ''
                        });
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"iCIMS extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    posted_date = jdata.get('posted_date', '').strip()

                    if not title or len(title) < 3:
                        continue
                    # Skip non-India jobs
                    title_lower = title.lower()
                    if title_lower in ['search jobs', 'job search', 'careers', 'home']:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    # Generate job ID from iCIMS URL or fallback
                    job_id = f"zebra_{idx}"
                    if url:
                        # iCIMS URLs typically contain /jobs/NNNN/job
                        icims_match = re.search(r'/jobs/(\d+)', url)
                        if icims_match:
                            job_id = icims_match.group(1)
                        else:
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue
                    scraped_ids.add(ext_id)

                    loc_data = self.parse_location(location)

                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': 'India',
                        'employment_type': '',
                        'department': department,
                        'apply_url': url if url else self.icims_url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("iCIMS extraction found no jobs")
                try:
                    body_preview = driver.execute_script(
                        "return document.body ? document.body.innerText.substring(0, 500) : ''"
                    )
                    logger.info(f"iCIMS page preview: {body_preview}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"iCIMS extraction error: {str(e)}")

        return jobs

    def _go_to_next_icims_page(self, driver, current_page):
        """Navigate to next page in iCIMS portal."""
        try:
            clicked = driver.execute_script("""
                // iCIMS pagination
                var nextSelectors = [
                    'a[class*="iCIMS_PagingNext"], a[class*="paging-next"]',
                    'a[aria-label="Next"], button[aria-label="Next"]',
                    'a[title="Next Page"], a[class*="next"]',
                    '.iCIMS_Paging a:last-child',
                    'li.next a, .pagination .next a'
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

                // Numbered pagination
                var nextPage = """ + str(current_page + 1) + """;
                var pageLinks = document.querySelectorAll(
                    '.iCIMS_Paging a, [class*="pagination"] a, [class*="pager"] a'
                );
                for (var i = 0; i < pageLinks.length; i++) {
                    if (pageLinks[i].innerText.trim() === String(nextPage)) {
                        pageLinks[i].click();
                        return true;
                    }
                }

                return false;
            """)

            if clicked:
                logger.info(f"Navigated to iCIMS page {current_page + 1}")
                time.sleep(5)
                return True

            logger.info("No next page found in iCIMS")
            return False
        except Exception as e:
            logger.error(f"iCIMS pagination error: {str(e)}")
            return False

    def _scrape_primary_site(self, driver, max_pages):
        """Scrape jobs from the primary careers.zebra.com SPA site."""
        jobs = []
        scraped_ids = set()

        try:
            driver.get(self.primary_url)

            # Wait for SPA to render
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'div[class*="job"], div[class*="career"], div[class*="position"], '
                        'a[class*="job"], div[class*="search-result"]'
                    ))
                )
                logger.info("Primary site job elements detected")
            except Exception as e:
                logger.warning(f"Primary site load timeout: {str(e)}")
                time.sleep(10)

            # Try to filter by India location
            self._apply_india_filter(driver)
            time.sleep(5)

            # Scroll to load all content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            page_num = 1
            while page_num <= max_pages:
                page_jobs = self._extract_primary_site_jobs(driver, scraped_ids)

                if not page_jobs:
                    break

                jobs.extend(page_jobs)
                logger.info(f"Primary site page {page_num}: {len(page_jobs)} jobs (total: {len(jobs)})")

                if not self._go_to_next_primary_page(driver):
                    break
                page_num += 1
                time.sleep(5)

        except Exception as e:
            logger.error(f"Primary site scraping error: {str(e)}")

        return jobs

    def _apply_india_filter(self, driver):
        """Try to apply India location filter on the primary careers site."""
        try:
            driver.execute_script("""
                // Try to find and click location filter/dropdown
                var filterSelectors = [
                    'input[placeholder*="location"], input[placeholder*="Location"]',
                    'input[class*="location"], input[class*="search"]',
                    'select[class*="location"], select[name*="location"]',
                    'button[class*="location"], button[aria-label*="location"]'
                ];

                for (var i = 0; i < filterSelectors.length; i++) {
                    try {
                        var el = document.querySelector(filterSelectors[i]);
                        if (el) {
                            if (el.tagName === 'INPUT') {
                                el.value = 'India';
                                el.dispatchEvent(new Event('input', {bubbles: true}));
                                el.dispatchEvent(new Event('change', {bubbles: true}));
                            } else if (el.tagName === 'SELECT') {
                                for (var j = 0; j < el.options.length; j++) {
                                    if (el.options[j].text.includes('India')) {
                                        el.selectedIndex = j;
                                        el.dispatchEvent(new Event('change', {bubbles: true}));
                                        break;
                                    }
                                }
                            } else {
                                el.click();
                            }
                            return true;
                        }
                    } catch(e) {}
                }

                // Try URL-based filtering
                if (!window.location.search.includes('India')) {
                    var sep = window.location.search ? '&' : '?';
                    window.location.search += sep + 'location=India';
                }

                return false;
            """)
        except Exception as e:
            logger.warning(f"Could not apply India filter: {str(e)}")

    def _extract_primary_site_jobs(self, driver, scraped_ids):
        """Extract job listings from the primary careers.zebra.com DOM."""
        jobs = []
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                var cardSelectors = [
                    'div[class*="job-card"], div[class*="jobCard"]',
                    'div[class*="job-listing"], div[class*="jobListing"]',
                    'div[class*="search-result"], div[class*="result-card"]',
                    'a[class*="job-card"], a[class*="job-link"]',
                    'article[class*="job"], li[class*="job"]',
                    'div[class*="position-card"], div[class*="opening"]'
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
                            'h1, h2, h3, h4, [class*="title"], [class*="Title"]'
                        );
                        var title = titleEl ? titleEl.innerText.trim() : text.split('\\n')[0].trim();
                        if (!title || title.length < 3) continue;

                        var linkEl = card.tagName === 'A' ? card : card.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';

                        var location = '';
                        var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                        if (locEl) location = locEl.innerText.trim();

                        if (!location) {
                            var lines = text.split('\\n');
                            for (var j = 0; j < lines.length; j++) {
                                if (lines[j].match(/India|Pune|Bangalore|Hyderabad|Chennai|Mumbai/i)) {
                                    location = lines[j].trim();
                                    break;
                                }
                            }
                        }

                        var department = '';
                        var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                        if (deptEl) department = deptEl.innerText.trim();

                        var key = url || title;
                        if (seen[key]) continue;
                        seen[key] = true;

                        results.push({
                            title: title, url: url, location: location,
                            department: department
                        });
                    }
                }

                // Fallback: any links that look like job postings
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var href = link.href;
                        var linkText = link.innerText.trim();
                        if (linkText.length < 10 || linkText.length > 150) continue;
                        if (href.includes('icims') || href.includes('job') || href.includes('career') ||
                            href.includes('position')) {
                            var lower = linkText.toLowerCase();
                            if (lower === 'apply' || lower === 'search' || lower === 'home') continue;
                            if (seen[href]) continue;
                            seen[href] = true;

                            results.push({
                                title: linkText.split('\\n')[0].trim(),
                                url: href, location: '', department: ''
                            });
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Primary site extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    job_id = f"zebra_primary_{idx}"
                    if url:
                        icims_match = re.search(r'/jobs/(\d+)', url)
                        if icims_match:
                            job_id = icims_match.group(1)
                        else:
                            id_match = re.search(r'(?:job|position|id)[=/]([a-zA-Z0-9_-]+)', url)
                            if id_match:
                                job_id = id_match.group(1)
                            else:
                                job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue
                    scraped_ids.add(ext_id)

                    loc_data = self.parse_location(location)

                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': 'India',
                        'employment_type': '',
                        'department': department,
                        'apply_url': url if url else self.primary_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

        except Exception as e:
            logger.error(f"Primary site extraction error: {str(e)}")

        return jobs

    def _go_to_next_primary_page(self, driver):
        """Navigate to next page on the primary careers site."""
        try:
            clicked = driver.execute_script("""
                var nextSelectors = [
                    'button[aria-label="Next"]', 'a[aria-label="Next"]',
                    'button[class*="next"]', 'a[class*="next"]',
                    '.pagination .next a', 'li.next a',
                    '[class*="pagination"] [class*="next"]',
                    'button[class*="load-more"]', 'button[class*="show-more"]'
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

                return false;
            """)

            if clicked:
                logger.info("Navigated to next page on primary site")
                time.sleep(5)
                return True

            return False
        except Exception as e:
            logger.error(f"Primary site pagination error: {str(e)}")
            return False


if __name__ == "__main__":
    scraper = ZebraTechnologiesScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

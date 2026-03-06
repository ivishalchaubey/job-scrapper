from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('starhealth_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class StarHealthScraper:
    def __init__(self):
        self.company_name = 'Star Health Insurance'
        # Star Health has migrated from PeopleStrong to DarwinBox.
        # The old PeopleStrong portal (starhealthcareers.peoplestrong.com)
        # returns 0 jobs and has empty master data (worksites, orgunit).
        # The new DarwinBox v2 portal is at starhealth.darwinbox.in.
        self.url = 'https://starhealth.darwinbox.in/ms/candidatev2/main/careers/allJobs'
        # DarwinBox v1 URL (the v2 SPA may redirect here when active)
        self.darwinbox_v1_url = 'https://starhealth.darwinbox.in/ms/candidate/careers'
        # Keep the old PeopleStrong URL as a fallback
        self.peoplestrong_url = 'https://starhealthcareers.peoplestrong.com/job/joblist'

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
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
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
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]

        city = ''
        state = ''
        for part in parts:
            part_clean = part.strip()
            if part_clean == 'India':
                continue
            if '#' in part_clean or '_' in part_clean:
                if '(' in part_clean and ')' in part_clean:
                    state = part_clean.split('(')[-1].split(')')[0].strip()
                continue
            if '..+' in part_clean:
                continue
            if not city:
                city = part_clean
            elif not state:
                state = part_clean

        return city, state, 'India'

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Star Health Insurance careers page.

        Star Health has migrated from PeopleStrong to DarwinBox v2.
        This scraper tries the DarwinBox portal first, then falls back
        to the legacy PeopleStrong portal if DarwinBox yields no results.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # --- Strategy 1a: DarwinBox v2 SPA portal ---
            logger.info(f"Trying DarwinBox v2 portal: {self.url}")
            driver.get(self.url)
            time.sleep(15)

            body_text = driver.find_element(By.TAG_NAME, 'body').text.strip()
            logger.info(f"DarwinBox v2 page body length: {len(body_text)}")

            if body_text and body_text != '-' and len(body_text) > 20:
                # DarwinBox SPA loaded with content -- scrape it
                for i in range(5):
                    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                    time.sleep(2)
                driver.execute_script('window.scrollTo(0, 0);')
                time.sleep(2)

                jobs = self._scrape_darwinbox_jobs(driver)
                if jobs:
                    logger.info(f"DarwinBox v2 portal returned {len(jobs)} jobs")
                    return jobs
                else:
                    logger.info("DarwinBox v2 portal loaded but no job tiles found")
            else:
                logger.info("DarwinBox v2 portal has no content or is not yet active")

            # --- Strategy 1b: DarwinBox v1 table portal ---
            logger.info(f"Trying DarwinBox v1 portal: {self.darwinbox_v1_url}")
            driver.get(self.darwinbox_v1_url)
            time.sleep(15)

            body_text = driver.find_element(By.TAG_NAME, 'body').text.strip()
            logger.info(f"DarwinBox v1 page body length: {len(body_text)}")

            if body_text and body_text != '-' and len(body_text) > 20:
                jobs = self._scrape_darwinbox_v1_table(driver, max_pages)
                if jobs:
                    logger.info(f"DarwinBox v1 portal returned {len(jobs)} jobs")
                    return jobs
                else:
                    logger.info("DarwinBox v1 portal loaded but no job rows found")
            else:
                logger.info("DarwinBox v1 portal has no content or is not yet active")

            # --- Strategy 2: Legacy PeopleStrong portal ---
            logger.info(f"Falling back to PeopleStrong portal: {self.peoplestrong_url}")
            driver.get(self.peoplestrong_url)
            time.sleep(15)

            body_text = driver.execute_script(
                "return (document.body.innerText || '').toLowerCase()"
            )
            if 'no jobs available' in body_text or 'no openings' in body_text:
                logger.info("PeopleStrong portal reports no jobs available at this time")
                return jobs

            # Scroll to load content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try to load more jobs
            for _ in range(max_pages):
                try:
                    load_more = driver.find_elements(By.XPATH,
                        '//button[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View More")]'
                        ' | //a[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View More")]')
                    if load_more:
                        driver.execute_script("arguments[0].click();", load_more[0])
                        logger.info("Clicked 'Load More' button")
                        time.sleep(3)
                    else:
                        break
                except Exception:
                    break

            jobs = self._extract_peoplestrong_jobs(driver)
            logger.info(f"PeopleStrong portal returned {len(jobs)} jobs")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _scrape_darwinbox_jobs(self, driver):
        """Extract jobs from the DarwinBox v2 allJobs page using JavaScript."""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // DarwinBox v2 (/candidatev2/) uses job tiles and jobDetails links
                var tiles = document.querySelectorAll('div.job-tile, div.jobs-section, div[class*="job-card"], div[class*="job-item"], div[class*="job-listing"]');
                if (tiles.length === 0) {
                    var jobLinks = document.querySelectorAll('a[href*="jobDetails"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var link = jobLinks[i];
                        var container = link.closest('div[class]') || link.parentElement;
                        var text = (container.innerText || '').trim();
                        var title = text.split('\\n')[0].trim();
                        if (title.length >= 3 && title !== 'View and Apply' && title !== 'Apply') {
                            results.push({
                                title: title,
                                url: link.href,
                                location: '',
                                experience: '',
                                employment_type: ''
                            });
                        }
                    }
                    return results;
                }

                for (var i = 0; i < tiles.length; i++) {
                    var tile = tiles[i];
                    var text = (tile.innerText || '').trim();
                    if (text.length < 5) continue;

                    var titleEl = tile.querySelector('span.job-title, .title-section, h3, h4, [class*="title"]');
                    var title = titleEl ? titleEl.innerText.trim() : text.split('\\n')[0].trim();

                    var linkEl = tile.querySelector('a[href*="jobDetails"]');
                    var url = linkEl ? linkEl.href : '';

                    var lines = text.split('\\n');
                    var location = '';
                    var experience = '';
                    var employment_type = '';
                    for (var j = 0; j < lines.length; j++) {
                        var line = lines[j].trim();
                        if (line.includes('India') || line.includes('Haryana') || line.includes('Gujarat') ||
                            line.includes('Maharashtra') || line.includes('Karnataka') || line.includes('Goa') ||
                            line.includes('Delhi') || line.includes('Tamil Nadu') || line.includes('Rajasthan') ||
                            line.includes('Odisha') || line.includes('Jharkhand') || line.includes('Chhattisgarh') ||
                            line.includes('Andhra Pradesh') || line.includes('Telangana') || line.includes('Kerala') ||
                            line.includes('Punjab') || line.includes('West Bengal') || line.includes('Uttar Pradesh') ||
                            line.includes('Bengaluru') || line.includes('Bangalore') || line.includes('Mumbai') ||
                            line.includes('Chennai') || line.includes('Hyderabad') || line.includes('Pune') ||
                            line.includes('Gurgaon') || line.includes('Gurugram') || line.includes('Noida') ||
                            line.includes('Kolkata') || line.includes('Manesar')) {
                            location = line;
                        }
                        if (line.includes('Years') || line.includes('years')) {
                            experience = line;
                        }
                        if (line === 'Permanent' || line === 'Contract' || line === 'Probation' || line === 'Intern' || line === 'Full Time' || line === 'Part Time') {
                            employment_type = line;
                        }
                    }

                    if (title.length >= 3 && title !== 'View and Apply') {
                        results.push({
                            title: title,
                            url: url,
                            location: location,
                            experience: experience,
                            employment_type: employment_type
                        });
                    }
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"DarwinBox extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    url = job_data.get('url', '')
                    location = job_data.get('location', '')
                    experience = job_data.get('experience', '')
                    employment_type = job_data.get('employment_type', '')

                    if not title:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    city, state, country = self.parse_location(location)

                    job_id = f"starhealth_{idx}"
                    if url and 'jobDetails/' in url:
                        job_id = url.split('jobDetails/')[-1].split('?')[0]
                    elif url:
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    jobs.append({
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
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.info("No job tiles found on DarwinBox page")

        except Exception as e:
            logger.error(f"DarwinBox extraction error: {str(e)}")

        return jobs

    def _scrape_darwinbox_v1_table(self, driver, max_pages):
        """Extract jobs from the DarwinBox v1 server-rendered table layout.

        DarwinBox v1 uses a table.db-table-one with rows containing cells for:
        title (with link), department, location, employee type, posted date.
        Pagination uses li.pagination-next.
        """
        all_jobs = []

        current_page = 1
        while current_page <= max_pages:
            logger.info(f"Scraping DarwinBox v1 page {current_page}")

            try:
                js_jobs = driver.execute_script("""
                    var results = [];
                    var seen = {};
                    var table = document.querySelector('table.db-table-one');
                    if (table) {
                        var rows = table.querySelectorAll('tbody tr');
                        for (var i = 0; i < rows.length; i++) {
                            var cells = rows[i].querySelectorAll('td');
                            if (cells.length < 4) continue;
                            var titleCell = cells[0];
                            var link = titleCell.querySelector('a[href*="/careers/"]');
                            var title = (link ? link.innerText : titleCell.innerText).trim();
                            var href = link ? link.href : '';
                            if (!title || title.length < 3 || seen[href || title]) continue;
                            seen[href || title] = true;
                            var department = cells.length > 1 ? cells[1].innerText.trim() : '';
                            var location = cells.length > 2 ? cells[2].innerText.trim() : '';
                            var employeeType = cells.length > 3 ? cells[3].innerText.trim() : '';
                            var postedDate = cells.length > 4 ? cells[4].innerText.trim() : '';
                            results.push({
                                title: title, url: href, department: department,
                                location: location, employment_type: employeeType,
                                posted_date: postedDate
                            });
                        }
                    }
                    if (results.length === 0) {
                        var links = document.querySelectorAll('a[href*="/careers/"]');
                        for (var i = 0; i < links.length; i++) {
                            var a = links[i];
                            var text = a.innerText.trim();
                            var href = a.href;
                            if (!text || text.length < 3 || text === 'apply here' ||
                                text.includes('LOGIN') || text.includes('SIGN UP')) continue;
                            if (seen[href]) continue;
                            seen[href] = true;
                            var row = a.closest('tr');
                            var dept = '', loc = '', empType = '', postDate = '';
                            if (row) {
                                var cells = row.querySelectorAll('td');
                                if (cells.length > 1) dept = cells[1].innerText.trim();
                                if (cells.length > 2) loc = cells[2].innerText.trim();
                                if (cells.length > 3) empType = cells[3].innerText.trim();
                                if (cells.length > 4) postDate = cells[4].innerText.trim();
                            }
                            results.push({
                                title: text, url: href, department: dept,
                                location: loc, employment_type: empType,
                                posted_date: postDate
                            });
                        }
                    }
                    return results;
                """)

                if js_jobs:
                    logger.info(f"DarwinBox v1 found {len(js_jobs)} jobs on page {current_page}")
                    seen_urls = {j['apply_url'] for j in all_jobs if j.get('apply_url')}
                    for idx, jd in enumerate(js_jobs):
                        title = jd.get('title', '')
                        url = jd.get('url', '')
                        if not title or (url and url in seen_urls):
                            continue
                        if url:
                            seen_urls.add(url)

                        location = jd.get('location', '')
                        city, state, country = self.parse_location(location)
                        job_id = f"starhealth_{len(all_jobs) + idx}"
                        if url and '/careers/' in url:
                            job_id = url.split('/careers/')[-1].split('?')[0].split('/')[0]
                        elif url:
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                        all_jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': country,
                            'employment_type': jd.get('employment_type', ''),
                            'department': jd.get('department', ''),
                            'apply_url': url if url else self.darwinbox_v1_url,
                            'posted_date': jd.get('posted_date', ''),
                            'job_function': jd.get('department', ''),
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })
                else:
                    logger.info("No job rows found on current page")
                    break

            except Exception as e:
                logger.error(f"DarwinBox v1 extraction error: {str(e)}")
                break

            # Navigate to next page
            if current_page < max_pages:
                try:
                    next_btn = driver.find_elements(
                        By.CSS_SELECTOR, 'li.pagination-next:not(.disabled) a.page-link'
                    )
                    if next_btn:
                        driver.execute_script("arguments[0].click();", next_btn[0])
                        logger.info("Clicked next page")
                        time.sleep(5)
                    else:
                        break
                except Exception:
                    break

            current_page += 1

        return all_jobs

    def _extract_peoplestrong_jobs(self, driver):
        """Extract jobs from legacy PeopleStrong Angular page using JavaScript."""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: PeopleStrong Angular — jobs-listing container
                var container = document.querySelector('div.jobs-listing');
                if (container) {
                    var jobLinks = container.querySelectorAll('a[href*="/job/"]');
                    for (var i = 0; i < jobLinks.length; i++) {
                        var link = jobLinks[i];
                        var title = link.innerText.trim().split('\\n')[0].trim();
                        var href = link.href;
                        if (!title || title.length < 3 || seen[href]) continue;
                        seen[href] = true;

                        var parent = link.closest('div[class*="clearfix"], div[class*="row"], div, li');
                        var location = '', department = '';
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                            if (locEl) location = locEl.innerText.trim();
                            var deptEl = parent.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="function"]');
                            if (deptEl) department = deptEl.innerText.trim();
                        }
                        results.push({title: title, href: href, location: location, department: department});
                    }
                }

                // Strategy 2: Generic job-related links
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/job/"], a[href*="jobdetail"], a[href*="job-detail"]');
                    for (var i = 0; i < links.length; i++) {
                        var link = links[i];
                        var text = link.innerText.trim().split('\\n')[0].trim();
                        var href = link.href;
                        if (text.length > 3 && text.length < 200 && !seen[text + href]) {
                            seen[text + href] = true;
                            var parent = link.closest('div, li, tr');
                            var loc = '';
                            var dept = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl) loc = locEl.innerText.trim();
                                var deptEl = parent.querySelector('[class*="department"], [class*="Department"]');
                                if (deptEl) dept = deptEl.innerText.trim();
                            }
                            results.push({title: text, href: href, location: loc, department: dept});
                        }
                    }
                }

                return results;
            """)

            if job_data:
                logger.info(f"PeopleStrong extraction found {len(job_data)} jobs")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '')
                    href = jd.get('href', '')
                    location = jd.get('location', '')
                    department = jd.get('department', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5((href or f"{title}_{idx}").encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': department,
                        'apply_url': href if href else self.peoplestrong_url,
                        'posted_date': '',
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.info("No job data found on PeopleStrong page")
        except Exception as e:
            logger.error(f"PeopleStrong extraction failed: {e}")

        return jobs


if __name__ == "__main__":
    scraper = StarHealthScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

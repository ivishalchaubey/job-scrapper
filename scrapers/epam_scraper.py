from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('epam_scraper')

class EPAMScraper:
    def __init__(self):
        self.company_name = "EPAM Systems"
        # Next.js SPA with country filter for India
        self.url = "https://careers.epam.com/en/jobs?country=4060741400035606931"
        self.base_url = 'https://careers.epam.com'
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape EPAM jobs from Next.js SPA.

        EPAM careers uses a Next.js app. Job listings link to individual
        vacancy pages via /en/vacancy/<slug> (not /en/jobs/ which is the
        search page). Location is shown as uppercase text like
        "OFFICE IN INDIA: TELANGANA, HYDERABAD & 4 OTHERS".
        Skills/tags follow in a separate line.
        """
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Wait for the React app to render vacancy links
            logger.info("Waiting for React SPA to render job listings...")
            try:
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("""
                        return document.querySelectorAll('a[href*="/en/vacancy/"]').length;
                    """) > 0
                )
                logger.info("Job vacancy links detected after React render")
            except Exception:
                logger.warning("Timeout waiting for React render, using fallback wait")
                time.sleep(15)

            # Give extra time for all job cards to render
            time.sleep(3)

            # Scroll to trigger lazy-loading of job cards
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            scraped_ids = set()
            page_num = 1

            while page_num <= max_pages:
                page_jobs = self._extract_jobs(driver, scraped_ids)
                if not page_jobs:
                    logger.info(f"No jobs found on page {page_num}, stopping")
                    break
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page_num}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if page_num < max_pages:
                    if not self._go_to_next_page(driver):
                        break
                    time.sleep(5)
                page_num += 1

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs(self, driver, scraped_ids):
        """Extract jobs by finding vacancy links and their parent containers.

        EPAM uses /en/vacancy/<slug> URLs for individual job pages.
        Each job card typically contains:
          - A link with the job title text
          - Location text (uppercase, e.g. "OFFICE IN INDIA: ...")
          - Skills/tags text (e.g. "JAVA & 10 OTHERS")
          - Description paragraph
        """
        jobs = []

        try:
            # Scroll to load all content
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Find all links to individual vacancy pages: /en/vacancy/<slug>
                var allLinks = document.querySelectorAll('a[href*="/en/vacancy/"]');
                for (var i = 0; i < allLinks.length; i++) {
                    var a = allLinks[i];
                    var href = a.href || '';

                    if (!href) continue;
                    if (seen[href]) continue;
                    seen[href] = true;

                    // Walk up to find the JobCard panel container
                    // EPAM uses: JobCard_panel__ > AccordionSection_container__ >
                    //   AccordionSection_header__ > AccordionSection_title__ > <a>
                    var container = a.closest('div[class*="JobCard_panel"]');
                    if (!container) {
                        // Fallback: walk up 4 levels from the link
                        container = a;
                        for (var up = 0; up < 4; up++) {
                            if (container.parentElement) container = container.parentElement;
                        }
                    }

                    // Extract title from the link text (first line)
                    var title = a.innerText.trim().split('\\n')[0].trim();

                    if (!title || title.length < 3 || title.length > 250) continue;

                    // Skip generic navigation text
                    if (/^(View|Apply|Save|Share|Sign|Log|Home|About|Back|Search|Filter|Clear|Reset|Next|Previous|Show|Load|More|Menu|Close|Open|Cookie|Privacy|Terms|Contact|Blog|News|EPAM|Career|Explore)/i.test(title)) continue;

                    // Extract location from the card container
                    // EPAM shows: "OFFICE IN INDIA: TELANGANA, HYDERABAD & 4 OTHERS"
                    var location = '';
                    var text = container.innerText || '';
                    var lines = text.split('\\n');
                    for (var j = 0; j < lines.length; j++) {
                        var line = lines[j].trim();
                        if (line === title) continue;
                        // Location lines start with OFFICE, HYBRID, REMOTE or contain IN INDIA
                        if (/^(OFFICE|HYBRID|REMOTE)/i.test(line) ||
                            /IN INDIA/i.test(line)) {
                            location = line;
                            break;
                        }
                    }

                    // If no explicit location marker, look for city names
                    if (!location) {
                        var cities = ['Hyderabad', 'Bangalore', 'Bengaluru', 'Mumbai',
                                      'Delhi', 'Chennai', 'Pune', 'Gurgaon', 'Noida',
                                      'Kolkata', 'Coimbatore', 'India'];
                        for (var k = 0; k < lines.length; k++) {
                            var l = lines[k].trim();
                            if (l === title) continue;
                            for (var m = 0; m < cities.length; m++) {
                                if (l.toUpperCase().indexOf(cities[m].toUpperCase()) !== -1 && l.length < 120) {
                                    location = l;
                                    break;
                                }
                            }
                            if (location) break;
                        }
                    }

                    // Extract skills/department from container
                    var department = '';
                    for (var n = 0; n < lines.length; n++) {
                        var l2 = lines[n].trim();
                        if (l2 === title || l2 === location) continue;
                        // Skills lines are typically short uppercase with & OTHERS
                        if (l2.length > 3 && l2.length < 100 &&
                            /^[A-Z]/.test(l2) && l2 !== location &&
                            !/^(OFFICE|HYBRID|REMOTE|We are|You will|As a)/i.test(l2)) {
                            department = l2;
                            break;
                        }
                    }

                    // Extract description (longer text block)
                    var description = '';
                    for (var p = 0; p < lines.length; p++) {
                        var pLine = lines[p].trim();
                        if (pLine.length > 80 && pLine !== title) {
                            description = pLine.substring(0, 1000);
                            break;
                        }
                    }

                    results.push({
                        title: title,
                        url: href,
                        location: location,
                        department: department,
                        description: description
                    });
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} vacancy links")
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    description = jdata.get('description', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    # Extract job ID from URL slug
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if '/en/vacancy/' in url:
                        path_part = url.split('/en/vacancy/')[-1].split('?')[0].split('#')[0]
                        if path_part:
                            job_id = path_part.rstrip('/')

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    # Parse location: "OFFICE IN INDIA: TELANGANA, HYDERABAD & 4 OTHERS"
                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url or self.url,
                        'location': location or 'India',
                        'department': department,
                        'employment_type': '',
                        'description': description,
                        'posted_date': '',
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': loc_data.get('remote_type', ''),
                        'status': 'active'
                    })
                    scraped_ids.add(ext_id)

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script(
                        'return document.body ? document.body.innerText.substring(0, 500) : ""'
                    )
                    logger.info(f"Page body preview: {body_text[:200]}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to the next page of results."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            old_count = driver.execute_script("""
                return document.querySelectorAll('a[href*="/en/vacancy/"]').length;
            """)

            # Try various pagination approaches
            for sel_type, sel_val in [
                (By.XPATH, '//button[contains(text(), "Load more")]'),
                (By.XPATH, '//button[contains(text(), "Show more")]'),
                (By.XPATH, '//button[contains(text(), "load more")]'),
                (By.XPATH, '//button[contains(text(), "show more")]'),
                (By.XPATH, '//a[contains(text(), "Load more")]'),
                (By.CSS_SELECTOR, 'button[class*="load-more"]'),
                (By.CSS_SELECTOR, 'button[class*="show-more"]'),
                (By.CSS_SELECTOR, 'button[class*="loadMore"]'),
                (By.CSS_SELECTOR, 'button[class*="showMore"]'),
                (By.CSS_SELECTOR, '[class*="pagination"] [class*="next"]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a[class*="next"]'),
                (By.CSS_SELECTOR, 'button[class*="next"]'),
                # EPAM specific: numbered page links
                (By.CSS_SELECTOR, '[class*="Pagination"] a:not([class*="active"])'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", btn
                        )
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", btn)

                        # Wait for new content
                        for _ in range(25):
                            time.sleep(0.2)
                            new_count = driver.execute_script("""
                                return document.querySelectorAll('a[href*="/en/vacancy/"]').length;
                            """)
                            if new_count != old_count:
                                break
                        time.sleep(0.5)
                        logger.info("Navigated to next page / loaded more results")
                        return True
                except Exception:
                    continue

            return False
        except Exception:
            return False

    def parse_location(self, location_str):
        """Parse EPAM location strings.

        EPAM locations look like:
        "OFFICE IN INDIA: TELANGANA, HYDERABAD & 4 OTHERS"
        "HYBRID IN INDIA: TELANGANA, HYDERABAD"
        "REMOTE"
        """
        result = {'city': '', 'state': '', 'country': 'India', 'remote_type': ''}
        if not location_str:
            return result

        loc_upper = location_str.upper()

        # Detect work type
        if loc_upper.startswith('OFFICE'):
            result['remote_type'] = 'Office'
        elif loc_upper.startswith('HYBRID'):
            result['remote_type'] = 'Hybrid'
        elif loc_upper.startswith('REMOTE'):
            result['remote_type'] = 'Remote'

        # Extract city/state from "IN INDIA: STATE, CITY" pattern
        if ':' in location_str:
            after_colon = location_str.split(':')[-1].strip()
            # Remove "& N OTHERS" suffix
            after_colon = after_colon.split('&')[0].strip()
            parts = [p.strip() for p in after_colon.split(',')]
            if len(parts) >= 2:
                result['state'] = parts[0]
                result['city'] = parts[1]
            elif len(parts) == 1 and parts[0]:
                result['city'] = parts[0]
        else:
            # Fallback comma parsing
            parts = [p.strip() for p in location_str.split(',')]
            if len(parts) >= 1:
                result['city'] = parts[0]
            if len(parts) >= 3:
                result['state'] = parts[1]
                result['country'] = parts[2]
            elif len(parts) == 2:
                result['country'] = parts[1]

        if 'India' in location_str or 'INDIA' in location_str:
            result['country'] = 'India'
        return result

if __name__ == "__main__":
    scraper = EPAMScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

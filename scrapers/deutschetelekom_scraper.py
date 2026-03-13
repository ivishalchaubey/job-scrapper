from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('deutschetelekom_scraper')

class DeutscheTelekomScraper:
    def __init__(self):
        self.company_name = "Deutsche Telekom"
        # Eightfold AI PCSX platform -- redirected from telekom.eightfold.ai
        self.url = "https://careers.telekom.com/en/jobs?location=India"
        self.base_url = 'https://growthhub.telekom.com'
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Deutsche Telekom jobs from Eightfold AI PCSX platform.

        The careers page is at growthhub.telekom.com/careers (redirected from
        telekom.eightfold.ai). The old API (/api/apply/v2/jobs) returns
        'Not authorized for PCSX', so we use Selenium with Eightfold PCSX
        CSS module selectors:
          - div[class*="cardContainer"] for card wrappers
          - a[class*="card-"] for card links with href="/careers/job/{id}"
          - div[class*="title-"] for job titles
          - div[class*="fieldValue"] for location (1st) and department (2nd)
          - div[class*="subData"] for posted date

        Note: Deutsche Telekom currently has 0 India positions. The scraper
        will return an empty list when there are no India jobs available.
        """
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_selenium(self, max_pages):
        """Selenium-based scraping for Eightfold AI PCSX platform."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            driver.get(self.url)

            # Wait for Eightfold PCSX card containers to render
            try:
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'div[class*="cardContainer"]'
                    ))
                )
                logger.info("Eightfold PCSX card containers detected")
            except Exception as e:
                logger.warning(f"Timeout waiting for card containers (may be 0 results): {str(e)}")
                time.sleep(5)
                # Check if the page says "0 jobs"
                body_text = driver.execute_script(
                    'return document.body ? document.body.innerText.substring(0, 1000) : ""'
                )
                if '0 jobs' in body_text or 'didn\'t find any' in body_text.lower():
                    logger.info("No jobs available for this location filter")
                    return all_jobs

            # Extra wait for full SPA hydration
            time.sleep(3)

            # Scroll to load all cards
            for _ in range(4):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            scraped_ids = set()

            # Primary strategy: DOM extraction using CSS module selectors
            dom_jobs = self._extract_from_dom(driver, scraped_ids)
            if dom_jobs:
                all_jobs.extend(dom_jobs)
                logger.info(f"DOM extraction: {len(dom_jobs)} jobs")
            else:
                # Fallback: React fiber extraction
                react_jobs = self._extract_from_react_fiber(driver, scraped_ids)
                all_jobs.extend(react_jobs)
                logger.info(f"React fiber extraction: {len(react_jobs)} jobs")

            # Pagination via Next button
            current_page = 1
            while current_page < max_pages and all_jobs:
                if not self._go_to_next_page(driver):
                    break
                time.sleep(3)
                current_page += 1

                new_dom = self._extract_from_dom(driver, scraped_ids)
                if new_dom:
                    all_jobs.extend(new_dom)
                else:
                    new_react = self._extract_from_react_fiber(driver, scraped_ids)
                    if not new_react:
                        break
                    all_jobs.extend(new_react)

                logger.info(f"Page {current_page}: total {len(all_jobs)} jobs")

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _extract_from_dom(self, driver, scraped_ids):
        """Extract jobs from DOM using Eightfold PCSX CSS module selectors.

        Card structure matches BNY's Eightfold theme:
          div[class*="cardContainer"]
            a[class*="card-"] href="/careers/job/{id}"
              div[class*="title-"]  -> job title
              div[class*="fieldValue"]  -> location (1st), department (2nd)
              div[class*="subData"]  -> posted date
        """
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                var containers = document.querySelectorAll(
                    'div[class*="cardContainer"]'
                );

                for (var i = 0; i < containers.length; i++) {
                    var container = containers[i];
                    var card = container.querySelector('a[class*="card-"]') || container;

                    // Get title from div[class*="title-"]
                    var title = '';
                    var titleEl = card.querySelector('div[class*="title-"]');
                    if (titleEl) title = titleEl.innerText.trim();

                    if (!title || title.length < 3 || title.length > 200) continue;
                    // Skip generic text
                    if (/^(View job|Job search|View|Apply|Save|Share|Sign)/i.test(title)) continue;

                    // Get URL from the card link
                    var url = '';
                    if (card.tagName === 'A') {
                        url = card.href;
                    } else {
                        var link = container.querySelector('a[href*="/careers/job/"]');
                        if (link) url = link.href;
                    }

                    if (url && seen[url]) continue;
                    if (url) seen[url] = true;

                    // Get location and department from fieldValue elements
                    var fieldValues = card.querySelectorAll('div[class*="fieldValue"]');
                    var location = '';
                    var department = '';
                    if (fieldValues.length >= 1) {
                        location = fieldValues[0].innerText.trim();
                    }
                    if (fieldValues.length >= 2) {
                        department = fieldValues[1].innerText.trim();
                    }

                    // Get posted date from subData element
                    var postedDate = '';
                    var subDataEl = card.querySelector('div[class*="subData"]');
                    if (subDataEl) postedDate = subDataEl.innerText.trim();

                    // Extract job ID from URL or card id
                    var jobId = '';
                    if (url) {
                        var match = url.match(/\\/careers\\/job\\/(\\d+)/);
                        if (match) jobId = match[1];
                    }
                    var cardId = card.getAttribute('id') || '';
                    if (!jobId && cardId) {
                        var idMatch = cardId.match(/job-card-(\\d+)/);
                        if (idMatch) jobId = idMatch[1];
                    }

                    results.push({
                        title: title,
                        url: url || '',
                        location: location,
                        department: department,
                        postedDate: postedDate,
                        jobId: jobId
                    });
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"DOM extraction found {len(js_jobs)} cards")
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    posted_date = jdata.get('postedDate', '').strip()
                    job_id = jdata.get('jobId', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    if not job_id:
                        job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location or 'India',
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'employment_type': '',
                        'department': department,
                        'apply_url': url or self.url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                    scraped_ids.add(ext_id)
            else:
                logger.warning("DOM extraction returned no results")
                try:
                    body_text = driver.execute_script(
                        'return document.body ? document.body.innerText.substring(0, 500) : ""'
                    )
                    logger.info(f"Page body preview: {body_text[:200]}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs from DOM: {str(e)}")

        return jobs

    def _extract_from_react_fiber(self, driver, scraped_ids):
        """Fallback: Extract job data from React fiber props on card elements."""
        jobs = []
        try:
            js_results = driver.execute_script("""
                var containers = document.querySelectorAll(
                    'div[class*="cardContainer"]'
                );
                var results = [];
                for (var i = 0; i < containers.length; i++) {
                    var card = containers[i].querySelector('a') || containers[i];
                    var reactKey = Object.keys(card).find(function(k) {
                        return k.startsWith('__reactInternalInstance') ||
                               k.startsWith('__reactFiber');
                    });
                    if (!reactKey) continue;
                    try {
                        var fiber = card[reactKey];
                        var current = fiber;
                        for (var depth = 0; depth < 20; depth++) {
                            if (current && current.memoizedProps &&
                                current.memoizedProps.position) {
                                var pos = current.memoizedProps.position;
                                // Also get location from DOM since fiber may not have it
                                var locEl = card.querySelector('div[class*="fieldValue"]');
                                var domLocation = locEl ? locEl.innerText.trim() : '';

                                results.push({
                                    id: pos.id || '',
                                    name: pos.name || '',
                                    location: pos.location || domLocation || '',
                                    department: pos.department || '',
                                    type: pos.type || '',
                                    t_create: pos.t_create || '',
                                    canonical: pos.canonicalPositionUrl || '',
                                    work_location_option: pos.work_location_option || ''
                                });
                                break;
                            }
                            if (current) current = current.return;
                            else break;
                        }
                    } catch(e) {}
                }
                return results;
            """)

            if js_results:
                logger.info(f"React fiber found {len(js_results)} positions")
                for pos in js_results:
                    title = (pos.get('name', '') or '').strip()
                    if not title:
                        continue

                    job_id = str(pos.get('id', ''))
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    location = pos.get('location', '')
                    if isinstance(location, list) and location:
                        location = location[0] if isinstance(location[0], str) else str(location[0])
                    elif not isinstance(location, str):
                        location = ''

                    apply_url = pos.get('canonical', '')
                    if not apply_url:
                        apply_url = f"{self.base_url}/careers/job/{job_id}"

                    department = pos.get('department', '')
                    if isinstance(department, list) and department:
                        department = department[0]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location or 'India',
                        'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'employment_type': str(pos.get('type', '') or ''),
                        'department': str(department or ''),
                        'apply_url': apply_url,
                        'posted_date': str(pos.get('t_create', '') or ''),
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                    scraped_ids.add(ext_id)
            else:
                logger.warning("React fiber extraction returned no results")

        except Exception as e:
            logger.error(f"React fiber extraction error: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Navigate to the next page of Eightfold AI results."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            old_first = driver.execute_script("""
                var card = document.querySelector(
                    'div[class*="cardContainer"]'
                );
                return card ? card.innerText.substring(0, 50) : '';
            """)

            next_selectors = [
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.XPATH, '//button[contains(@aria-label, "Next")]'),
                (By.CSS_SELECTOR, '[class*="pagination"] button:last-child'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[class*="next"]'),
            ]

            for sel_type, sel_val in next_selectors:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        cls = btn.get_attribute('class') or ''
                        if 'disabled' in cls:
                            continue
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", btn
                        )
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", btn)

                        for _ in range(25):
                            time.sleep(0.2)
                            new_first = driver.execute_script("""
                                var card = document.querySelector(
                                    'div[class*="cardContainer"]'
                                );
                                return card ? card.innerText.substring(0, 50) : '';
                            """)
                            if new_first and new_first != old_first:
                                break
                        time.sleep(0.5)
                        logger.info("Navigated to next page")
                        return True
                except Exception:
                    continue

            return False
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

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
            if parts[1] in ['IN', 'IND', 'India']:
                result['country'] = 'India'
            else:
                result['state'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result

if __name__ == "__main__":
    scraper = DeutscheTelekomScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

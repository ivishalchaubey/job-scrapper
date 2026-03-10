# Fixed: Stay on careerpage URL, do not navigate to /jobs (which returns 404)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from pathlib import Path


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('britannia_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class BritanniaScraper:
    def __init__(self):
        self.company_name = "Britannia Industries"
        self.url = "https://britannia.turbohire.co/dashboardv2?orgId=c143932d-0df7-4856-9dc5-0a9f1ca26dc5&type=0"
        self.base_url = 'https://britannia.turbohire.co'

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
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Auto-detect failed: {str(e)}, trying explicit path")
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
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

            # Wait for TurboHire SPA to fully render
            logger.info("Waiting for TurboHire SPA to render...")
            time.sleep(15)

            logger.info(f"Current URL after load: {driver.current_url}")

            # Scroll to trigger lazy loading of all content on the careerpage
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((i + 1) / 5))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # TurboHire career pages often show department categories that need
            # to be clicked/expanded to reveal individual job listings.
            # Try clicking all expandable department sections.
            self._expand_all_departments(driver)
            time.sleep(3)

            # Try clicking any "View All Jobs" / "View All" / "See All" buttons
            # that stay on the same page (not navigation links).
            self._click_view_all_buttons(driver)
            time.sleep(3)

            # Scroll again after expanding to load any newly revealed content
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((i + 1) / 3))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            for page in range(max_pages):
                page_jobs = self._extract_jobs(driver)
                if not page_jobs:
                    break
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                if not self._go_to_next_page(driver):
                    break
                time.sleep(5)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _expand_all_departments(self, driver):
        """Click on department sections/categories to expand job listings within them."""
        try:
            expanded_count = driver.execute_script("""
                var count = 0;

                // Strategy 1: Click department/category cards or sections
                var deptSelectors = [
                    '[class*="department"]', '[class*="Department"]',
                    '[class*="category"]', '[class*="Category"]',
                    '[class*="team-card"]', '[class*="teamCard"]',
                    '[class*="dept"]', '[class*="Dept"]',
                    '[class*="section-card"]', '[class*="sectionCard"]',
                    '[class*="group-card"]', '[class*="groupCard"]'
                ];

                for (var s = 0; s < deptSelectors.length; s++) {
                    var elements = document.querySelectorAll(deptSelectors[s]);
                    for (var i = 0; i < elements.length; i++) {
                        var el = elements[i];
                        if (el.offsetParent !== null) {  // is visible
                            try { el.click(); count++; } catch(e) {}
                        }
                    }
                    if (count > 0) break;
                }

                // Strategy 2: Click accordion/expandable headers
                if (count === 0) {
                    var accordionSelectors = [
                        '[class*="accordion"]', '[class*="Accordion"]',
                        '[class*="expand"]', '[class*="Expand"]',
                        '[class*="collapse"]', '[class*="Collapse"]',
                        '[role="button"]', '[data-toggle]',
                        '[class*="header"] [class*="arrow"]',
                        '[class*="header"] [class*="chevron"]'
                    ];
                    for (var s = 0; s < accordionSelectors.length; s++) {
                        var elements = document.querySelectorAll(accordionSelectors[s]);
                        for (var i = 0; i < elements.length; i++) {
                            var el = elements[i];
                            if (el.offsetParent !== null) {
                                try { el.click(); count++; } catch(e) {}
                            }
                        }
                        if (count > 0) break;
                    }
                }

                return count;
            """)
            if expanded_count:
                logger.info(f"Expanded {expanded_count} department sections")
            else:
                logger.info("No department sections found to expand")
        except Exception as e:
            logger.warning(f"Error expanding departments: {str(e)}")

    def _click_view_all_buttons(self, driver):
        """Click 'View All Jobs' / 'View All' type buttons that stay on-page (not navigating away)."""
        try:
            clicked = driver.execute_script("""
                var count = 0;
                var buttons = document.querySelectorAll('button, a, span, div');
                for (var i = 0; i < buttons.length; i++) {
                    var el = buttons[i];
                    var text = (el.innerText || '').trim().toLowerCase();
                    // Only click in-page buttons, skip links that would navigate to a different URL
                    if (el.tagName === 'A') {
                        var href = (el.getAttribute('href') || '').toLowerCase();
                        // Skip links that navigate to separate pages (e.g. /jobs, /openings)
                        if (href && href !== '#' && href !== 'javascript:void(0)' && !href.startsWith('javascript:')) {
                            continue;
                        }
                    }
                    if (text === 'view all jobs' || text === 'view all' ||
                        text === 'see all jobs' || text === 'see all' ||
                        text === 'all jobs' || text === 'all openings' ||
                        text === 'view all openings' || text === 'show all' ||
                        text === 'view more' || text === 'show more jobs' ||
                        text === 'load all') {
                        if (el.offsetParent !== null) {
                            try { el.click(); count++; } catch(e) {}
                        }
                    }
                }
                return count;
            """)
            if clicked:
                logger.info(f"Clicked {clicked} 'View All' type buttons on the page")
        except Exception as e:
            logger.warning(f"Error clicking view-all buttons: {str(e)}")

    def _extract_jobs(self, driver):
        jobs = []

        try:
            # Scroll to load all lazy content
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: TurboHire specific - opening cards / job cards
                var cards = document.querySelectorAll(
                    '.opening-card, .job-card, [class*="opening-card"], [class*="openingCard"], ' +
                    '[class*="job-card"], [class*="jobCard"], [class*="job-listing"], [class*="job-item"], ' +
                    '[class*="position-card"], [class*="positionCard"], [class*="career-card"], [class*="careerCard"], ' +
                    '[class*="requisition"], [class*="vacancy"]'
                );

                // If no specific job cards found, try generic cards
                if (cards.length === 0) {
                    cards = document.querySelectorAll('div[class*="card"]');
                    // Filter to only cards that seem to contain job info
                    var filteredCards = [];
                    for (var i = 0; i < cards.length; i++) {
                        var c = cards[i];
                        var text = (c.innerText || '').trim();
                        // Must have reasonable content length and contain a link or job-like text
                        if (text.length > 10 && text.length < 500) {
                            var hasLink = c.querySelector('a[href]');
                            var hasJobKeyword = /manager|engineer|analyst|executive|officer|lead|head|specialist|associate|coordinator|developer|intern|trainee|supervisor|director|senior|junior|designer|consultant|advisor/i.test(text);
                            if (hasLink || hasJobKeyword) {
                                filteredCards.push(c);
                            }
                        }
                    }
                    if (filteredCards.length > 0) cards = filteredCards;
                }

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var titleEl = card.querySelector('h2, h3, h4, h5, .job-title, [class*="job-title"], [class*="title"], [class*="designation"], [class*="role-name"]');
                    var locEl = card.querySelector('[class*="location"], [class*="Location"], [class*="city"]');
                    var linkEl = card.querySelector('a[href]');

                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title && linkEl) title = linkEl.innerText.trim().split('\\n')[0];
                    if (!title) {
                        var cardText = card.innerText.trim();
                        if (cardText) title = cardText.split('\\n')[0].trim();
                    }
                    var location = locEl ? locEl.innerText.trim() : '';
                    var href = linkEl ? linkEl.href : '';

                    if (title && title.length > 2 && title.length < 200 && !seen[title + href]) {
                        if (!href || (!href.includes('login') && !href.includes('sign-in') && !href.includes('javascript:'))) {
                            seen[title + href] = true;
                            var deptEl = card.querySelector('[class*="department"], [class*="dept"], [class*="team"], [class*="category"]');
                            var dept = deptEl ? deptEl.innerText.trim() : '';
                            results.push({title: title, location: location, url: href || '', date: '', department: dept});
                        }
                    }
                }

                // Strategy 2: Direct job links (TurboHire may use /jobs/, /job/, /openings/, or query params like jobId)
                if (results.length === 0) {
                    var jobLinks = document.querySelectorAll(
                        'a[href*="/jobs/"], a[href*="/job/"], a[href*="/openings/"], a[href*="/opening/"], ' +
                        'a[href*="jobId"], a[href*="openingId"], a[href*="requisitionId"]'
                    );
                    for (var i = 0; i < jobLinks.length; i++) {
                        var el = jobLinks[i];
                        var title = (el.innerText || '').trim().split('\\n')[0].trim();
                        var url = el.href || '';
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (url.includes('login') || url.includes('sign-in') || url.includes('javascript:')) continue;
                        if (seen[url]) continue;
                        seen[url] = true;
                        var location = '';
                        var parent = el.closest('li, div, article, tr, section');
                        if (parent) {
                            var locEl = parent.querySelector('[class*="location"], [class*="Location"], [class*="city"]');
                            if (locEl && locEl !== el) location = locEl.innerText.trim();
                        }
                        results.push({title: title, url: url, location: location, date: '', department: ''});
                    }
                }

                // Strategy 3: Look for any links that look like job postings by text content
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    var jobKeywords = ['manager', 'engineer', 'analyst', 'executive', 'officer', 'lead', 'head', 'specialist', 'associate', 'coordinator', 'developer', 'intern', 'trainee', 'supervisor', 'director', 'senior', 'junior', 'designer', 'consultant', 'advisor', 'relationship'];
                    for (var i = 0; i < allLinks.length; i++) {
                        var el = allLinks[i];
                        var text = (el.innerText || '').trim().split('\\n')[0].trim();
                        var href = el.href || '';
                        if (!text || text.length < 5 || text.length > 200) continue;
                        if (href.includes('login') || href.includes('sign-in') || href.includes('javascript:') || href.includes('#')) continue;
                        if (seen[href]) continue;
                        var textLower = text.toLowerCase();
                        var isJob = false;
                        for (var k = 0; k < jobKeywords.length; k++) {
                            if (textLower.includes(jobKeywords[k])) { isJob = true; break; }
                        }
                        // Also consider any link under a job-section
                        if (!isJob) {
                            var jobParent = el.closest('[class*="job"], [class*="opening"], [class*="career"], [class*="listing"]');
                            if (jobParent) isJob = true;
                        }
                        if (isJob) {
                            seen[href] = true;
                            var location = '';
                            var parent = el.closest('li, div, article, tr, section');
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="city"]');
                                if (locEl && locEl !== el) location = locEl.innerText.trim();
                            }
                            results.push({title: text, url: href, location: location, date: '', department: ''});
                        }
                    }
                }

                // Strategy 4: Look for elements with job title keywords in text content
                // (for cases where the SPA renders jobs as plain divs/spans without links)
                if (results.length === 0) {
                    var allElements = document.querySelectorAll('div, li, article, span, p, h2, h3, h4, h5, h6');
                    var jobKeywords2 = ['manager', 'engineer', 'analyst', 'executive', 'officer', 'lead', 'head', 'specialist', 'associate', 'coordinator', 'developer', 'intern', 'trainee', 'supervisor', 'director', 'senior', 'junior', 'designer', 'consultant', 'advisor'];
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        if (el.children.length > 5) continue;  // Skip containers
                        var elText = (el.innerText || '').trim();
                        if (elText.length < 5 || elText.length > 300) continue;

                        var elTitle = elText.split('\\n')[0].trim();
                        if (elTitle.length < 3 || elTitle.length > 200 || seen[elTitle]) continue;

                        var elLower = elTitle.toLowerCase();
                        var isJobTitle = false;
                        for (var k = 0; k < jobKeywords2.length; k++) {
                            if (elLower.includes(jobKeywords2[k])) { isJobTitle = true; break; }
                        }
                        if (!isJobTitle) continue;

                        // Skip navigation/UI text
                        var skipWords = ['home', 'about', 'contact', 'login', 'sign', 'filter', 'search', 'sort', 'showing', 'privacy', 'terms', 'cookie'];
                        var isSkip = false;
                        for (var s = 0; s < skipWords.length; s++) {
                            if (elLower.includes(skipWords[s])) { isSkip = true; break; }
                        }
                        if (isSkip) continue;

                        seen[elTitle] = true;
                        var elLink = el.querySelector('a[href]') || el.closest('a[href]');
                        var elUrl = elLink ? elLink.href : '';

                        var elLoc = '';
                        var elLines = elText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        for (var j = 1; j < elLines.length; j++) {
                            if (/mumbai|delhi|bangalore|bengaluru|pune|hyderabad|chennai|kolkata|india|noida|gurgaon|gurugram|remote|ahmedabad|jaipur|lucknow|indore|bhopal/i.test(elLines[j])) {
                                elLoc = elLines[j];
                                break;
                            }
                        }

                        var elDept = '';
                        for (var j = 1; j < elLines.length; j++) {
                            if (/department|division|function/i.test(elLines[j])) {
                                elDept = elLines[j].replace(/department|division|function/gi, '').replace(/[:\\-]/g, '').trim();
                                break;
                            }
                        }

                        results.push({title: elTitle, url: elUrl, location: elLoc, date: '', department: elDept});
                    }
                }

                // Strategy 5: TurboHire department sections - extract job counts and individual jobs
                if (results.length === 0) {
                    var sections = document.querySelectorAll('[class*="department"], [class*="category"], [class*="section"]');
                    for (var s = 0; s < sections.length; s++) {
                        var sec = sections[s];
                        var links = sec.querySelectorAll('a[href]');
                        for (var j = 0; j < links.length; j++) {
                            var el = links[j];
                            var text = (el.innerText || '').trim().split('\\n')[0].trim();
                            var href = el.href || '';
                            if (!text || text.length < 3 || text.length > 200) continue;
                            if (href.includes('javascript:') || href.includes('#') || seen[href]) continue;
                            if (text.toLowerCase().includes('view') || text.toLowerCase().includes('see all')) continue;
                            seen[href] = true;
                            results.push({title: text, url: href, location: '', date: '', department: ''});
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    date = jdata.get('date', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    if url and url.startswith('/'):
                        url = f"{self.base_url}{url}"

                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]
                    if url and '/jobs/' in url:
                        parts = url.split('/jobs/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]
                    elif url and '/job/' in url:
                        parts = url.split('/job/')[-1].split('/')
                        if parts[0]:
                            job_id = parts[0]
                    elif url and 'jobId=' in url:
                        job_id = url.split('jobId=')[-1].split('&')[0]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': title,
                        'apply_url': url or self.url, 'location': location,
                        'department': department, 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })

            if jobs:
                logger.info(f"Successfully extracted {len(jobs)} jobs")
            else:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                    page_url = driver.current_url
                    logger.info(f"Current URL: {page_url}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # TurboHire pagination / load-more selectors
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, 'button[class*="load-more"]'),
                (By.CSS_SELECTOR, '[class*="load-more"] button'),
                (By.XPATH, '//button[contains(translate(text(),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"load more")]'),
                (By.XPATH, '//button[contains(translate(text(),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"show more")]'),
                (By.XPATH, '//a[contains(translate(text(),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"load more")]'),
                (By.XPATH, '//a[contains(translate(text(),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"next")]'),
                (By.CSS_SELECTOR, 'a[aria-label="Next"]'),
                (By.CSS_SELECTOR, 'button[aria-label="Next"]'),
                (By.CSS_SELECTOR, '.pagination .next a'),
                (By.CSS_SELECTOR, 'a.next-page'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, 'li.pagination-next a'),
                (By.CSS_SELECTOR, '[class*="pagination"] a[class*="next"]'),
                (By.CSS_SELECTOR, '[class*="pagination"] button[class*="next"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
            ]:
                try:
                    btn = driver.find_element(sel_type, sel_val)
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("Navigated to next page")
                        return True
                except:
                    continue
            return False
        except:
            return False

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str: return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1: result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str: result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = BritanniaScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

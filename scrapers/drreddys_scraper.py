from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('drreddys_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class DrReddysScraper:
    def __init__(self):
        self.company_name = "Dr. Reddy's Laboratories"
        self.url = 'https://www.drreddys.com/careers/'

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

        try:
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _find_careers_portal_url(self, driver):
        """Find the external careers portal URL from the main page"""
        # Try to find a link to careers.drreddys.com
        portal_url = None

        try:
            portal_url = driver.execute_script("""
                var links = document.querySelectorAll('a[href]');
                for (var i = 0; i < links.length; i++) {
                    var href = links[i].href || '';
                    if (href.includes('careers.drreddys.com')) {
                        return href;
                    }
                }
                // Also check for iframe sources
                var iframes = document.querySelectorAll('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    var src = iframes[i].src || '';
                    if (src.includes('careers.drreddys.com')) {
                        return src;
                    }
                }
                return null;
            """)
        except Exception as e:
            logger.error(f"Error finding portal URL via JS: {str(e)}")

        if portal_url:
            logger.info(f"Found careers portal URL: {portal_url}")
            return portal_url

        # Fallback: try known portal URL directly
        logger.info("Using known careers portal URL: https://careers.drreddys.com/jobs")
        return "https://careers.drreddys.com/jobs"

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Dr. Reddy's careers portal"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Step 1: Load the main careers page to find portal link
            driver.get(self.url)
            time.sleep(8)

            # Step 2: Find and navigate to the external careers portal
            portal_url = self._find_careers_portal_url(driver)
            logger.info(f"Navigating to careers portal: {portal_url}")
            driver.get(portal_url)
            time.sleep(12)  # Wait for SPA rendering

            # Scroll to trigger lazy loading
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((i + 1) / 3))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_portal_page(driver)
                if not page_jobs and current_page == 1:
                    # Try the /jobs endpoint directly if portal didn't load properly
                    logger.info("No jobs found on portal, trying /jobs endpoint directly")
                    driver.get("https://careers.drreddys.com/jobs")
                    time.sleep(12)
                    for i in range(3):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((i + 1) / 3))
                        time.sleep(2)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(2)
                    page_jobs = self._scrape_portal_page(driver)

                jobs.extend(page_jobs)
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                if not page_jobs:
                    logger.info("No jobs found on current page, stopping pagination")
                    break

                # Try to navigate to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(3)

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page"""
        try:
            next_page_num = current_page + 1

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            next_page_selectors = [
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'button[aria-label="Go to page {next_page_num}"]'),
                (By.XPATH, '//button[@aria-label="Go to next page"]'),
                (By.XPATH, '//button[contains(@class, "next")]'),
                (By.CSS_SELECTOR, 'button.pagination-next'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a[rel="next"]'),
                (By.CSS_SELECTOR, '[class*="pagination"] [class*="next"]'),
                (By.CSS_SELECTOR, '[class*="pager"] [class*="next"]'),
                (By.XPATH, '//button[contains(@aria-label, "next")]'),
                (By.XPATH, '//a[contains(@aria-label, "next")]'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    if next_button.is_displayed() and next_button.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", next_button)
                        logger.info(f"Clicked next page button")
                        return True
                except:
                    continue

            # Try JS-based pagination detection
            try:
                has_next = driver.execute_script("""
                    // Look for "Load More" or "Show More" buttons
                    var buttons = document.querySelectorAll('button, a');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = (buttons[i].textContent || '').toLowerCase().trim();
                        if (text.includes('load more') || text.includes('show more') || text.includes('view more')) {
                            buttons[i].click();
                            return true;
                        }
                    }
                    return false;
                """)
                if has_next:
                    logger.info("Clicked 'Load More' button via JS")
                    return True
            except:
                pass

            logger.warning("Could not find next page button")
            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_portal_page(self, driver):
        """Scrape jobs from the external careers portal page using JS-first extraction"""
        jobs = []
        time.sleep(2)

        # Strategy 1: JS-based extraction of job cards from careers.drreddys.com
        try:
            js_jobs = driver.execute_script("""
                var jobs = [];

                // Strategy A: Look for job card elements with links to /job/ URLs
                var jobLinks = document.querySelectorAll('a[href*="/job/"]');
                var seen = {};
                for (var i = 0; i < jobLinks.length; i++) {
                    var link = jobLinks[i];
                    var href = link.href || '';
                    if (seen[href]) continue;
                    seen[href] = true;

                    var title = '';
                    // Try to get title from the link text or nearby heading
                    var headings = link.querySelectorAll('h1, h2, h3, h4, h5, h6');
                    if (headings.length > 0) {
                        title = headings[0].textContent.trim();
                    } else {
                        title = link.textContent.trim().split('\\n')[0].trim();
                    }

                    if (!title || title.length < 3 || title.length > 200) continue;

                    // Try to extract location from sibling or parent elements
                    var location = '';
                    var card = link.closest('[class*="card"], [class*="job"], [class*="listing"], [class*="item"], [class*="result"], li, article, div');
                    if (card) {
                        var cardText = card.textContent || '';
                        var lines = cardText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        for (var j = 0; j < lines.length; j++) {
                            if (lines[j].match(/Hyderabad|Bangalore|Mumbai|Chennai|Delhi|Pune|India|Remote|Vizag|Visakhapatnam|Duvvada/i) && lines[j] !== title) {
                                location = lines[j];
                                break;
                            }
                        }
                    }

                    // Extract JID from URL
                    var jidMatch = href.match(/jid-(\d+)/);
                    var jobId = jidMatch ? jidMatch[1] : '';

                    jobs.push({title: title, url: href, location: location, jobId: jobId});
                }

                // Strategy B: If no /job/ links found, look for any job-like card structures
                if (jobs.length === 0) {
                    var cards = document.querySelectorAll('[class*="job-card"], [class*="job-listing"], [class*="job-item"], [class*="jobCard"], [class*="job_card"], [class*="position-card"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var cardLink = card.querySelector('a[href]');
                        var cardTitle = '';
                        var cardUrl = '';

                        var heading = card.querySelector('h1, h2, h3, h4, h5, h6');
                        if (heading) {
                            cardTitle = heading.textContent.trim();
                        } else if (cardLink) {
                            cardTitle = cardLink.textContent.trim().split('\\n')[0].trim();
                        }

                        if (cardLink) {
                            cardUrl = cardLink.href || '';
                        }

                        if (!cardTitle || cardTitle.length < 3) continue;

                        var loc = '';
                        var cardText = card.textContent || '';
                        var cLines = cardText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        for (var j = 0; j < cLines.length; j++) {
                            if (cLines[j].match(/Hyderabad|Bangalore|Mumbai|Chennai|Delhi|Pune|India|Remote/i) && cLines[j] !== cardTitle) {
                                loc = cLines[j];
                                break;
                            }
                        }

                        if (!seen[cardUrl || cardTitle]) {
                            seen[cardUrl || cardTitle] = true;
                            jobs.push({title: cardTitle, url: cardUrl, location: loc, jobId: ''});
                        }
                    }
                }

                // Strategy C: Look for list items or divs that contain job title keywords
                if (jobs.length === 0) {
                    var allElements = document.querySelectorAll('li, article, div[role="listitem"], [data-testid*="job"], [data-testid*="position"]');
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        var elText = el.textContent.trim();
                        if (elText.length < 10 || elText.length > 500) continue;
                        if (elText.match(/engineer|analyst|manager|developer|scientist|specialist|director|lead|associate|executive|officer|consultant|coordinator|technician/i)) {
                            var elLink = el.querySelector('a[href]');
                            var elTitle = '';
                            var elUrl = '';

                            var elHeading = el.querySelector('h1, h2, h3, h4, h5, h6, [class*="title"]');
                            if (elHeading) {
                                elTitle = elHeading.textContent.trim();
                            } else if (elLink) {
                                elTitle = elLink.textContent.trim().split('\\n')[0].trim();
                            } else {
                                elTitle = elText.split('\\n')[0].trim();
                            }

                            if (elLink) elUrl = elLink.href || '';

                            if (!elTitle || elTitle.length < 3 || seen[elUrl || elTitle]) continue;
                            seen[elUrl || elTitle] = true;

                            var elLoc = '';
                            var elLines = elText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                            for (var j = 0; j < elLines.length; j++) {
                                if (elLines[j].match(/Hyderabad|Bangalore|Mumbai|Chennai|Delhi|Pune|India|Remote/i) && elLines[j] !== elTitle) {
                                    elLoc = elLines[j];
                                    break;
                                }
                            }

                            jobs.push({title: elTitle, url: elUrl, location: elLoc, jobId: ''});
                        }
                    }
                }

                return jobs;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs from portal")
                seen_titles = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    job_id_str = jdata.get('jobId', '') or hashlib.md5((url or title).encode()).hexdigest()[:12]

                    if not title or len(title) < 3 or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    city, state, country = self.parse_location(location)

                    job_data = {
                        'external_id': self.generate_external_id(job_id_str, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country or 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': url if url else driver.current_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job_data)
        except Exception as e:
            logger.error(f"JS extraction error: {str(e)}")

        # Strategy 2: Selenium-based fallback with selectors
        if not jobs:
            logger.info("JS extraction found 0 jobs, trying Selenium selectors")
            wait = WebDriverWait(driver, 8)
            job_cards = []
            selectors = [
                (By.CSS_SELECTOR, 'a[href*="/job/"]'),
                (By.CSS_SELECTOR, 'div[class*="job-card"]'),
                (By.CSS_SELECTOR, 'div[class*="job-listing"]'),
                (By.CSS_SELECTOR, 'div[class*="position-card"]'),
                (By.CSS_SELECTOR, '[class*="jobCard"]'),
                (By.CSS_SELECTOR, 'li[class*="job"]'),
                (By.CSS_SELECTOR, 'article'),
                (By.CSS_SELECTOR, '[role="listitem"]'),
            ]

            for selector_type, selector_value in selectors:
                try:
                    wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                    job_cards = driver.find_elements(selector_type, selector_value)
                    if job_cards and len(job_cards) > 0:
                        logger.info(f"Found {len(job_cards)} cards using selector: {selector_value}")
                        break
                except:
                    continue

            for idx, card in enumerate(job_cards):
                try:
                    card_text = card.text.strip()
                    if not card_text or len(card_text) < 5:
                        continue

                    job_title = ""
                    job_link = ""
                    try:
                        if card.tag_name == 'a':
                            job_title = card.text.strip().split('\n')[0].strip()
                            job_link = card.get_attribute('href')
                        else:
                            title_link = card.find_element(By.TAG_NAME, 'a')
                            job_title = title_link.text.strip().split('\n')[0].strip()
                            job_link = title_link.get_attribute('href')
                    except:
                        job_title = card_text.split('\n')[0].strip()

                    if not job_title or len(job_title) < 3:
                        continue

                    job_id = f"drreddys_{idx}"
                    if job_link:
                        jid_match = None
                        if 'jid-' in job_link:
                            jid_match = job_link.split('jid-')[-1].split('/')[0].split('?')[0]
                        if jid_match:
                            job_id = jid_match
                        else:
                            job_id = job_link.split('/')[-1].split('?')[0] or job_id

                    location = ""
                    city = ""
                    state = ""
                    lines = card_text.split('\n')
                    for line in lines:
                        if any(loc in line for loc in ['Hyderabad', 'Bangalore', 'Mumbai', 'Chennai', 'Delhi', 'Pune', 'India', 'Vizag', 'Duvvada']):
                            location = line.strip()
                            city, state, _ = self.parse_location(location)
                            break

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': job_title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': job_link if job_link else driver.current_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job_data)

                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        # Strategy 3: Broad link-based extraction as final fallback
        if not jobs:
            logger.info("Trying broad link-based extraction on portal page")
            try:
                all_links_data = driver.execute_script("""
                    var results = [];
                    var seen = {};
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim().split('\\n')[0].trim();
                        var href = link.href || '';
                        if (text.length > 3 && text.length < 200 && href.length > 10 && !seen[href]) {
                            var lhref = href.toLowerCase();
                            if (lhref.includes('/job') || lhref.includes('/position') || lhref.includes('/career') ||
                                lhref.includes('/opening') || lhref.includes('/apply') || lhref.includes('/requisition')) {
                                seen[href] = true;
                                results.push({title: text, url: href});
                            }
                        }
                    });
                    return results;
                """)
                if all_links_data:
                    exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq', 'alert', 'early career']
                    seen = set()
                    for link_data in all_links_data:
                        title = link_data.get('title', '').strip()
                        url = link_data.get('url', '')
                        if not title or not url or len(title) < 3 or title in seen:
                            continue
                        if any(w in title.lower() for w in exclude):
                            continue
                        seen.add(title)
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '', 'location': '', 'city': '', 'state': '',
                            'country': 'India', 'employment_type': '', 'department': '',
                            'apply_url': url, 'posted_date': '', 'job_function': '',
                            'experience_level': '', 'salary_range': '', 'remote_type': '', 'status': 'active'
                        })
                    if jobs:
                        logger.info(f"Link-based fallback found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"Link-based fallback error: {str(e)}")

        return jobs

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(3)

            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div.job-description'),
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, '//div[contains(@class, "content")]'),
                ]

                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        details['description'] = desc_elem.text.strip()[:2000]
                        break
                    except:
                        continue
            except:
                pass

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass

        return details

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

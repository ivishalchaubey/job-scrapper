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

logger = setup_logger('jswenergy_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class JSWEnergyScraper:
    def __init__(self):
        self.company_name = 'JSW Energy'
        self.url = 'https://www.jsw.in/careers'

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

    def _find_turbohire_portal_url(self, driver):
        """Find the TurboHire portal URL from the main JSW careers page"""
        portal_url = None

        try:
            portal_url = driver.execute_script("""
                var links = document.querySelectorAll('a[href]');
                for (var i = 0; i < links.length; i++) {
                    var href = links[i].href || '';
                    if (href.includes('turbohire.co') || href.includes('turbohire')) {
                        return href;
                    }
                }
                // Check iframes too
                var iframes = document.querySelectorAll('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    var src = iframes[i].src || '';
                    if (src.includes('turbohire.co') || src.includes('turbohire')) {
                        return src;
                    }
                }
                // Also look for links with "Apply" or "View Openings" or "Current Openings" text
                for (var i = 0; i < links.length; i++) {
                    var text = (links[i].textContent || '').toLowerCase().trim();
                    var href = links[i].href || '';
                    if ((text.includes('view opening') || text.includes('current opening') || text.includes('apply now') || text.includes('explore opportunities')) && href.includes('http')) {
                        return href;
                    }
                }
                return null;
            """)
        except Exception as e:
            logger.error(f"Error finding TurboHire portal URL: {str(e)}")

        if portal_url:
            logger.info(f"Found TurboHire portal URL: {portal_url}")
            return portal_url

        # Fallback: use known TurboHire portal URL
        known_url = "https://jswgroup.turbohire.co/careerpage/9b510aa7-a9f2-46a7-aeb7-8853d81bcf10"
        logger.info(f"Using known TurboHire portal URL: {known_url}")
        return known_url

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from JSW Energy via TurboHire portal"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Step 1: Load the main careers page to find TurboHire link
            driver.get(self.url)
            time.sleep(8)

            # Step 2: Find and navigate to TurboHire portal
            portal_url = self._find_turbohire_portal_url(driver)
            logger.info(f"Navigating to TurboHire portal: {portal_url}")
            driver.get(portal_url)
            time.sleep(12)  # Wait for SPA rendering

            # Scroll to trigger lazy loading
            for i in range(4):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((i + 1) / 4))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            current_page = 1

            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page} of {max_pages}")

                page_jobs = self._scrape_turbohire_page(driver)

                # If first page and no jobs, try alternate TurboHire URL
                if not page_jobs and current_page == 1:
                    logger.info("No jobs found, trying alternate TurboHire URLs")
                    alternate_urls = [
                        "https://jswgroup.turbohire.co/careerpage/9b510aa7-a9f2-46a7-aeb7-8853d81bcf10",
                        "https://jswgroup.turbohire.co",
                    ]
                    for alt_url in alternate_urls:
                        if alt_url != portal_url:
                            logger.info(f"Trying alternate URL: {alt_url}")
                            driver.get(alt_url)
                            time.sleep(12)
                            for i in range(3):
                                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((i + 1) / 3))
                                time.sleep(2)
                            driver.execute_script("window.scrollTo(0, 0);")
                            time.sleep(2)
                            page_jobs = self._scrape_turbohire_page(driver)
                            if page_jobs:
                                break

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
        """Navigate to the next page on TurboHire portal"""
        try:
            next_page_num = current_page + 1

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            next_page_selectors = [
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.XPATH, f'//button[text()="{next_page_num}"]'),
                (By.CSS_SELECTOR, f'a[aria-label="Page {next_page_num}"]'),
                (By.XPATH, '//a[@aria-label="Next page"]'),
                (By.XPATH, '//button[contains(text(), "Next")]'),
                (By.CSS_SELECTOR, 'a.pagination-next'),
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
                        logger.info("Clicked next page button")
                        return True
                except:
                    continue

            # Try JS-based "Load More" or "Show More" detection
            try:
                has_next = driver.execute_script("""
                    var buttons = document.querySelectorAll('button, a');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = (buttons[i].textContent || '').toLowerCase().trim();
                        if (text.includes('load more') || text.includes('show more') || text.includes('view more') || text === 'more') {
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

    def _scrape_turbohire_page(self, driver):
        """Scrape jobs from TurboHire career portal using JS-first extraction"""
        jobs = []
        time.sleep(2)

        # Strategy 1: JS-based extraction for TurboHire platform
        try:
            js_jobs = driver.execute_script("""
                var jobs = [];
                var seen = {};

                // TurboHire Strategy A: Look for job cards with common TurboHire selectors
                var cardSelectors = [
                    'div.job-card', 'div[class*="job-card"]', 'div[class*="jobCard"]',
                    'div[class*="job_card"]', 'div[class*="job-listing"]', 'div[class*="jobListing"]',
                    'div.card', 'div[class*="career-card"]', 'div[class*="careerCard"]',
                    'div[class*="position-card"]', 'div[class*="positionCard"]',
                    'div[class*="opening"]', 'li[class*="job"]', 'article',
                    '[class*="job-title"]', '[class*="jobTitle"]',
                    'a[href*="/jobs/"]', 'a[href*="/job/"]', 'a[href*="jobId"]'
                ];

                var cards = [];
                for (var s = 0; s < cardSelectors.length; s++) {
                    cards = document.querySelectorAll(cardSelectors[s]);
                    if (cards.length > 0) break;
                }

                if (cards.length > 0) {
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var cardText = card.textContent.trim();
                        if (!cardText || cardText.length < 5) continue;

                        var title = '';
                        var url = '';

                        // Get title from heading or title-classed element
                        var heading = card.querySelector('h1, h2, h3, h4, h5, h6, [class*="title"], [class*="Title"]');
                        if (heading) {
                            title = heading.textContent.trim();
                        }

                        // Get URL from link
                        var link = card.tagName === 'A' ? card : card.querySelector('a[href]');
                        if (link) {
                            url = link.href || '';
                            if (!title) {
                                title = link.textContent.trim().split('\\n')[0].trim();
                            }
                        }

                        if (!title) {
                            title = cardText.split('\\n')[0].trim();
                        }

                        if (!title || title.length < 3 || title.length > 200 || seen[url || title]) continue;
                        seen[url || title] = true;

                        // Extract location
                        var location = '';
                        var lines = cardText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        for (var j = 0; j < lines.length; j++) {
                            if (lines[j].match(/Mumbai|Delhi|Bangalore|Bengaluru|Chennai|Kolkata|Pune|Hyderabad|Gurgaon|Gurugram|India|Raigad|Vijayanagar|Toranagallu|Bellary|JSW/i) && lines[j] !== title) {
                                location = lines[j];
                                break;
                            }
                        }

                        // Extract department
                        var department = '';
                        for (var j = 0; j < lines.length; j++) {
                            if (lines[j].match(/department|division|function/i) && lines[j] !== title) {
                                department = lines[j].replace(/department|division|function/gi, '').replace(/[:\\-]/g, '').trim();
                                break;
                            }
                        }

                        // Extract job ID from URL
                        var jobId = '';
                        if (url) {
                            var idMatch = url.match(/(?:jobId=|\/jobs\/|\/job\/)([^&?/]+)/);
                            if (idMatch) jobId = idMatch[1];
                        }

                        jobs.push({title: title, url: url, location: location, department: department, jobId: jobId});
                    }
                }

                // TurboHire Strategy B: If no cards found, look for all links with job-related hrefs
                if (jobs.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var href = link.href || '';
                        var text = link.textContent.trim().split('\\n')[0].trim();

                        if (!text || text.length < 3 || text.length > 200 || seen[href]) continue;

                        var lhref = href.toLowerCase();
                        if (lhref.includes('/job') || lhref.includes('jobid') || lhref.includes('/position') ||
                            lhref.includes('/opening') || lhref.includes('/career') && lhref.includes('turbohire')) {
                            seen[href] = true;

                            var parentCard = link.closest('div, li, article');
                            var loc = '';
                            if (parentCard) {
                                var pText = parentCard.textContent || '';
                                var pLines = pText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                                for (var j = 0; j < pLines.length; j++) {
                                    if (pLines[j].match(/Mumbai|Delhi|Bangalore|Bengaluru|Chennai|Kolkata|Pune|Hyderabad|Gurgaon|Gurugram|India|Raigad|JSW/i) && pLines[j] !== text) {
                                        loc = pLines[j];
                                        break;
                                    }
                                }
                            }

                            jobs.push({title: text, url: href, location: loc, department: '', jobId: ''});
                        }
                    }
                }

                // TurboHire Strategy C: Look for elements containing job title keywords
                if (jobs.length === 0) {
                    var allElements = document.querySelectorAll('div, li, article, span, p');
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        var elText = el.textContent.trim();
                        if (elText.length < 10 || elText.length > 500) continue;
                        if (el.children.length > 5) continue;  // Skip containers with many children

                        if (elText.match(/engineer|analyst|manager|developer|consultant|associate|specialist|director|lead|intern|executive|officer|trainee|coordinator|supervisor/i)) {
                            var elTitle = elText.split('\\n')[0].trim();
                            var elLink = el.querySelector('a[href]') || el.closest('a[href]');
                            var elUrl = elLink ? elLink.href : '';

                            if (!elTitle || elTitle.length < 3 || seen[elUrl || elTitle]) continue;
                            seen[elUrl || elTitle] = true;

                            var elLoc = '';
                            var elLines = elText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                            for (var j = 0; j < elLines.length; j++) {
                                if (elLines[j].match(/Mumbai|Delhi|Bangalore|Bengaluru|Chennai|Kolkata|Pune|Hyderabad|India|Raigad|JSW/i) && elLines[j] !== elTitle) {
                                    elLoc = elLines[j];
                                    break;
                                }
                            }

                            jobs.push({title: elTitle, url: elUrl, location: elLoc, department: '', jobId: ''});
                        }
                    }
                }

                return jobs;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} jobs from TurboHire portal")
                seen_titles = set()
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    job_id_str = jdata.get('jobId', '') or hashlib.md5((url or title).encode()).hexdigest()[:12]

                    if not title or len(title) < 3 or title in seen_titles:
                        continue
                    # Skip navigation/UI text
                    skip_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq', 'menu', 'search', 'filter']
                    if any(w == title.lower() for w in skip_words):
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
                        'department': department,
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

        # Strategy 2: Selenium-based fallback
        if not jobs:
            logger.info("JS extraction found 0 jobs, trying Selenium selectors")
            wait = WebDriverWait(driver, 8)
            job_cards = []
            selectors = [
                (By.CSS_SELECTOR, 'div.job-card'),
                (By.CSS_SELECTOR, 'div[class*="job-card"]'),
                (By.CSS_SELECTOR, 'div[class*="jobCard"]'),
                (By.CSS_SELECTOR, 'a[href*="/jobs/"]'),
                (By.CSS_SELECTOR, 'a[href*="jobId"]'),
                (By.CSS_SELECTOR, 'div[class*="card"]'),
                (By.CSS_SELECTOR, 'div[class*="opening"]'),
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
                            title_elem = None
                            for tag in ['h3', 'h4', 'h2', 'h5', 'a']:
                                try:
                                    title_elem = card.find_element(By.TAG_NAME, tag)
                                    break
                                except:
                                    continue
                            if title_elem:
                                job_title = title_elem.text.strip()
                                if tag == 'a':
                                    job_link = title_elem.get_attribute('href')
                            else:
                                job_title = card_text.split('\n')[0].strip()

                            if not job_link:
                                try:
                                    link_elem = card.find_element(By.TAG_NAME, 'a')
                                    job_link = link_elem.get_attribute('href')
                                except:
                                    pass
                    except:
                        job_title = card_text.split('\n')[0].strip()

                    if not job_title or len(job_title) < 3:
                        continue

                    job_id = f"jsw_{idx}"
                    if job_link:
                        if 'jobId=' in job_link:
                            job_id = job_link.split('jobId=')[-1].split('&')[0]
                        elif '/jobs/' in job_link:
                            job_id = job_link.split('/jobs/')[-1].split('?')[0].split('/')[0]
                        elif '/job/' in job_link:
                            job_id = job_link.split('/job/')[-1].split('?')[0].split('/')[0]

                    location = ""
                    city = ""
                    state = ""
                    lines = card_text.split('\n')
                    for line in lines:
                        if any(loc in line for loc in ['India', 'Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Pune', 'Hyderabad', 'Raigad', 'JSW', 'Bellary', 'Toranagallu']):
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

        # Strategy 3: Broad link fallback
        if not jobs:
            logger.info("Trying broad link-based extraction on TurboHire portal")
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
                                lhref.includes('/opening') || lhref.includes('/apply') || lhref.includes('jobid') ||
                                lhref.includes('/vacancy') || lhref.includes('/requisition')) {
                                seen[href] = true;
                                results.push({title: text, url: href});
                            }
                        }
                    });
                    return results;
                """)
                if all_links_data:
                    exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq']
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
                    (By.XPATH, '//div[contains(@class, "description")]'),
                ]

                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        if desc_elem and desc_elem.text.strip():
                            details['description'] = desc_elem.text.strip()[:2000]
                            break
                    except:
                        continue
            except:
                pass

            try:
                dept_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'Department')]//following-sibling::*")
                details['department'] = dept_elem.text.strip()
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

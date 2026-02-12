from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('zepto_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class ZeptoScraper:
    def __init__(self):
        self.company_name = 'Zepto'
        self.url = 'https://www.zeptonow.com/careers'

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
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Zepto careers page - TalentRecruit platform with iframe"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)

            # Wait for page to load and potential redirect to talentrecruit
            time.sleep(15)

            logger.info(f"Current URL after load: {driver.current_url}")

            wait = WebDriverWait(driver, 10)

            # Strategy 1: Try to find and switch to iframe (TalentRecruit embeds jobs in iframe)
            iframe_jobs = self._scrape_via_iframe(driver, wait)
            if iframe_jobs:
                jobs.extend(iframe_jobs)
                logger.info(f"Found {len(iframe_jobs)} jobs via iframe")

            # Strategy 2: If no iframe jobs, try direct page scraping (in case page structure changed)
            if not jobs:
                logger.info("No iframe jobs found, trying direct page scraping")
                # Scroll to load content
                for i in range(5):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)

                page_jobs = self._scrape_page_direct(driver, wait)
                jobs.extend(page_jobs)

            # Strategy 3: If still nothing, try navigating directly to the TalentRecruit URL
            if not jobs:
                logger.info("Trying direct TalentRecruit URL navigation")
                try:
                    driver.get('https://zepto.talentrecruit.com/career-page')
                    time.sleep(10)
                    logger.info(f"TalentRecruit URL: {driver.current_url}")

                    # Check for iframe again on this page
                    iframe_jobs = self._scrape_via_iframe(driver, wait)
                    if iframe_jobs:
                        jobs.extend(iframe_jobs)
                    else:
                        # Try direct scraping on TalentRecruit page
                        direct_jobs = self._scrape_talentrecruit_direct(driver, wait)
                        jobs.extend(direct_jobs)
                except Exception as e:
                    logger.error(f"TalentRecruit direct navigation failed: {str(e)}")

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _scrape_via_iframe(self, driver, wait):
        """Try to find iframe and scrape jobs inside it"""
        jobs = []

        try:
            # Find all iframes on the page
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            logger.info(f"Found {len(iframes)} iframes on page")

            target_iframe = None

            for idx, iframe in enumerate(iframes):
                try:
                    src = iframe.get_attribute('src') or ''
                    logger.info(f"iframe {idx}: src={src[:100]}")
                    if 'talentrecruit' in src.lower() or 'career' in src.lower() or 'appcareer' in src.lower():
                        target_iframe = iframe
                        logger.info(f"Found TalentRecruit iframe: {src}")
                        break
                except:
                    continue

            # If no specific iframe found, try the first one if it exists
            if not target_iframe and iframes:
                target_iframe = iframes[0]
                logger.info("Using first iframe as fallback")

            if not target_iframe:
                logger.info("No iframe found on page")
                return jobs

            # Switch to the iframe
            driver.switch_to.frame(target_iframe)
            logger.info("Switched to iframe context")

            # Wait for iframe content to load
            time.sleep(5)

            # Try TalentRecruit-specific selectors inside the iframe
            jobs = self._scrape_iframe_content(driver, wait)

            # Switch back to main content
            driver.switch_to.default_content()
            logger.info("Switched back to default content")

        except Exception as e:
            logger.error(f"iframe scraping error: {str(e)}")
            try:
                driver.switch_to.default_content()
            except:
                pass

        return jobs

    def _scrape_iframe_content(self, driver, wait):
        """Scrape job content from inside an iframe (TalentRecruit platform)"""
        jobs = []

        # TalentRecruit platform selectors - try multiple patterns
        selector_strategies = [
            # Common TalentRecruit selectors
            ('div.job-listing', 'div.job-listing'),
            ('div[class*="job-card"]', 'div[class*="job-card"]'),
            ('div[class*="job-list"]', 'div[class*="job-list"]'),
            ('div[class*="opening"]', 'div[class*="opening"]'),
            ('div[class*="position"]', 'div[class*="position"]'),
            ('tr[class*="job"]', 'tr[class*="job"]'),
            ('li[class*="job"]', 'li[class*="job"]'),
            ('a[class*="job"]', 'a[class*="job"]'),
            ('div.card', 'div.card'),
            ('[class*="vacancy"]', '[class*="vacancy"]'),
            ('[class*="career"]', '[class*="career"]'),
        ]

        job_elements = []
        used_selector = ""

        for name, selector in selector_strategies:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and len(elements) > 0:
                    # Filter to elements that have meaningful text
                    valid = [e for e in elements if e.text.strip() and len(e.text.strip()) > 5]
                    if valid:
                        job_elements = valid
                        used_selector = name
                        logger.info(f"Found {len(valid)} elements inside iframe using: {name}")
                        break
            except:
                continue

        if job_elements:
            for idx, elem in enumerate(job_elements):
                try:
                    text = elem.text.strip()
                    if not text or len(text) < 5:
                        continue

                    title = ""
                    job_link = ""

                    # Try to find title
                    for tag in ['h2', 'h3', 'h4', 'a', 'strong', 'b', 'span[class*="title"]']:
                        try:
                            title_elem = elem.find_element(By.CSS_SELECTOR, tag)
                            t = title_elem.text.strip()
                            if t and len(t) >= 3 and len(t) <= 200:
                                title = t
                                if tag == 'a' or title_elem.tag_name == 'a':
                                    job_link = title_elem.get_attribute('href') or ''
                                break
                        except:
                            continue

                    if not title:
                        title = text.split('\n')[0].strip()

                    if not title or len(title) < 3:
                        continue

                    # Try to get link if not found yet
                    if not job_link:
                        try:
                            link = elem.find_element(By.TAG_NAME, 'a')
                            job_link = link.get_attribute('href') or ''
                        except:
                            pass

                    location = self._extract_location_from_text(text, title)
                    city, state, _ = self.parse_location(location)

                    job_id = f"zepto_{idx}"
                    if job_link:
                        job_id = hashlib.md5(job_link.encode()).hexdigest()[:12]

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': job_link if job_link else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                    logger.info(f"iframe extracted: {title}")

                except Exception as e:
                    logger.error(f"Error extracting iframe job {idx}: {str(e)}")
                    continue

        # JavaScript fallback inside iframe
        if not jobs:
            logger.info("Trying JS extraction inside iframe")
            try:
                js_jobs = driver.execute_script("""
                    var results = [];
                    // Get all links
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = (links[i].innerText || '').trim();
                        var href = links[i].href || '';
                        if (text.length > 3 && text.length < 200) {
                            // Filter out navigation links
                            var lower = text.toLowerCase();
                            if (lower === 'home' || lower === 'about' || lower === 'contact' ||
                                lower === 'login' || lower === 'sign in' || lower === 'register') continue;
                            results.push({title: text.split('\\n')[0].trim(), url: href});
                        }
                    }
                    // If no links found, try extracting text from divs/spans that look like job titles
                    if (results.length === 0) {
                        var allElements = document.querySelectorAll('h2, h3, h4, div[class*="title"], span[class*="title"], td:first-child');
                        for (var i = 0; i < allElements.length; i++) {
                            var text = (allElements[i].innerText || '').trim();
                            if (text.length >= 5 && text.length <= 200) {
                                var lower = text.toLowerCase();
                                if (lower === 'home' || lower === 'about' || lower === 'contact') continue;
                                var parent = allElements[i].closest('a') || allElements[i].querySelector('a');
                                var link = parent ? (parent.href || '') : '';
                                results.push({title: text, url: link});
                            }
                        }
                    }
                    return results;
                """)
                if js_jobs:
                    seen = set()
                    for idx, jdata in enumerate(js_jobs):
                        title = jdata.get('title', '').strip()
                        url = jdata.get('url', '').strip()
                        if not title or title in seen or len(title) < 3:
                            continue
                        skip_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'menu']
                        if any(w in title.lower() for w in skip_words):
                            continue
                        seen.add(title)
                        job_id = f"zepto_iframe_{idx}"
                        if url:
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]
                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': '',
                            'city': '',
                            'state': '',
                            'country': 'India',
                            'employment_type': '',
                            'department': '',
                            'apply_url': url if url else self.url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })
                    logger.info(f"JS iframe extraction found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"JS iframe extraction error: {str(e)}")

        return jobs

    def _scrape_talentrecruit_direct(self, driver, wait):
        """Scrape TalentRecruit page directly (not inside iframe)"""
        jobs = []

        # Scroll to load content
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        # Check for iframes again (TalentRecruit career-page may also have iframes)
        iframes = driver.find_elements(By.TAG_NAME, 'iframe')
        if iframes:
            logger.info(f"Found {len(iframes)} iframes on TalentRecruit page")
            for iframe in iframes:
                try:
                    driver.switch_to.frame(iframe)
                    time.sleep(3)
                    iframe_jobs = self._scrape_iframe_content(driver, wait)
                    driver.switch_to.default_content()
                    if iframe_jobs:
                        jobs.extend(iframe_jobs)
                        break
                except:
                    try:
                        driver.switch_to.default_content()
                    except:
                        pass
                    continue

        if jobs:
            return jobs

        # Try direct selectors on the TalentRecruit page
        selectors = [
            'div[class*="job"]',
            'div[class*="opening"]',
            'div[class*="position"]',
            'div[class*="career"]',
            'li[class*="job"]',
            'tr[class*="job"]',
            'a[class*="job"]',
            'div.card',
        ]

        job_elements = []
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                valid = [e for e in elements if e.text.strip() and len(e.text.strip()) > 5]
                if valid:
                    job_elements = valid
                    logger.info(f"TalentRecruit direct: found {len(valid)} elements using {selector}")
                    break
            except:
                continue

        for idx, elem in enumerate(job_elements):
            try:
                text = elem.text.strip()
                if not text or len(text) < 5:
                    continue
                title = text.split('\n')[0].strip()
                if not title or len(title) < 3:
                    continue

                job_link = ""
                try:
                    link = elem.find_element(By.TAG_NAME, 'a')
                    job_link = link.get_attribute('href') or ''
                except:
                    pass

                location = self._extract_location_from_text(text, title)
                city, state, _ = self.parse_location(location)

                job_id = f"zepto_tr_{idx}"
                if job_link:
                    job_id = hashlib.md5(job_link.encode()).hexdigest()[:12]

                jobs.append({
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': 'India',
                    'employment_type': '',
                    'department': '',
                    'apply_url': job_link if job_link else self.url,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                })
                logger.info(f"TalentRecruit direct extracted: {title}")
            except Exception as e:
                logger.error(f"Error extracting TR job {idx}: {str(e)}")

        # JS fallback on TalentRecruit page
        if not jobs:
            logger.info("Trying JS fallback on TalentRecruit page")
            try:
                js_jobs = driver.execute_script("""
                    var results = [];
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            var lower = text.toLowerCase();
                            if (lower === 'home' || lower === 'about' || lower === 'contact' ||
                                lower === 'login' || lower === 'sign in') return;
                            results.push({title: text.split('\\n')[0].trim(), url: href});
                        }
                    });
                    return results;
                """)
                if js_jobs:
                    seen = set()
                    for idx, jdata in enumerate(js_jobs):
                        title = jdata.get('title', '').strip()
                        url = jdata.get('url', '').strip()
                        if not title or title in seen or len(title) < 3:
                            continue
                        skip = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms']
                        if any(w in title.lower() for w in skip):
                            continue
                        seen.add(title)
                        job_id = hashlib.md5(f"{title}_{url}".encode()).hexdigest()[:12]
                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '', 'location': '', 'city': '', 'state': '',
                            'country': 'India', 'employment_type': '', 'department': '',
                            'apply_url': url if url else self.url, 'posted_date': '', 'job_function': '',
                            'experience_level': '', 'salary_range': '', 'remote_type': '', 'status': 'active'
                        })
                    logger.info(f"JS TR fallback found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"JS TR fallback error: {str(e)}")

        return jobs

    def _scrape_page_direct(self, driver, wait):
        """Scrape jobs directly from the main page (non-iframe approach)"""
        jobs = []

        # Try multiple selectors for job listings on the main page
        job_cards = []
        selectors = [
            (By.CSS_SELECTOR, 'div[class*="job-card"]'),
            (By.CSS_SELECTOR, 'div[class*="job-list"]'),
            (By.CSS_SELECTOR, 'div[class*="opening"]'),
            (By.CSS_SELECTOR, 'div[class*="position"]'),
            (By.CSS_SELECTOR, 'div[class*="career"]'),
            (By.CSS_SELECTOR, 'div[class*="role"]'),
            (By.CSS_SELECTOR, 'li[class*="job"]'),
            (By.CSS_SELECTOR, 'a[href*="talentrecruit"]'),
            (By.TAG_NAME, 'article'),
        ]

        for selector_type, selector_value in selectors:
            try:
                elements = driver.find_elements(selector_type, selector_value)
                valid = [e for e in elements if e.text.strip() and len(e.text.strip()) > 5]
                if valid:
                    job_cards = valid
                    logger.info(f"Direct page: found {len(valid)} elements using {selector_value}")
                    break
            except:
                continue

        if job_cards:
            for idx, card in enumerate(job_cards):
                try:
                    card_text = card.text.strip()
                    if not card_text or len(card_text) < 5:
                        continue

                    job_title = ""
                    job_link = ""
                    try:
                        title_link = card.find_element(By.TAG_NAME, 'a')
                        job_title = title_link.text.strip()
                        job_link = title_link.get_attribute('href')
                    except:
                        job_title = card_text.split('\n')[0].strip()

                    if not job_title or len(job_title) < 3:
                        continue

                    location = self._extract_location_from_text(card_text, job_title)
                    city, state, _ = self.parse_location(location)

                    job_id = f"zepto_{idx}"
                    if job_link:
                        job_id = hashlib.md5(job_link.encode()).hexdigest()[:12]

                    jobs.append({
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
                        'apply_url': job_link if job_link else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

                except Exception as e:
                    logger.error(f"Error extracting direct job {idx}: {str(e)}")
                    continue

        # Link-based fallback
        if not jobs:
            logger.info("Trying link-based fallback on main page")
            seen_titles = set()
            try:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                for idx, link in enumerate(all_links):
                    try:
                        href = link.get_attribute('href') or ''
                        text = link.text.strip()
                        if not text or len(text) < 5 or len(text) > 200:
                            continue
                        job_url_patterns = ['/job/', '/jobs/', '/position/', '/career', '/opening', 'talentrecruit', 'lever.co', 'greenhouse.io']
                        if any(p in href.lower() for p in job_url_patterns):
                            if text in seen_titles:
                                continue
                            seen_titles.add(text)
                            exclude_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms']
                            if any(w in text.lower() for w in exclude_words):
                                continue

                            job_id = hashlib.md5(href.encode()).hexdigest()[:12]
                            jobs.append({
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name,
                                'title': text,
                                'description': '',
                                'location': '',
                                'city': '',
                                'state': '',
                                'country': 'India',
                                'employment_type': '',
                                'department': '',
                                'apply_url': href if href.startswith('http') else self.url,
                                'posted_date': '',
                                'job_function': '',
                                'experience_level': '',
                                'salary_range': '',
                                'remote_type': '',
                                'status': 'active'
                            })
                    except:
                        continue
                if jobs:
                    logger.info(f"Link-based fallback found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"Link fallback error: {str(e)}")

        # JS-based extraction fallback
        if not jobs:
            logger.info("Trying JS extraction on main page")
            try:
                js_links = driver.execute_script("""
                    var results = [];
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length > 3 && text.length < 200 && href.length > 10) {
                            var lhref = href.toLowerCase();
                            if (lhref.includes('/job') || lhref.includes('/position') || lhref.includes('/career') ||
                                lhref.includes('/opening') || lhref.includes('talentrecruit') ||
                                lhref.includes('/role') || lhref.includes('/requisition') || lhref.includes('/apply')) {
                                results.push({title: text.split('\\n')[0].trim(), url: href});
                            }
                        }
                    });
                    return results;
                """)
                if js_links:
                    seen = set()
                    exclude = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'cookie', 'blog', 'faq']
                    for link_data in js_links:
                        title = link_data.get('title', '')
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
                        logger.info(f"JS main page fallback found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"JS fallback error: {str(e)}")

        return jobs

    def _extract_location_from_text(self, text, title):
        """Extract location from text, excluding the title"""
        location = ""
        cities = ['Mumbai', 'Bangalore', 'Bengaluru', 'Delhi', 'Gurgaon', 'Gurugram',
                  'Noida', 'Pune', 'Chennai', 'Hyderabad', 'Kolkata', 'India', 'Remote']
        for line in text.split('\n'):
            line_s = line.strip()
            if line_s == title:
                continue
            if any(c in line_s for c in cities):
                location = line_s
                break
        return location

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
                desc_elem = driver.find_element(By.CSS_SELECTOR, 'div[class*="description"]')
                details['description'] = desc_elem.text.strip()[:2000]
            except:
                pass

            try:
                dept_elem = driver.find_element(By.CSS_SELECTOR, 'span[class*="department"]')
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

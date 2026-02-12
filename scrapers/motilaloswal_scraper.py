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

logger = setup_logger('motilaloswal_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class MotilalOswalScraper:
    def __init__(self):
        self.company_name = 'Motilal Oswal'
        self.url = 'https://motilaloswal.turbohire.co/dashboardv2?orgId=0f6e3a76-85ff-4b66-8bfa-4cd4fede4ffa&type=0'

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

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
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

            # Wait 15s for TurboHire SPA to render
            time.sleep(15)

            logger.info(f"Current URL after load: {driver.current_url}")

            # Scroll multiple times to load lazy content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try pagination - scrape multiple pages
            page = 1
            while page <= max_pages:
                logger.info(f"Scraping page {page}")
                jobs = self._scrape_page(driver)
                if jobs:
                    all_jobs.extend(jobs)
                    logger.info(f"Page {page}: found {len(jobs)} jobs, total so far: {len(all_jobs)}")
                else:
                    logger.info(f"Page {page}: no jobs found, stopping pagination")
                    break

                # Try to click next page / load more
                if not self._go_to_next_page(driver):
                    break
                page += 1
                time.sleep(3)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _go_to_next_page(self, driver):
        """Try to navigate to the next page or load more results"""
        try:
            # Try common pagination / load more selectors
            next_selectors = [
                "a[aria-label='Next']",
                "button[aria-label='Next']",
                "a.next",
                "button.next",
                "li.next a",
                "[class*='next']",
                "[class*='load-more']",
                "[class*='loadMore']",
                "button[class*='more']",
                "[class*='pagination'] a:last-child",
                "a[rel='next']",
            ]

            for selector in next_selectors:
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if next_btn.is_displayed() and next_btn.is_enabled():
                        next_btn.click()
                        time.sleep(3)
                        return True
                except:
                    continue

            # Try JavaScript-based pagination
            clicked = driver.execute_script("""
                var buttons = document.querySelectorAll('a, button, span, div');
                for (var i = 0; i < buttons.length; i++) {
                    var text = (buttons[i].innerText || '').trim().toLowerCase();
                    var ariaLabel = (buttons[i].getAttribute('aria-label') || '').toLowerCase();
                    if (text === 'next' || text === 'load more' || text === 'show more' ||
                        text === '>' || text === '>>' || ariaLabel === 'next' || ariaLabel === 'next page') {
                        buttons[i].click();
                        return true;
                    }
                }
                return false;
            """)
            if clicked:
                time.sleep(3)
                return True

            return False
        except Exception as e:
            logger.error(f"Pagination error: {str(e)}")
            return False

    def _scrape_page(self, driver):
        jobs = []
        scraped_ids = set()

        try:
            # --- Strategy 1: JS extraction for TurboHire ---
            logger.info("Trying JS-based TurboHire extraction")
            js_jobs = driver.execute_script("""
                var results = [];

                // Strategy A: Find job cards/containers - TurboHire uses div-based card layouts
                var jobCards = document.querySelectorAll(
                    'div[class*="job"], div[class*="card"], div[class*="listing"], ' +
                    'div[class*="position"], div[class*="opening"], div[class*="vacancy"], ' +
                    'div[class*="Job"], div[class*="Card"], div[class*="requisition"]'
                );

                if (jobCards.length > 0) {
                    for (var i = 0; i < jobCards.length; i++) {
                        var card = jobCards[i];
                        var text = (card.innerText || '').trim();
                        if (text.length < 5) continue;

                        var lines = text.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        if (lines.length === 0) continue;

                        var title = '';
                        var location = '';
                        var department = '';

                        // Check for links or headings
                        var titleEl = card.querySelector('a[href*="/job"], a[href*="/jobs"], a[href*="/requisition"], h2, h3, h4, h5');
                        if (titleEl) {
                            title = (titleEl.innerText || '').trim().split('\\n')[0];
                        }
                        if (!title) {
                            title = lines[0];
                        }

                        // Skip navigation items
                        var skipWords = ['home', 'about', 'contact', 'login', 'sign in', 'register', 'filter', 'search', 'sort', 'all jobs', 'showing'];
                        var lowerTitle = title.toLowerCase();
                        var isSkip = false;
                        for (var s = 0; s < skipWords.length; s++) {
                            if (lowerTitle === skipWords[s] || lowerTitle.indexOf(skipWords[s]) === 0) {
                                isSkip = true;
                                break;
                            }
                        }
                        if (isSkip) continue;
                        if (title.length < 3 || title.length > 200) continue;

                        // Extract location and department from remaining lines
                        for (var j = 1; j < lines.length && j < 6; j++) {
                            var line = lines[j];
                            if (line.length < 2 || line.length > 100) continue;
                            if (/mumbai|delhi|bangalore|bengaluru|pune|hyderabad|chennai|kolkata|india|noida|gurgaon|gurugram|remote|ahmedabad|jaipur|lucknow|indore|bhopal/i.test(line)) {
                                if (!location) location = line;
                            } else if (!department && line.length > 2 && line.length < 80) {
                                department = line;
                            }
                        }

                        var url = '';
                        if (titleEl && titleEl.href) {
                            url = titleEl.href;
                        } else {
                            var anyLink = card.querySelector('a[href]');
                            if (anyLink) url = anyLink.href || '';
                        }

                        results.push({title: title, url: url, location: location, department: department});
                    }
                }

                // Strategy B: Find all links that look like job postings
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    var seenTexts = new Set();
                    for (var k = 0; k < allLinks.length; k++) {
                        var link = allLinks[k];
                        var linkText = (link.innerText || '').trim().split('\\n')[0];
                        var href = link.href || '';
                        if (linkText.length < 5 || linkText.length > 200) continue;
                        if (seenTexts.has(linkText)) continue;

                        var skipNav = ['home', 'about', 'contact', 'login', 'sign', 'register', 'privacy', 'terms', 'cookie'];
                        var isNav = false;
                        for (var n = 0; n < skipNav.length; n++) {
                            if (linkText.toLowerCase().indexOf(skipNav[n]) !== -1) { isNav = true; break; }
                        }
                        if (isNav) continue;

                        var isJobLink = /job|position|career|opening|requisition|vacancy|apply|dashboardv2/i.test(href);
                        var hasJobTitle = /manager|officer|executive|engineer|analyst|lead|head|director|specialist|coordinator|associate|senior|junior|intern|trainee|designer|developer|consultant|supervisor|assistant|advisor|relationship/i.test(linkText);

                        if (isJobLink || hasJobTitle) {
                            seenTexts.add(linkText);
                            results.push({title: linkText, url: href, location: '', department: ''});
                        }
                    }
                }

                // Strategy C: Find headings that look like job titles
                if (results.length === 0) {
                    var headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6, span[class*="title"], div[class*="title"]');
                    var seenH = new Set();
                    for (var h = 0; h < headings.length; h++) {
                        var hText = (headings[h].innerText || '').trim();
                        if (hText.length < 5 || hText.length > 200 || seenH.has(hText)) continue;
                        var hasJob = /manager|officer|executive|engineer|analyst|lead|head|director|specialist|coordinator|associate|senior|junior|intern|trainee|designer|developer|consultant|supervisor|assistant|advisor|relationship/i.test(hText);
                        if (hasJob) {
                            seenH.add(hText);
                            var hParent = headings[h].closest('div, li, article, section');
                            var hLink = headings[h].querySelector('a') || (hParent ? hParent.querySelector('a[href]') : null);
                            var hUrl = hLink ? (hLink.href || '') : '';
                            results.push({title: hText, url: hUrl, location: '', department: ''});
                        }
                    }
                }

                // Strategy D: Extract from any visible text blocks
                if (results.length === 0) {
                    var allDivs = document.querySelectorAll('div, li, article');
                    var seenD = new Set();
                    for (var d = 0; d < allDivs.length; d++) {
                        var divEl = allDivs[d];
                        // Only look at leaf-ish elements (fewer children)
                        if (divEl.children.length > 10) continue;
                        var dText = (divEl.innerText || '').trim();
                        if (dText.length < 10 || dText.length > 300) continue;
                        var dLines = dText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        if (dLines.length < 1 || dLines.length > 8) continue;
                        var dTitle = dLines[0];
                        if (seenD.has(dTitle)) continue;
                        var hasJobD = /manager|officer|executive|engineer|analyst|lead|head|director|specialist|coordinator|associate|senior|junior|intern|trainee|designer|developer|consultant|supervisor|assistant|advisor|relationship/i.test(dTitle);
                        if (hasJobD && dTitle.length >= 5) {
                            seenD.add(dTitle);
                            var dLink = divEl.querySelector('a[href]');
                            var dUrl = dLink ? (dLink.href || '') : '';
                            var dLoc = '';
                            for (var dl = 1; dl < dLines.length; dl++) {
                                if (/mumbai|delhi|bangalore|bengaluru|pune|hyderabad|chennai|kolkata|india|noida|gurgaon|gurugram|remote/i.test(dLines[dl])) {
                                    dLoc = dLines[dl];
                                    break;
                                }
                            }
                            results.push({title: dTitle, url: dUrl, location: dLoc, department: ''});
                        }
                    }
                }

                // Deduplicate by title
                var unique = [];
                var seenTitles = new Set();
                for (var u = 0; u < results.length; u++) {
                    if (!seenTitles.has(results[u].title)) {
                        seenTitles.add(results[u].title);
                        unique.push(results[u]);
                    }
                }
                return unique;
            """)

            if js_jobs and len(js_jobs) > 0:
                logger.info(f"JS TurboHire extraction found {len(js_jobs)} jobs")
                for jdx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if not url:
                        url = self.url

                    job_id = f"motilaloswal_{jdx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url,
                        'location': location,
                        'department': department,
                        'employment_type': '',
                        'description': '',
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

                    location_parts = self.parse_location(location)
                    job_data.update(location_parts)

                    if job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job {len(jobs)}: {title}")

                if jobs:
                    return jobs

            # --- Strategy 2: Selenium CSS selector-based extraction ---
            logger.info("JS extraction returned 0, trying Selenium selectors")
            job_elements = []
            selectors = [
                "div[class*='job']",
                "div[class*='card']",
                "div[class*='Card']",
                "a[href*='/job']",
                "div[class*='listing']",
                "div[class*='position']",
                "div[class*='requisition']",
                "table tr",
                "li[class*='job']",
                "article",
            ]

            short_wait = WebDriverWait(driver, 5)
            for selector in selectors:
                try:
                    short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    valid = [e for e in elements if e.text.strip() and len(e.text.strip()) > 5]
                    if valid:
                        job_elements = valid
                        logger.info(f"Found {len(valid)} listings using selector: {selector}")
                        break
                except:
                    continue

            # Fallback: find links that look like job postings
            if not job_elements:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                job_links = []
                for link in all_links:
                    href = link.get_attribute('href') or ''
                    text = link.text.strip()
                    if ('/job' in href or 'turbohire' in href or '/requisition' in href) and text and len(text) > 5:
                        skip_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms']
                        if not any(w in text.lower() for w in skip_words):
                            job_links.append(link)
                if job_links:
                    job_elements = job_links
                    logger.info(f"Fallback found {len(job_links)} job links")

            if not job_elements:
                logger.warning("Could not find job listings on TurboHire page")
                return jobs

            for idx, job_elem in enumerate(job_elements, 1):
                try:
                    title = ""
                    job_url = ""

                    tag_name = job_elem.tag_name
                    if tag_name == 'a':
                        title = job_elem.text.strip().split('\n')[0]
                        job_url = job_elem.get_attribute('href')
                    else:
                        for sel in ['h2 a', 'h3 a', 'h4 a', 'a[href*="/job"]', 'a', 'h2', 'h3', 'h4']:
                            try:
                                el = job_elem.find_element(By.CSS_SELECTOR, sel)
                                title = el.text.strip()
                                job_url = el.get_attribute('href') or ''
                                if title:
                                    break
                            except:
                                continue

                    if not title:
                        text = job_elem.text.strip()
                        if text:
                            title = text.split('\n')[0].strip()

                    if not title or len(title) < 3:
                        continue

                    skip_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'filter', 'search']
                    if any(w in title.lower() for w in skip_words):
                        continue

                    if not job_url:
                        job_url = self.url

                    job_id = f"motilaloswal_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

                    location = ""
                    try:
                        all_text = job_elem.text
                        lines = all_text.split('\n')
                        for line in lines:
                            line_s = line.strip()
                            if any(city in line_s for city in ['Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Pune', 'Hyderabad', 'India', 'Noida', 'Gurugram']):
                                location = line_s
                                break
                    except:
                        pass

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': job_url,
                        'location': location,
                        'department': '',
                        'employment_type': '',
                        'description': '',
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

                    location_parts = self.parse_location(location)
                    job_data.update(location_parts)

                    if job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job {len(jobs)}: {title}")
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        return jobs

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


if __name__ == "__main__":
    scraper = MotilalOswalScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

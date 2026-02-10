from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import re
from datetime import datetime
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('statebankofindia_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class StateBankOfIndiaScraper:
    def __init__(self):
        self.company_name = 'State Bank of India'
        # sbi.co.in/web/careers/current-openings redirects to sbi.bank.in/web/careers/current-openings
        self.url = 'https://sbi.co.in/web/careers/current-openings'

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
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--ignore-ssl-errors')
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])

        try:
            driver_path = CHROMEDRIVER_PATH
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape recruitment openings from SBI careers page"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            driver.get(self.url)

            # Wait for page to load
            time.sleep(15)

            # Scroll to trigger lazy-loaded content
            for scroll_i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((scroll_i + 1) / 5))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # SBI does not have typical job cards - it has recruitment notices/advertisements
            # Each notice has a title, advertisement number, and last date to apply
            page_jobs = self._scrape_page_js(driver)
            jobs.extend(page_jobs)

            logger.info(f"Successfully scraped {len(jobs)} total recruitment notices from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _scrape_page_js(self, driver):
        """Scrape SBI recruitment notices using JavaScript extraction"""
        jobs = []
        time.sleep(3)

        try:
            # SBI page structure: recruitment notices with titles in uppercase,
            # ADVERTISEMENT NO: CRPD/xxx, LAST DATE TO APPLY, and "APPLY ONLINE" links
            js_jobs = driver.execute_script("""
                var jobs = [];
                var seen = {};
                var bodyText = document.body.innerText || '';
                var lines = bodyText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                // Method 1: Parse recruitment blocks from text content
                // Each recruitment block starts with a title in CAPS and has an ADVERTISEMENT NO
                var currentTitle = '';
                var currentAdvNo = '';
                var currentLastDate = '';
                var currentApplyUrl = '';

                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];

                    // Detect recruitment title - typically all uppercase, starts with RECRUITMENT/ENGAGEMENT
                    if ((line.startsWith('RECRUITMENT') || line.startsWith('ENGAGEMENT') ||
                         line.startsWith('SELECTION') || line.startsWith('EMPANELMENT')) &&
                        line.length > 20 && line.length < 500) {

                        // Save previous block if exists
                        if (currentTitle && currentAdvNo && !seen[currentAdvNo]) {
                            seen[currentAdvNo] = true;
                            jobs.push({
                                title: currentTitle,
                                advNo: currentAdvNo,
                                lastDate: currentLastDate,
                                applyUrl: currentApplyUrl
                            });
                        }

                        currentTitle = line;
                        currentAdvNo = '';
                        currentLastDate = '';
                        currentApplyUrl = '';
                    }

                    // Extract advertisement number
                    if (line.includes('ADVERTISEMENT NO') || line.includes('ADVT. NO')) {
                        var advMatch = line.match(/CRPD\\/[\\w-]+\\/\\d+/);
                        if (advMatch) {
                            currentAdvNo = advMatch[0];
                        } else {
                            // Try next line
                            if (i + 1 < lines.length) {
                                advMatch = lines[i+1].match(/CRPD\\/[\\w-]+\\/\\d+/);
                                if (advMatch) currentAdvNo = advMatch[0];
                            }
                        }
                    }

                    // Extract last date
                    if (line.includes('LAST DATE TO APPLY')) {
                        var dateMatch = line.match(/\\d{2}-\\d{2}-\\d{4}/);
                        if (dateMatch) {
                            currentLastDate = dateMatch[0];
                        }
                    }
                }

                // Save the last block
                if (currentTitle && currentAdvNo && !seen[currentAdvNo]) {
                    seen[currentAdvNo] = true;
                    jobs.push({
                        title: currentTitle,
                        advNo: currentAdvNo,
                        lastDate: currentLastDate,
                        applyUrl: currentApplyUrl
                    });
                }

                // Method 2: Also find "APPLY ONLINE" links and match them
                var applyLinks = document.querySelectorAll('a[href*="recruitment.sbi"], a[href*="apply"]');
                var linkMap = {};
                applyLinks.forEach(function(link) {
                    var text = (link.textContent || '').trim();
                    var href = link.href || '';
                    if (text.includes('APPLY') && href.length > 10) {
                        // Try to find the associated advertisement
                        var parent = link.parentElement;
                        for (var p = 0; p < 5; p++) {
                            if (parent && parent.parentElement) {
                                parent = parent.parentElement;
                            }
                        }
                        var pText = (parent ? parent.innerText : '') || '';
                        var advMatch = pText.match(/CRPD\\/[\\w-]+\\/\\d+/);
                        if (advMatch) {
                            linkMap[advMatch[0]] = href;
                        }
                    }
                });

                // Attach apply URLs
                for (var k = 0; k < jobs.length; k++) {
                    if (linkMap[jobs[k].advNo]) {
                        jobs[k].applyUrl = linkMap[jobs[k].advNo];
                    }
                }

                // Method 3: Also find PDF links for detailed notifications
                var pdfLinks = document.querySelectorAll('a[href*=".pdf"]');
                var pdfMap = {};
                pdfLinks.forEach(function(link) {
                    var href = link.href || '';
                    var parent = link.parentElement;
                    for (var p = 0; p < 5; p++) {
                        if (parent && parent.parentElement) parent = parent.parentElement;
                    }
                    var pText = (parent ? parent.innerText : '') || '';
                    var advMatch = pText.match(/CRPD\\/[\\w-]+\\/\\d+/);
                    if (advMatch && href.includes('.pdf')) {
                        if (!pdfMap[advMatch[0]]) pdfMap[advMatch[0]] = href;
                    }
                });

                return jobs;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} recruitment notices")
                for job_data in js_jobs:
                    title = job_data.get('title', '')
                    if not title or len(title) < 10:
                        continue

                    adv_no = job_data.get('advNo', '')
                    last_date = job_data.get('lastDate', '')
                    apply_url = job_data.get('applyUrl', '')

                    # Clean up title - make it more readable
                    clean_title = title
                    # Remove "(APPLY ONLINE FROM ...)" part from title if present
                    paren_match = re.search(r'\(APPLY ONLINE.*?\)', clean_title)
                    if paren_match:
                        clean_title = clean_title[:paren_match.start()].strip()
                    # Also remove other parenthetical notes
                    paren_match2 = re.search(r'\(ONLINE REGISTRATION.*?\)', clean_title)
                    if paren_match2:
                        clean_title = clean_title[:paren_match2.start()].strip()
                    paren_match3 = re.search(r'\(LIST OF.*?\)', clean_title)
                    if paren_match3:
                        clean_title = clean_title[:paren_match3.start()].strip()
                    paren_match4 = re.search(r'\(INTERVIEW.*?\)', clean_title)
                    if paren_match4:
                        clean_title = clean_title[:paren_match4.start()].strip()
                    paren_match5 = re.search(r'\(FINAL RESULT.*?\)', clean_title)
                    if paren_match5:
                        clean_title = clean_title[:paren_match5.start()].strip()
                    paren_match6 = re.search(r'\(REVISED.*?\)', clean_title)
                    if paren_match6:
                        clean_title = clean_title[:paren_match6.start()].strip()

                    job_id = adv_no or hashlib.md5(title.encode()).hexdigest()[:12]

                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': clean_title,
                        'description': f"Advertisement No: {adv_no}. Last Date to Apply: {last_date}",
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': 'Full-time',
                        'department': 'CRPD',
                        'apply_url': apply_url if apply_url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job)
            else:
                logger.warning("JS extraction found no recruitment notices")

        except Exception as e:
            logger.error(f"Error in JS extraction: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

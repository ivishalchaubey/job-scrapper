from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('amnsindia_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class AMNSIndiaScraper:
    def __init__(self):
        self.company_name = "Nippon Steel"
        self.url = "https://www.amns.in/careers/join_us"
        self.alt_url = 'https://www.amns.in/careers/join_us'
        self.base_url = 'https://ace.amns.in'

    def setup_driver(self):
        """Set up Chrome driver with anti-detection options"""
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
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) >= 1 else ''
        state = parts[1] if len(parts) >= 2 else ''
        return city, state, 'India'

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from AMNS India — try ACE portal first, fallback to main careers page"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Strategy 1: ACE Angular Material portal
            jobs = self._scrape_ace_portal(driver)

            if jobs:
                logger.info(f"ACE portal scraping found {len(jobs)} jobs")
            else:
                # Strategy 2: Main careers page (Laravel/Livewire)
                logger.info("ACE portal returned no jobs, trying main careers page")
                jobs = self._scrape_main_careers(driver)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _scrape_ace_portal(self, driver):
        """Scrape from ACE Angular Material SPA"""
        jobs = []

        try:
            logger.info(f"Navigating to ACE portal: {self.url}")
            driver.get(self.url)

            # Angular SPA needs longer wait
            time.sleep(15)

            # Scroll to trigger lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Angular Material card elements
                var matCards = document.querySelectorAll('mat-card, .mat-card, .mat-mdc-card, mat-list-item, .mat-list-item');
                for (var i = 0; i < matCards.length; i++) {
                    var card = matCards[i];
                    var text = card.innerText.trim();
                    if (text.length < 5 || text.length > 2000) continue;

                    var titleEl = card.querySelector('mat-card-title, .mat-card-title, h2, h3, h4, [class*="title"], [class*="name"], strong');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title) title = text.split('\\n')[0].trim();

                    var locEl = card.querySelector('[class*="location"], [class*="city"], [class*="place"], mat-card-subtitle, .mat-card-subtitle');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var deptEl = card.querySelector('[class*="department"], [class*="dept"], [class*="function"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';

                    var expEl = card.querySelector('[class*="experience"], [class*="exp"]');
                    var experience = expEl ? expEl.innerText.trim() : '';

                    var linkEl = card.querySelector('a[href]');
                    var url = linkEl ? linkEl.href : '';

                    if (title && title.length > 2 && title.length < 200 && !seen[title + location]) {
                        seen[title + location] = true;
                        results.push({
                            title: title, location: location, department: department,
                            experience: experience, url: url
                        });
                    }
                }

                // Strategy 2: Generic job card elements
                if (results.length === 0) {
                    var cards = document.querySelectorAll('[class*="job"], [class*="career"], [class*="opening"], [class*="position"], [class*="vacancy"], [class*="card"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var text = card.innerText.trim();
                        if (text.length < 10 || text.length > 2000) continue;

                        var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="name"], strong, a');
                        var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : text.split('\\n')[0].trim();
                        var linkEl = card.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';

                        var lines = text.split('\\n');
                        var location = '';
                        var department = '';
                        var experience = '';
                        for (var j = 0; j < lines.length; j++) {
                            var line = lines[j].trim();
                            if (line.match(/location|city|place/i) || line.match(/Hazira|Mumbai|Delhi|Bangalore|Gujarat|Maharashtra/i)) {
                                location = line.replace(/location\s*[:]/i, '').trim();
                            }
                            if (line.match(/department|dept|function/i)) {
                                department = line.replace(/department\s*[:]/i, '').trim();
                            }
                            if (line.match(/experience|exp|years/i)) {
                                experience = line.replace(/experience\s*[:]/i, '').trim();
                            }
                        }

                        if (title && title.length > 2 && title.length < 200 && !seen[title]) {
                            seen[title] = true;
                            results.push({
                                title: title, location: location, department: department,
                                experience: experience, url: url
                            });
                        }
                    }
                }

                // Strategy 3: Table rows
                if (results.length === 0) {
                    var tables = document.querySelectorAll('table');
                    for (var t = 0; t < tables.length; t++) {
                        var rows = tables[t].querySelectorAll('tbody tr, tr');
                        for (var i = 0; i < rows.length; i++) {
                            var cells = rows[i].querySelectorAll('td');
                            if (cells.length < 1) continue;
                            var title = cells[0] ? cells[0].innerText.trim() : '';
                            var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                            var department = cells.length > 2 ? cells[2].innerText.trim() : '';
                            var link = rows[i].querySelector('a[href]');
                            var url = link ? link.href : '';

                            if (title && title.length > 2 && !seen[title + location]) {
                                seen[title + location] = true;
                                results.push({
                                    title: title, location: location, department: department,
                                    experience: '', url: url
                                });
                            }
                        }
                    }
                }

                // Strategy 4: Links with job-related patterns
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href || '';
                        if (text.length > 3 && text.length < 200 && !seen[text]) {
                            if (href.includes('job') || href.includes('career') || href.includes('opening') || href.includes('position') || href.includes('apply') || href.includes('CAND')) {
                                if (!href.includes('login') && !href.includes('javascript:')) {
                                    seen[text] = true;
                                    results.push({title: text, location: '', department: '', experience: '', url: href});
                                }
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"ACE portal extraction found {len(js_jobs)} jobs")
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    experience = job_data.get('experience', '')
                    url = job_data.get('url', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5(f"{title}_{location}_{idx}".encode()).hexdigest()[:12]
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
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found on ACE portal")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"ACE page body preview: {body_text}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"ACE portal scraping error: {str(e)}")

        return jobs

    def _scrape_main_careers(self, driver):
        """Scrape from main AMNS careers page (Laravel/Livewire)"""
        jobs = []

        try:
            logger.info(f"Navigating to main careers page: {self.alt_url}")
            driver.get(self.alt_url)
            time.sleep(15)

            # Scroll to load content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Look for Livewire-rendered job elements
                var cards = document.querySelectorAll('[class*="job"], [class*="career"], [class*="opening"], [class*="position"], [class*="card"], [class*="listing"], [class*="vacancy"]');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = card.innerText.trim();
                    if (text.length < 10 || text.length > 2000) continue;

                    var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="name"], strong, a');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : text.split('\\n')[0].trim();
                    var linkEl = card.querySelector('a[href]');
                    var url = linkEl ? linkEl.href : '';

                    var lines = text.split('\\n');
                    var location = '';
                    var department = '';
                    var experience = '';
                    for (var j = 0; j < lines.length; j++) {
                        var line = lines[j].trim();
                        if (line.match(/Hazira|Mumbai|Delhi|Bangalore|Gujarat|Maharashtra|Surat|Pune|Kolkata/i)) {
                            location = line;
                        }
                        if (line.match(/department|dept/i)) {
                            department = line.replace(/department\s*[:]/i, '').trim();
                        }
                        if (line.match(/experience|exp|years/i)) {
                            experience = line;
                        }
                    }

                    if (title && title.length > 2 && title.length < 200 && !seen[title]) {
                        seen[title] = true;
                        results.push({
                            title: title, location: location, department: department,
                            experience: experience, url: url
                        });
                    }
                }

                // Table rows fallback
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var cells = rows[i].querySelectorAll('td');
                        if (cells.length < 1) continue;
                        var title = cells[0].innerText.trim();
                        var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                        var link = rows[i].querySelector('a[href]');
                        var url = link ? link.href : '';

                        if (title && title.length > 2 && !seen[title]) {
                            seen[title] = true;
                            results.push({title: title, location: location, department: '', experience: '', url: url});
                        }
                    }
                }

                // Link-based fallback
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href || '';
                        if (text.length > 5 && text.length < 200 && !seen[text]) {
                            if (href.includes('job') || href.includes('career') || href.includes('opening') || href.includes('position') || href.includes('apply')) {
                                if (!href.includes('login') && !href.includes('javascript:') && !href.includes('#')) {
                                    seen[text] = true;
                                    results.push({title: text, location: '', department: '', experience: '', url: href});
                                }
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Main careers page extraction found {len(js_jobs)} jobs")
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    experience = job_data.get('experience', '')
                    url = job_data.get('url', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5(f"{title}_{location}_{idx}".encode()).hexdigest()[:12]
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
                        'apply_url': url if url else self.alt_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found on main careers page either")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Main page body preview: {body_text}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Main careers page scraping error: {str(e)}")

        return jobs


if __name__ == '__main__':
    scraper = AMNSIndiaScraper()
    results = scraper.scrape()
    print(f"\nTotal jobs found: {len(results)}")
    for job in results[:10]:
        print(f"  - {job['title']} | {job['location']} | {job['department']} | {job['apply_url']}")

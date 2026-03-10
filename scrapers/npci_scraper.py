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

logger = setup_logger('npci_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class NPCIScraper:
    def __init__(self):
        self.company_name = "National Payments Corporation of India"
        self.url = "https://www.npci.org.in/careers"
        self.fallback_url = 'https://www.npci.org.in/careers'

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
        except Exception:
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
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'

    def _map_department(self, text):
        """Map job text to NPCI department categories."""
        text_lower = text.lower()
        dept_map = {
            'blockchain': 'Blockchain',
            'analytics': 'Analytics',
            'data': 'Analytics',
            'it': 'IT',
            'technology': 'IT',
            'software': 'IT',
            'developer': 'IT',
            'engineer': 'IT',
            'risk': 'Risk Management',
            'compliance': 'Risk Management',
            'infosec': 'Information Security',
            'security': 'Information Security',
            'cyber': 'Information Security',
            'product': 'Product',
            'finance': 'Finance',
            'accounting': 'Finance',
            'hr': 'Human Resources',
            'human resource': 'Human Resources',
            'people': 'Human Resources',
            'operations': 'Operations',
            'business': 'Business',
            'marketing': 'Marketing',
            'legal': 'Legal',
        }
        for keyword, dept in dept_map.items():
            if keyword in text_lower:
                return dept
        return ''

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from NPCI career portal."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Try primary URL first
            driver.get(self.url)
            time.sleep(10)

            # Wait for dynamic content to load
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href], div[class*="job"], div[class*="career"], div[class*="opening"], table, li'))
                )
            except Exception:
                logger.warning("Timeout on primary URL, trying fallback")
                driver.get(self.fallback_url)
                time.sleep(10)

            # Scroll to trigger lazy loading
            for i in range(6):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Click any expand/load more buttons
            for _ in range(max_pages):
                try:
                    load_more = driver.find_elements(By.XPATH,
                        '//button[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View More") or contains(text(),"View All")]'
                        ' | //a[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View All") or contains(text(),"See All")]')
                    if load_more:
                        driver.execute_script("arguments[0].click();", load_more[0])
                        logger.info("Clicked load more button")
                        time.sleep(3)
                    else:
                        break
                except Exception:
                    break

            # Extract jobs
            jobs = self._extract_jobs_js(driver)

            # If no jobs from primary, try fallback
            if not jobs and self.url in driver.current_url:
                logger.info("No jobs found on primary URL, trying fallback")
                driver.get(self.fallback_url)
                time.sleep(10)
                for i in range(5):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                jobs = self._extract_jobs_js(driver)

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs_js(self, driver):
        """Extract jobs from NPCI career portal using JavaScript."""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Job cards / listings with common selectors
                var selectors = [
                    'div[class*="job-card"]', 'div[class*="jobCard"]', 'div[class*="job_card"]',
                    'div[class*="career-card"]', 'div[class*="opening"]', 'div[class*="vacancy"]',
                    'div[class*="position"]', 'tr[class*="job"]', 'li[class*="job"]',
                    'div[class*="job-listing"]', 'div[class*="job-item"]',
                    '.card', 'article'
                ];

                for (var s = 0; s < selectors.length; s++) {
                    var cards = document.querySelectorAll(selectors[s]);
                    if (cards.length > 0) {
                        for (var i = 0; i < cards.length; i++) {
                            var card = cards[i];
                            var title = '';
                            var href = '';
                            var location = '';
                            var department = '';
                            var experience = '';

                            var heading = card.querySelector('h1, h2, h3, h4, h5, a[href*="job"], a[href*="career"], a[href*="opening"]');
                            if (heading) {
                                title = heading.innerText.trim().split('\\n')[0].trim();
                                if (heading.tagName === 'A') href = heading.href;
                                else {
                                    var hLink = heading.querySelector('a');
                                    if (hLink) href = hLink.href;
                                }
                            }
                            if (!title) {
                                var firstLink = card.querySelector('a');
                                if (firstLink) {
                                    title = firstLink.innerText.trim().split('\\n')[0].trim();
                                    href = firstLink.href;
                                }
                            }
                            if (!href) {
                                var anyLink = card.querySelector('a[href]');
                                if (anyLink) href = anyLink.href;
                            }

                            var locEl = card.querySelector('[class*="location"], [class*="Location"], [class*="city"]');
                            if (locEl) location = locEl.innerText.trim();

                            var deptEl = card.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="domain"]');
                            if (deptEl) department = deptEl.innerText.trim();

                            var expEl = card.querySelector('[class*="experience"], [class*="Experience"], [class*="exp"]');
                            if (expEl) experience = expEl.innerText.trim();

                            if (title && title.length > 2 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({title: title, href: href, location: location, department: department, experience: experience});
                            }
                        }
                        if (results.length > 0) break;
                    }
                }

                // Strategy 2: Table-based listings (common for government/semi-gov portals)
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tr, div[role="row"]');
                    for (var i = 1; i < rows.length; i++) {
                        var row = rows[i];
                        var cells = row.querySelectorAll('td, div[role="cell"]');
                        if (cells.length >= 2) {
                            var titleCell = cells[0];
                            var link = titleCell.querySelector('a');
                            var title = titleCell.innerText.trim().split('\\n')[0].trim();
                            var href = link ? link.href : '';
                            var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                            var dept = cells.length > 2 ? cells[2].innerText.trim() : '';
                            if (title.length > 3 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({title: title, href: href, location: location, department: dept, experience: ''});
                            }
                        }
                    }
                }

                // Strategy 3: Links with job/career/opening keywords
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="job"], a[href*="career"], a[href*="opening"], a[href*="apply"], a[href*="position"], a[href*="vacancy"]');
                    for (var i = 0; i < links.length; i++) {
                        var link = links[i];
                        var text = link.innerText.trim().split('\\n')[0].trim();
                        var href = link.href;
                        if (text.length > 3 && text.length < 200 && !seen[text + href]) {
                            if (href.includes('login') || href.includes('sign-in') || href.includes('javascript:')) continue;
                            seen[text + href] = true;
                            var parent = link.closest('div, li, tr, article');
                            var loc = '';
                            var dept = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl) loc = locEl.innerText.trim();
                                var deptEl = parent.querySelector('[class*="department"], [class*="Department"]');
                                if (deptEl) dept = deptEl.innerText.trim();
                            }
                            results.push({title: text, href: href, location: loc, department: dept, experience: ''});
                        }
                    }
                }

                // Strategy 4: Accordion/expandable sections (common in NPCI-style portals)
                if (results.length === 0) {
                    var sections = document.querySelectorAll('[class*="accordion"], [class*="Accordion"], [class*="collapse"], [class*="panel"], details');
                    for (var i = 0; i < sections.length; i++) {
                        var section = sections[i];
                        var titleEl = section.querySelector('[class*="header"], [class*="title"], summary, h3, h4');
                        if (titleEl) {
                            var title = titleEl.innerText.trim().split('\\n')[0].trim();
                            var link = section.querySelector('a[href]');
                            var href = link ? link.href : '';
                            if (title.length > 3 && !seen[title]) {
                                seen[title] = true;
                                results.push({title: title, href: href, location: '', department: '', experience: ''});
                            }
                        }
                    }
                }

                return results;
            """)

            if job_data:
                logger.info(f"JS extraction found {len(job_data)} jobs")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '').strip()
                    href = jd.get('href', '').strip()
                    location = jd.get('location', '').strip()
                    department = jd.get('department', '').strip()
                    experience = jd.get('experience', '').strip()

                    if not title or len(title) < 3:
                        continue

                    # Skip non-job entries (nav links, etc.)
                    skip_keywords = ['home', 'about', 'contact', 'login', 'sign up', 'register', 'privacy', 'terms']
                    if any(kw in title.lower() for kw in skip_keywords) and len(title) < 20:
                        continue

                    job_id = hashlib.md5((href or f"{title}_{idx}").encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    # Infer department from title if not found
                    if not department:
                        department = self._map_department(title)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location if location else 'India',
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': department,
                        'apply_url': href if href else self.url,
                        'posted_date': '',
                        'job_function': department,
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
        except Exception as e:
            logger.error(f"JS extraction failed: {e}")

        return jobs


if __name__ == "__main__":
    scraper = NPCIScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

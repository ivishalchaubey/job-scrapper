import requests
import hashlib
import re
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import os

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('shriramfinance_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class ShriramFinanceScraper:
    def __init__(self):
        self.company_name = 'Shriram Finance'
        self.url = 'https://www.shriramfinance.in/careers'
        self.base_url = 'https://www.shriramfinance.in'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

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
        """Scrape jobs from Shriram Finance — try requests first (Angular SSR), fallback to Selenium"""
        jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name}")

            # Strategy 1: requests + BS4 (Angular SSR may have server-rendered content)
            jobs = self._scrape_with_requests()

            if jobs:
                logger.info(f"Requests-based scraping found {len(jobs)} jobs")
                return jobs

            # Strategy 2: Fallback to Selenium for full Angular render
            logger.info("Requests-based scraping returned no jobs, falling back to Selenium")
            jobs = self._scrape_with_selenium()

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
        return jobs

    def _scrape_with_requests(self):
        """Scrape using requests + BS4 for SSR content"""
        jobs = []

        try:
            session = requests.Session()
            session.headers.update(self.headers)

            response = session.get(self.url, timeout=30)
            response.raise_for_status()
            logger.info(f"Career page HTTP {response.status_code}, length: {len(response.text)}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for Angular SSR transfer state (embedded JSON)
            script_tags = soup.find_all('script', {'id': re.compile(r'serverApp-state|transfer-state', re.I)})
            if not script_tags:
                script_tags = soup.find_all('script', {'type': 'application/json'})

            for script in script_tags:
                try:
                    import json
                    data = json.loads(script.string)
                    logger.info(f"Found embedded JSON data, keys: {list(data.keys())[:5]}")
                    # Try to extract job data from transfer state
                    jobs = self._extract_from_transfer_state(data)
                    if jobs:
                        return jobs
                except (json.JSONDecodeError, TypeError):
                    continue

            # Look for job listing sections in SSR HTML
            job_sections = soup.find_all(['div', 'section', 'article', 'mat-card'], class_=re.compile(
                r'job|career|opening|position|vacancy|listing|role|opportunity', re.I
            ))

            for idx, section in enumerate(job_sections):
                text = section.get_text(strip=True)
                if len(text) < 10:
                    continue

                title_el = section.find(['h2', 'h3', 'h4', 'h5', 'strong', 'a', 'b'])
                title = title_el.get_text(strip=True) if title_el else ''

                if not title or len(title) < 3:
                    continue

                # Extract location
                location = ''
                loc_el = section.find(class_=re.compile(r'location|city|place', re.I))
                if loc_el:
                    location = loc_el.get_text(strip=True)

                # Extract qualifications
                qualifications = ''
                qual_el = section.find(class_=re.compile(r'qualification|education|degree', re.I))
                if qual_el:
                    qualifications = qual_el.get_text(strip=True)

                # Extract department
                department = ''
                dept_el = section.find(class_=re.compile(r'department|dept|team', re.I))
                if dept_el:
                    department = dept_el.get_text(strip=True)

                link = section.find('a', href=True)
                apply_url = ''
                if link:
                    href = link.get('href', '')
                    if href.startswith('http'):
                        apply_url = href
                    elif href.startswith('/'):
                        apply_url = self.base_url + href

                job_id = hashlib.md5(f"{title}_{location}_{idx}".encode()).hexdigest()[:12]
                city, state, country = self.parse_location(location)

                jobs.append({
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': qualifications,
                    'location': location,
                    'city': city,
                    'state': state,
                    'country': country,
                    'employment_type': '',
                    'department': department,
                    'apply_url': apply_url if apply_url else self.url,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                })

            # Look for "Apply for Job" buttons that may indicate job entries
            if not jobs:
                apply_buttons = soup.find_all('a', string=re.compile(r'Apply', re.I))
                for idx, btn in enumerate(apply_buttons):
                    parent = btn.find_parent(['div', 'section', 'article', 'li', 'tr'])
                    if not parent:
                        continue

                    text = parent.get_text(strip=True)
                    title_el = parent.find(['h2', 'h3', 'h4', 'h5', 'strong', 'b'])
                    title = title_el.get_text(strip=True) if title_el else text.split('\n')[0].strip()

                    if not title or len(title) < 3 or 'Apply' in title:
                        continue

                    href = btn.get('href', '')
                    apply_url = ''
                    if href.startswith('http'):
                        apply_url = href
                    elif href.startswith('/'):
                        apply_url = self.base_url + href

                    job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]

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
                        'apply_url': apply_url if apply_url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

        except Exception as e:
            logger.error(f"Requests-based scraping error: {str(e)}")

        return jobs

    def _extract_from_transfer_state(self, data):
        """Extract jobs from Angular transfer state JSON"""
        jobs = []

        try:
            # Angular transfer state stores API responses as cached data
            for key, value in data.items():
                if isinstance(value, dict) and 'body' in value:
                    body = value['body']
                    if isinstance(body, list):
                        for idx, item in enumerate(body):
                            if isinstance(item, dict):
                                title = item.get('title', item.get('Title', item.get('jobTitle', '')))
                                if not title or len(title) < 3:
                                    continue

                                location = item.get('location', item.get('Location', ''))
                                department = item.get('department', item.get('Department', ''))
                                qualifications = item.get('qualifications', item.get('Qualifications', ''))

                                job_id = hashlib.md5(f"{title}_{location}_{idx}".encode()).hexdigest()[:12]
                                city, state, country = self.parse_location(location)

                                jobs.append({
                                    'external_id': self.generate_external_id(job_id, self.company_name),
                                    'company_name': self.company_name,
                                    'title': title,
                                    'description': qualifications[:2000] if qualifications else '',
                                    'location': location,
                                    'city': city,
                                    'state': state,
                                    'country': country,
                                    'employment_type': '',
                                    'department': department,
                                    'apply_url': self.url,
                                    'posted_date': '',
                                    'job_function': '',
                                    'experience_level': '',
                                    'salary_range': '',
                                    'remote_type': '',
                                    'status': 'active'
                                })

        except Exception as e:
            logger.error(f"Transfer state extraction error: {str(e)}")

        return jobs

    def _scrape_with_selenium(self):
        """Fallback: Scrape using Selenium for full Angular render"""
        jobs = []
        driver = None

        try:
            driver = self.setup_driver()
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(15)

            # Scroll to load all content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Angular job card/listing elements
                var cards = document.querySelectorAll('[class*="job"], [class*="career"], [class*="opening"], [class*="position"], [class*="vacancy"], [class*="listing"], [class*="opportunity"], [class*="role"]');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = card.innerText.trim();
                    if (text.length < 10 || text.length > 3000) continue;

                    var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="name"], strong, b, a');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title || title.length < 3) continue;
                    if (title.match(/^(Apply|Submit|Click|View|See)/i)) continue;

                    var locEl = card.querySelector('[class*="location"], [class*="city"], [class*="place"]');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var qualEl = card.querySelector('[class*="qualification"], [class*="education"], [class*="degree"]');
                    var qualifications = qualEl ? qualEl.innerText.trim() : '';

                    var deptEl = card.querySelector('[class*="department"], [class*="dept"], [class*="team"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';

                    var linkEl = card.querySelector('a[href*="apply"], a[href*="job"], a[href*="career"], a[href]');
                    var url = linkEl ? linkEl.href : '';

                    if (title.length > 2 && title.length < 200 && !seen[title + location]) {
                        seen[title + location] = true;
                        results.push({
                            title: title, location: location, department: department,
                            qualifications: qualifications, url: url
                        });
                    }
                }

                // Strategy 2: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var cells = rows[i].querySelectorAll('td');
                        if (cells.length < 1) continue;
                        var title = cells[0].innerText.trim();
                        if (!title || title.length < 3) continue;
                        var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                        var qualifications = cells.length > 2 ? cells[2].innerText.trim() : '';
                        var link = rows[i].querySelector('a[href]');
                        var url = link ? link.href : '';

                        if (!seen[title + location]) {
                            seen[title + location] = true;
                            results.push({
                                title: title, location: location, department: '',
                                qualifications: qualifications, url: url
                            });
                        }
                    }
                }

                // Strategy 3: Sections with "Apply for Job" buttons
                if (results.length === 0) {
                    var applyBtns = document.querySelectorAll('a[href*="apply"], button[class*="apply"], a:not([href*="login"])');
                    for (var i = 0; i < applyBtns.length; i++) {
                        var btn = applyBtns[i];
                        if (!btn.innerText.match(/apply/i)) continue;
                        var parent = btn.closest('div[class], section, article, li, tr');
                        if (!parent) continue;
                        var text = parent.innerText.trim();
                        var titleEl = parent.querySelector('h2, h3, h4, h5, strong, b');
                        var title = titleEl ? titleEl.innerText.trim() : text.split('\\n')[0].trim();
                        if (!title || title.length < 3 || title.match(/^apply/i)) continue;
                        var url = btn.href || '';

                        if (!seen[title]) {
                            seen[title] = true;
                            results.push({title: title, location: '', department: '', qualifications: '', url: url});
                        }
                    }
                }

                // Strategy 4: Generic link-based extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href || '';
                        if (text.length > 5 && text.length < 200 && !seen[text]) {
                            if (href.includes('career') || href.includes('job') || href.includes('opening') || href.includes('apply')) {
                                if (!href.includes('login') && !href.includes('javascript:') && !href.includes('#')) {
                                    seen[text] = true;
                                    results.push({title: text, location: '', department: '', qualifications: '', url: href});
                                }
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Selenium extraction found {len(js_jobs)} jobs")
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    qualifications = job_data.get('qualifications', '')
                    url = job_data.get('url', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5(f"{title}_{location}_{idx}".encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': qualifications[:2000] if qualifications else '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found via Selenium")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Selenium scraping error: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs


if __name__ == '__main__':
    scraper = ShriramFinanceScraper()
    results = scraper.scrape()
    print(f"\nTotal jobs found: {len(results)}")
    for job in results[:10]:
        print(f"  - {job['title']} | {job['location']} | {job['department']} | {job['apply_url']}")

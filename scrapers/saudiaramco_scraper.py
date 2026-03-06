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

logger = setup_logger('saudiaramco_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class SaudiAramcoScraper:
    def __init__(self):
        self.company_name = 'Saudi Aramco'
        self.url = 'https://india.aramco.com/en/careers/current-openings'
        self.alt_url = 'https://careers.aramco.com/'
        self.base_url = 'https://india.aramco.com'
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
        country = 'India'
        # Detect if Saudi Arabia based
        if any(k in location_str.lower() for k in ['saudi', 'dhahran', 'riyadh', 'jeddah', 'ksa']):
            country = 'Saudi Arabia'
        return city, state, country

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Saudi Aramco — try India page first, fallback to Taleo"""
        jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name}")

            # Strategy 1: India page with requests
            jobs = self._scrape_india_page_requests()

            if jobs:
                logger.info(f"India page (requests) found {len(jobs)} jobs")
                return jobs

            # Strategy 2: India page with Selenium
            logger.info("Requests-based India page scraping returned no jobs, trying Selenium")
            jobs = self._scrape_india_page_selenium()

            if jobs:
                logger.info(f"India page (Selenium) found {len(jobs)} jobs")
                return jobs

            # Strategy 3: Fallback to Taleo careers page
            logger.info("India page returned no jobs, trying Taleo careers portal")
            jobs = self._scrape_taleo_careers()

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
        return jobs

    def _scrape_india_page_requests(self):
        """Scrape the India-specific careers page using requests"""
        jobs = []

        try:
            session = requests.Session()
            session.headers.update(self.headers)

            response = session.get(self.url, timeout=30)
            response.raise_for_status()
            logger.info(f"India career page HTTP {response.status_code}, length: {len(response.text)}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for job listing sections
            job_sections = soup.find_all(['div', 'section', 'article', 'li'], class_=re.compile(
                r'job|career|opening|position|vacancy|listing|opportunity', re.I
            ))

            for idx, section in enumerate(job_sections):
                text = section.get_text(strip=True)
                if len(text) < 10:
                    continue

                title_el = section.find(['h2', 'h3', 'h4', 'h5', 'strong', 'a', 'b'])
                title = title_el.get_text(strip=True) if title_el else ''
                if not title or len(title) < 3:
                    continue

                location = ''
                loc_el = section.find(class_=re.compile(r'location|city|place', re.I))
                if loc_el:
                    location = loc_el.get_text(strip=True)

                department = ''
                dept_el = section.find(class_=re.compile(r'department|dept|team|category', re.I))
                if dept_el:
                    department = dept_el.get_text(strip=True)

                description = ''
                desc_el = section.find(class_=re.compile(r'description|desc|summary|content', re.I))
                if desc_el:
                    description = desc_el.get_text(strip=True)[:2000]

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
                    'description': description,
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

            # Also look for tables
            if not jobs:
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for idx, row in enumerate(rows):
                        cells = row.find_all('td')
                        if len(cells) < 1:
                            continue
                        title = cells[0].get_text(strip=True)
                        if not title or len(title) < 3:
                            continue
                        location = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        department = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                        description = cells[3].get_text(strip=True) if len(cells) > 3 else ''

                        link = row.find('a', href=True)
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
                            'description': description[:2000] if description else '',
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

        except Exception as e:
            logger.error(f"India page requests error: {str(e)}")

        return jobs

    def _scrape_india_page_selenium(self):
        """Scrape India page with Selenium for JS-rendered content"""
        jobs = []
        driver = None

        try:
            driver = self.setup_driver()
            logger.info(f"Navigating to India page: {self.url}")
            driver.get(self.url)
            time.sleep(12)

            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Job listing elements
                var cards = document.querySelectorAll('[class*="job"], [class*="career"], [class*="opening"], [class*="position"], [class*="vacancy"], [class*="listing"], [class*="opportunity"]');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = card.innerText.trim();
                    if (text.length < 10 || text.length > 3000) continue;

                    var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="name"], strong, a');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title) title = text.split('\\n')[0].trim();
                    if (!title || title.length < 3 || title.length > 200) continue;

                    var locEl = card.querySelector('[class*="location"], [class*="city"]');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var deptEl = card.querySelector('[class*="department"], [class*="dept"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';

                    var descEl = card.querySelector('[class*="description"], [class*="desc"], [class*="summary"]');
                    var description = descEl ? descEl.innerText.trim().substring(0, 500) : '';

                    var linkEl = card.querySelector('a[href]');
                    var url = linkEl ? linkEl.href : '';

                    if (!seen[title + location]) {
                        seen[title + location] = true;
                        results.push({
                            title: title, location: location, department: department,
                            description: description, url: url
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
                        var department = cells.length > 2 ? cells[2].innerText.trim() : '';
                        var link = rows[i].querySelector('a[href]');
                        var url = link ? link.href : '';

                        if (!seen[title]) {
                            seen[title] = true;
                            results.push({title: title, location: location, department: department, description: '', url: url});
                        }
                    }
                }

                // Strategy 3: Link-based extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href || '';
                        if (text.length > 5 && text.length < 200 && !seen[text]) {
                            if (href.includes('career') || href.includes('job') || href.includes('opening') || href.includes('position') || href.includes('apply') || href.includes('requisition')) {
                                if (!href.includes('login') && !href.includes('javascript:') && !href.includes('#')) {
                                    seen[text] = true;
                                    results.push({title: text, location: '', department: '', description: '', url: href});
                                }
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"India page Selenium found {len(js_jobs)} jobs")
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    description = job_data.get('description', '')
                    url = job_data.get('url', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5(f"{title}_{location}_{idx}".encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': description[:2000] if description else '',
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
                logger.warning("No jobs found on India page via Selenium")

        except Exception as e:
            logger.error(f"India page Selenium error: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _scrape_taleo_careers(self):
        """Fallback: Scrape from Taleo careers portal"""
        jobs = []
        driver = None

        try:
            driver = self.setup_driver()
            logger.info(f"Navigating to Taleo portal: {self.alt_url}")
            driver.get(self.alt_url)
            time.sleep(15)

            # Scroll to load content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            # Try to search for India-specific jobs
            try:
                driver.execute_script("""
                    var searchInputs = document.querySelectorAll('input[type="text"], input[name*="search"], input[name*="keyword"], input[placeholder*="Search"], input[placeholder*="search"]');
                    for (var i = 0; i < searchInputs.length; i++) {
                        searchInputs[i].value = 'India';
                        searchInputs[i].dispatchEvent(new Event('input', {bubbles: true}));
                        searchInputs[i].dispatchEvent(new Event('change', {bubbles: true}));
                    }
                    var searchBtns = document.querySelectorAll('button[type="submit"], button[class*="search"], input[type="submit"]');
                    if (searchBtns.length > 0) searchBtns[0].click();
                """)
                time.sleep(8)
            except Exception:
                pass

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Taleo-specific selectors
                var cards = document.querySelectorAll('[class*="job"], [class*="requisition"], [class*="posting"], [class*="search-result"], [class*="opening"]');
                if (cards.length === 0) {
                    cards = document.querySelectorAll('tr[class*="data"], li[class*="result"], div[class*="result"]');
                }

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = card.innerText.trim();
                    if (text.length < 10 || text.length > 3000) continue;

                    var titleEl = card.querySelector('h2, h3, h4, a[class*="title"], a[class*="job"], [class*="title"], strong');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : text.split('\\n')[0].trim();
                    if (!title || title.length < 3 || title.length > 200) continue;

                    var locEl = card.querySelector('[class*="location"], [class*="city"]');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var deptEl = card.querySelector('[class*="department"], [class*="category"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';

                    var linkEl = card.querySelector('a[href]');
                    var url = linkEl ? linkEl.href : '';

                    if (!seen[title + location]) {
                        seen[title + location] = true;
                        results.push({title: title, location: location, department: department, url: url});
                    }
                }

                // Generic link extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href || '';
                        if (text.length > 5 && text.length < 200 && !seen[text]) {
                            if (href.includes('job') || href.includes('requisition') || href.includes('posting') || href.includes('career') || href.includes('apply')) {
                                if (!href.includes('login') && !href.includes('javascript:')) {
                                    seen[text] = true;
                                    results.push({title: text, location: '', department: '', url: href});
                                }
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Taleo portal found {len(js_jobs)} jobs")
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
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
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found on Taleo portal either")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Taleo page body preview: {body_text}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Taleo scraping error: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs


if __name__ == '__main__':
    scraper = SaudiAramcoScraper()
    results = scraper.scrape()
    print(f"\nTotal jobs found: {len(results)}")
    for job in results[:10]:
        print(f"  - {job['title']} | {job['location']} | {job['department']} | {job['apply_url']}")

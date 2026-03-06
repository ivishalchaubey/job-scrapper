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

logger = setup_logger('finolex_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class FinolexScraper:
    def __init__(self):
        self.company_name = 'Finolex'
        self.url = 'https://www.finolex.com/Team/Career'
        self.base_url = 'https://www.finolex.com'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.finolex.com/',
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
        for part in parts:
            if part.strip().lower() in ['india', 'in', 'ind']:
                country = 'India'
        return city, state, country

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Finolex Career page — try requests first, fallback to Selenium"""
        jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name}")

            # Strategy 1: requests + BeautifulSoup (ASP.NET server-rendered DataTable)
            jobs = self._scrape_with_requests()

            if jobs:
                logger.info(f"Requests-based scraping found {len(jobs)} jobs")
                return jobs

            # Strategy 2: Try GetJobDescription API endpoint
            logger.info("Trying GetJobDescription API endpoint...")
            jobs = self._scrape_api_endpoint()

            if jobs:
                logger.info(f"API endpoint scraping found {len(jobs)} jobs")
                return jobs

            # Strategy 3: Fallback to Selenium
            logger.info("Requests-based scraping returned no jobs, falling back to Selenium")
            jobs = self._scrape_with_selenium()

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
        return jobs

    def _scrape_with_requests(self):
        """Scrape using requests + BeautifulSoup for server-rendered DataTable"""
        jobs = []

        try:
            session = requests.Session()
            session.headers.update(self.headers)

            response = session.get(self.url, timeout=30)
            response.raise_for_status()
            logger.info(f"Career page HTTP {response.status_code}, length: {len(response.text)}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for DataTable content
            table = soup.find('table', {'id': re.compile(r'dataTable|DataTable|jobTable|tblCareer', re.I)})
            if not table:
                table = soup.find('table', class_=re.compile(r'dataTable|display|table', re.I))
            if not table:
                tables = soup.find_all('table')
                for t in tables:
                    rows = t.find_all('tr')
                    if len(rows) > 1:
                        table = t
                        break

            if table:
                logger.info("Found DataTable on page")
                rows = table.find_all('tr')
                for idx, row in enumerate(rows):
                    cells = row.find_all(['td', 'th'])
                    if not cells or len(cells) < 2:
                        continue

                    # Skip header rows
                    if row.find('th'):
                        continue

                    title = cells[0].get_text(strip=True) if len(cells) > 0 else ''
                    location = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                    department = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                    description = cells[3].get_text(strip=True) if len(cells) > 3 else ''

                    if not title or len(title) < 3:
                        continue

                    # Extract apply URL from link in row
                    link = row.find('a', href=True)
                    apply_url = ''
                    if link:
                        href = link.get('href', '')
                        if href.startswith('/'):
                            apply_url = self.base_url + href
                        elif href.startswith('http'):
                            apply_url = href

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

            # Also look for non-table job listing elements
            if not jobs:
                job_divs = soup.find_all('div', class_=re.compile(r'job|career|opening|position|vacancy', re.I))
                for idx, div in enumerate(job_divs):
                    text = div.get_text(strip=True)
                    if len(text) < 10:
                        continue

                    title_el = div.find(['h2', 'h3', 'h4', 'h5', 'a', 'strong'])
                    title = title_el.get_text(strip=True) if title_el else text.split('\n')[0].strip()

                    if not title or len(title) < 3:
                        continue

                    link = div.find('a', href=True)
                    apply_url = ''
                    if link:
                        href = link.get('href', '')
                        if href.startswith('/'):
                            apply_url = self.base_url + href
                        elif href.startswith('http'):
                            apply_url = href

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

    def _scrape_api_endpoint(self):
        """Try the ASP.NET GetJobDescription API endpoint"""
        jobs = []

        try:
            session = requests.Session()
            session.headers.update(self.headers)

            # First get the career page to establish session/cookies
            session.get(self.url, timeout=30)

            # Try the API endpoint
            api_url = f"{self.base_url}/Team/GetJobDescription"
            for content_type in ['application/json', 'application/x-www-form-urlencoded']:
                try:
                    response = session.post(api_url, headers={'Content-Type': content_type}, timeout=30)
                    if response.status_code == 200 and response.text:
                        try:
                            data = response.json()
                            if isinstance(data, list):
                                for idx, item in enumerate(data):
                                    title = item.get('Title', item.get('title', item.get('JobTitle', '')))
                                    if not title:
                                        continue
                                    location = item.get('Location', item.get('location', ''))
                                    department = item.get('Department', item.get('department', ''))
                                    description = item.get('Description', item.get('description', item.get('JobDescription', '')))
                                    job_id_raw = item.get('Id', item.get('id', item.get('JobId', str(idx))))

                                    job_id = hashlib.md5(str(job_id_raw).encode()).hexdigest()[:12]
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
                                        'apply_url': self.url,
                                        'posted_date': '',
                                        'job_function': '',
                                        'experience_level': '',
                                        'salary_range': '',
                                        'remote_type': '',
                                        'status': 'active'
                                    })
                        except ValueError:
                            logger.debug("API response not JSON, trying HTML parse")
                            soup = BeautifulSoup(response.text, 'html.parser')
                            # Parse any returned HTML for job data
                            items = soup.find_all(['div', 'tr', 'li'])
                            for idx, item in enumerate(items):
                                text = item.get_text(strip=True)
                                if len(text) > 10:
                                    logger.debug(f"API HTML item: {text[:100]}")
                except Exception as e:
                    logger.debug(f"API call with {content_type} failed: {str(e)}")

        except Exception as e:
            logger.error(f"API endpoint scraping error: {str(e)}")

        return jobs

    def _scrape_with_selenium(self):
        """Fallback: Scrape using Selenium for JavaScript-rendered DataTable"""
        jobs = []
        driver = None

        try:
            driver = self.setup_driver()
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(10)

            # Scroll to trigger lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Extract from DataTable or generic job elements
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: DataTable rows
                var table = document.querySelector('table.dataTable, table.display, table[id*="DataTable"], table[id*="career"], table[id*="Career"]');
                if (!table) {
                    var tables = document.querySelectorAll('table');
                    for (var i = 0; i < tables.length; i++) {
                        if (tables[i].querySelectorAll('tr').length > 2) {
                            table = tables[i];
                            break;
                        }
                    }
                }

                if (table) {
                    var rows = table.querySelectorAll('tbody tr, tr');
                    for (var i = 0; i < rows.length; i++) {
                        var cells = rows[i].querySelectorAll('td');
                        if (cells.length < 2) continue;
                        var title = cells[0] ? cells[0].innerText.trim() : '';
                        var location = cells[1] ? cells[1].innerText.trim() : '';
                        var department = cells.length > 2 ? cells[2].innerText.trim() : '';
                        var description = cells.length > 3 ? cells[3].innerText.trim() : '';
                        var link = rows[i].querySelector('a[href]');
                        var url = link ? link.href : '';

                        if (title && title.length > 2 && !seen[title + location]) {
                            seen[title + location] = true;
                            results.push({
                                title: title, location: location, department: department,
                                description: description, url: url
                            });
                        }
                    }
                }

                // Strategy 2: Generic job card/div elements
                if (results.length === 0) {
                    var cards = document.querySelectorAll('[class*="job"], [class*="career"], [class*="opening"], [class*="position"], [class*="vacancy"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var text = card.innerText.trim();
                        if (text.length < 10) continue;
                        var titleEl = card.querySelector('h2, h3, h4, h5, a, strong, [class*="title"]');
                        var title = titleEl ? titleEl.innerText.trim() : text.split('\\n')[0].trim();
                        var linkEl = card.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';
                        if (title && title.length > 2 && title.length < 200 && !seen[title]) {
                            seen[title] = true;
                            results.push({title: title, location: '', department: '', description: '', url: url});
                        }
                    }
                }

                // Strategy 3: Links containing job-related URLs
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="career"], a[href*="job"], a[href*="opening"], a[href*="Career"], a[href*="Job"]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href;
                        if (text && text.length > 3 && text.length < 200 && !seen[text]) {
                            if (!href.includes('login') && !href.includes('javascript:')) {
                                seen[text] = true;
                                results.push({title: text, location: '', department: '', description: '', url: href});
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
                logger.warning("No jobs found via Selenium either")
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
    scraper = FinolexScraper()
    results = scraper.scrape()
    print(f"\nTotal jobs found: {len(results)}")
    for job in results[:10]:
        print(f"  - {job['title']} | {job['location']} | {job['department']} | {job['apply_url']}")

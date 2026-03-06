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

logger = setup_logger('ifb_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class IFBScraper:
    def __init__(self):
        self.company_name = 'IFB'
        self.url = 'https://www.ifbindustries.com/career.php'
        self.base_url = 'https://www.ifbindustries.com'
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
        """Scrape jobs from IFB career page — try requests first, fallback to Selenium"""
        jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name}")

            # Strategy 1: requests + BeautifulSoup (PHP server-rendered)
            jobs = self._scrape_with_requests()

            if jobs:
                logger.info(f"Requests-based scraping found {len(jobs)} jobs")
                return jobs

            # Strategy 2: Fallback to Selenium
            logger.info("Requests-based scraping returned no jobs, falling back to Selenium")
            jobs = self._scrape_with_selenium()

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
        return jobs

    def _scrape_with_requests(self):
        """Scrape using requests + BeautifulSoup for PHP-rendered page"""
        jobs = []

        try:
            session = requests.Session()
            session.headers.update(self.headers)

            response = session.get(self.url, timeout=30)
            response.raise_for_status()
            logger.info(f"Career page HTTP {response.status_code}, length: {len(response.text)}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for job listing tables
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue

                logger.info(f"Found table with {len(rows)} rows")
                for idx, row in enumerate(rows):
                    cells = row.find_all('td')
                    if not cells or len(cells) < 1:
                        continue

                    # Skip header-like rows
                    if row.find('th'):
                        continue

                    title = cells[0].get_text(strip=True) if len(cells) > 0 else ''
                    location = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                    description = cells[2].get_text(strip=True) if len(cells) > 2 else ''

                    if not title or len(title) < 3:
                        continue

                    link = row.find('a', href=True)
                    apply_url = ''
                    if link:
                        href = link.get('href', '')
                        if href.startswith('/'):
                            apply_url = self.base_url + href
                        elif href.startswith('http'):
                            apply_url = href
                        elif href and not href.startswith('#') and not href.startswith('javascript'):
                            apply_url = self.base_url + '/' + href

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
                        'department': '',
                        'apply_url': apply_url if apply_url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            # Also look for job listing divs/sections
            if not jobs:
                job_sections = soup.find_all('div', class_=re.compile(r'job|career|opening|position|vacancy|listing', re.I))
                if not job_sections:
                    job_sections = soup.find_all(['div', 'section', 'article'], class_=re.compile(r'job|career|opening|position', re.I))

                for idx, section in enumerate(job_sections):
                    text = section.get_text(strip=True)
                    if len(text) < 10:
                        continue

                    title_el = section.find(['h2', 'h3', 'h4', 'h5', 'strong', 'b'])
                    title = title_el.get_text(strip=True) if title_el else ''

                    if not title:
                        # Try to get title from link text
                        link = section.find('a')
                        if link:
                            title = link.get_text(strip=True)

                    if not title or len(title) < 3:
                        continue

                    # Try to extract location from text
                    location = ''
                    location_patterns = [
                        r'Location\s*[:\-]\s*(.+?)(?:\n|$)',
                        r'Place\s*[:\-]\s*(.+?)(?:\n|$)',
                    ]
                    for pattern in location_patterns:
                        match = re.search(pattern, text, re.I)
                        if match:
                            location = match.group(1).strip()
                            break

                    # Try to extract description
                    description = ''
                    desc_patterns = [
                        r'Description\s*[:\-]\s*(.+?)(?:\n|$)',
                        r'Requirement\s*[:\-]\s*(.+?)(?:\n|$)',
                    ]
                    for pattern in desc_patterns:
                        match = re.search(pattern, text, re.I)
                        if match:
                            description = match.group(1).strip()
                            break

                    link = section.find('a', href=True)
                    apply_url = ''
                    if link:
                        href = link.get('href', '')
                        if href.startswith('http'):
                            apply_url = href
                        elif href.startswith('/'):
                            apply_url = self.base_url + href

                    job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]
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
                        'department': '',
                        'apply_url': apply_url if apply_url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

            # Strategy: look for accordion/expandable sections common in PHP career pages
            if not jobs:
                accordions = soup.find_all(['div', 'li'], class_=re.compile(r'accordion|panel|collapse|expand|toggle', re.I))
                for idx, acc in enumerate(accordions):
                    title_el = acc.find(['h2', 'h3', 'h4', 'h5', 'a', 'button', 'strong'])
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue

                    body = acc.find('div', class_=re.compile(r'body|content|panel-body|collapse', re.I))
                    description = body.get_text(strip=True)[:2000] if body else ''

                    job_id = hashlib.md5(f"{title}_{idx}".encode()).hexdigest()[:12]

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': description,
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': self.url,
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

    def _scrape_with_selenium(self):
        """Fallback: Scrape using Selenium for JavaScript-rendered content"""
        jobs = []
        driver = None

        try:
            driver = self.setup_driver()
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(10)

            # Scroll to load all content
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Table rows
                var tables = document.querySelectorAll('table');
                for (var t = 0; t < tables.length; t++) {
                    var rows = tables[t].querySelectorAll('tbody tr, tr');
                    for (var i = 0; i < rows.length; i++) {
                        var cells = rows[i].querySelectorAll('td');
                        if (cells.length < 1) continue;
                        var title = cells[0] ? cells[0].innerText.trim() : '';
                        var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                        var description = cells.length > 2 ? cells[2].innerText.trim() : '';
                        var link = rows[i].querySelector('a[href]');
                        var url = link ? link.href : '';

                        if (title && title.length > 2 && !seen[title + location]) {
                            seen[title + location] = true;
                            results.push({title: title, location: location, description: description, url: url});
                        }
                    }
                }

                // Strategy 2: Job card/div elements
                if (results.length === 0) {
                    var cards = document.querySelectorAll('[class*="job"], [class*="career"], [class*="opening"], [class*="position"], [class*="vacancy"], [class*="listing"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var text = card.innerText.trim();
                        if (text.length < 10 || text.length > 2000) continue;

                        var titleEl = card.querySelector('h2, h3, h4, h5, strong, b, a, [class*="title"]');
                        var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : text.split('\\n')[0].trim();
                        var linkEl = card.querySelector('a[href]');
                        var url = linkEl ? linkEl.href : '';

                        if (title && title.length > 2 && title.length < 200 && !seen[title]) {
                            seen[title] = true;
                            results.push({title: title, location: '', description: '', url: url});
                        }
                    }
                }

                // Strategy 3: Accordion/panel sections
                if (results.length === 0) {
                    var panels = document.querySelectorAll('[class*="accordion"], [class*="panel"], [class*="collapse"], [class*="toggle"]');
                    for (var i = 0; i < panels.length; i++) {
                        var panel = panels[i];
                        var titleEl = panel.querySelector('h2, h3, h4, h5, a, button, strong');
                        if (!titleEl) continue;
                        var title = titleEl.innerText.trim();
                        if (!title || title.length < 3) continue;
                        if (seen[title]) continue;
                        seen[title] = true;
                        var body = panel.querySelector('[class*="body"], [class*="content"]');
                        var desc = body ? body.innerText.trim().substring(0, 500) : '';
                        results.push({title: title, location: '', description: desc, url: ''});
                    }
                }

                // Strategy 4: Generic job-related links
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var href = link.href || '';
                        var text = link.innerText.trim();
                        if (text.length > 3 && text.length < 200 && !seen[text]) {
                            if (href.includes('career') || href.includes('job') || href.includes('opening') || href.includes('position') || href.includes('apply')) {
                                if (!href.includes('login') && !href.includes('javascript:')) {
                                    seen[text] = true;
                                    results.push({title: text, location: '', description: '', url: href});
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
                        'department': '',
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
    scraper = IFBScraper()
    results = scraper.scrape()
    print(f"\nTotal jobs found: {len(results)}")
    for job in results[:10]:
        print(f"  - {job['title']} | {job['location']} | {job['apply_url']}")

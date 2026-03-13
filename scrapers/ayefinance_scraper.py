import requests
import hashlib
import re
import json
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
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('ayefinance_scraper')

class AyeFinanceScraper:
    def __init__(self):
        self.company_name = "Aye Finance"
        self.url = "https://ayefin.com/careers/join-us#opportunities"
        self.base_url = 'https://www.ayefin.com'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

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
        """Scrape jobs from Aye Finance — try Next.js data route first, fallback to Selenium"""
        jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name}")

            # Strategy 1: Try to discover Next.js buildId and fetch JSON data
            jobs = self._scrape_nextjs_data()

            if jobs:
                logger.info(f"Next.js data scraping found {len(jobs)} jobs")
                return jobs

            # Strategy 2: Try requests + BS4 for SSR content
            logger.info("Next.js data not available, trying SSR content")
            jobs = self._scrape_with_requests()

            if jobs:
                logger.info(f"Requests-based scraping found {len(jobs)} jobs")
                return jobs

            # Strategy 3: Fallback to Selenium
            logger.info("Requests-based scraping returned no jobs, falling back to Selenium")
            jobs = self._scrape_with_selenium()

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
        return jobs

    def _scrape_nextjs_data(self):
        """Try to discover Next.js buildId and fetch JSON data from /_next/data/"""
        jobs = []

        try:
            session = requests.Session()
            session.headers.update(self.headers)

            # Fetch the main page to discover buildId
            response = session.get(self.url, timeout=30)
            response.raise_for_status()

            # Look for buildId in the page source
            build_id = None
            # Pattern 1: __NEXT_DATA__ script
            match = re.search(r'"buildId"\s*:\s*"([^"]+)"', response.text)
            if match:
                build_id = match.group(1)
                logger.info(f"Found Next.js buildId: {build_id}")

            # Pattern 2: /_next/static/ paths
            if not build_id:
                match = re.search(r'/_next/static/([a-zA-Z0-9_-]+)/', response.text)
                if match:
                    build_id = match.group(1)
                    logger.info(f"Found buildId from static path: {build_id}")

            if build_id:
                # Try to fetch the data JSON
                data_url = f"{self.base_url}/_next/data/{build_id}/careers/join-us.json"
                logger.info(f"Trying Next.js data URL: {data_url}")

                try:
                    data_response = session.get(data_url, timeout=30)
                    if data_response.status_code == 200:
                        data = data_response.json()
                        logger.info(f"Got Next.js data response")

                        # Extract jobs from __NEXT_DATA__ pageProps
                        page_props = data.get('pageProps', {})
                        jobs = self._extract_jobs_from_nextjs_data(page_props)
                except Exception as e:
                    logger.debug(f"Next.js data fetch failed: {str(e)}")

            # Also try parsing __NEXT_DATA__ from the HTML directly
            if not jobs:
                match = re.search(r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>', response.text, re.DOTALL)
                if match:
                    try:
                        next_data = json.loads(match.group(1))
                        page_props = next_data.get('props', {}).get('pageProps', {})
                        jobs = self._extract_jobs_from_nextjs_data(page_props)
                    except json.JSONDecodeError:
                        logger.debug("Failed to parse __NEXT_DATA__ JSON")

        except Exception as e:
            logger.error(f"Next.js data scraping error: {str(e)}")

        return jobs

    def _extract_jobs_from_nextjs_data(self, page_props):
        """Extract jobs from Next.js page props data"""
        jobs = []

        try:
            # Search recursively for job-like data
            def find_jobs(obj, depth=0):
                if depth > 10:
                    return []
                found = []

                if isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, dict):
                            # Check if this looks like a job object
                            title_keys = ['title', 'Title', 'jobTitle', 'position', 'name', 'role']
                            title = ''
                            for key in title_keys:
                                if key in item and isinstance(item[key], str) and len(item[key]) > 2:
                                    title = item[key]
                                    break

                            if title:
                                found.append(item)
                            else:
                                found.extend(find_jobs(item, depth + 1))
                        elif isinstance(item, list):
                            found.extend(find_jobs(item, depth + 1))

                elif isinstance(obj, dict):
                    for key, value in obj.items():
                        if isinstance(value, (list, dict)):
                            found.extend(find_jobs(value, depth + 1))

                return found

            job_items = find_jobs(page_props)
            logger.info(f"Found {len(job_items)} potential job items in Next.js data")

            for idx, item in enumerate(job_items):
                title = ''
                for key in ['title', 'Title', 'jobTitle', 'position', 'name', 'role']:
                    if key in item and isinstance(item[key], str):
                        title = item[key]
                        break

                if not title or len(title) < 3:
                    continue

                location = ''
                for key in ['location', 'Location', 'city', 'place']:
                    if key in item and isinstance(item[key], str):
                        location = item[key]
                        break

                department = ''
                for key in ['department', 'Department', 'dept', 'team', 'category']:
                    if key in item and isinstance(item[key], str):
                        department = item[key]
                        break

                description = ''
                for key in ['description', 'Description', 'desc', 'summary', 'content']:
                    if key in item and isinstance(item[key], str):
                        description = item[key][:2000]
                        break

                apply_url = ''
                for key in ['url', 'link', 'applyUrl', 'href', 'slug']:
                    if key in item and isinstance(item[key], str):
                        val = item[key]
                        if val.startswith('http'):
                            apply_url = val
                        elif val.startswith('/'):
                            apply_url = self.base_url + val
                        else:
                            apply_url = f"{self.base_url}/careers/{val}"
                        break

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

        except Exception as e:
            logger.error(f"Error extracting jobs from Next.js data: {str(e)}")

        return jobs

    def _scrape_with_requests(self):
        """Scrape using requests + BS4 for SSR content"""
        jobs = []

        try:
            session = requests.Session()
            session.headers.update(self.headers)

            response = session.get(self.url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for job listing sections
            job_sections = soup.find_all(['div', 'section', 'article'], class_=re.compile(
                r'job|career|opening|position|vacancy|listing|role', re.I
            ))

            for idx, section in enumerate(job_sections):
                text = section.get_text(strip=True)
                if len(text) < 10:
                    continue

                title_el = section.find(['h2', 'h3', 'h4', 'h5', 'strong', 'a'])
                title = title_el.get_text(strip=True) if title_el else ''

                if not title or len(title) < 3:
                    continue

                # Extract location
                location = ''
                loc_el = section.find(class_=re.compile(r'location|city|place', re.I))
                if loc_el:
                    location = loc_el.get_text(strip=True)
                else:
                    for city in ['Gurugram', 'Gurgaon', 'Pan India', 'Delhi', 'Mumbai', 'Bangalore', 'Noida']:
                        if city.lower() in text.lower():
                            location = city
                            break

                # Extract department
                department = ''
                dept_el = section.find(class_=re.compile(r'department|dept|team|category', re.I))
                if dept_el:
                    department = dept_el.get_text(strip=True)
                else:
                    for dept in ['Technology', 'Data Science', 'Collections', 'Legal', 'Operations', 'Finance', 'HR']:
                        if dept.lower() in text.lower():
                            department = dept
                            break

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
                    'description': '',
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
            logger.error(f"Requests-based scraping error: {str(e)}")

        return jobs

    def _scrape_with_selenium(self):
        """Fallback: Scrape using Selenium for client-side rendered content"""
        jobs = []
        driver = None

        try:
            driver = self.setup_driver()
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(12)

            # Scroll to load lazy content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Look for job card/listing elements
                var cards = document.querySelectorAll('[class*="job"], [class*="career"], [class*="opening"], [class*="position"], [class*="role"], [class*="listing"], [class*="vacancy"]');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = card.innerText.trim();
                    if (text.length < 10 || text.length > 2000) continue;

                    var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="name"], strong, a');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title) title = text.split('\\n')[0].trim();

                    var locEl = card.querySelector('[class*="location"], [class*="city"], [class*="place"]');
                    var location = locEl ? locEl.innerText.trim() : '';
                    if (!location) {
                        var lines = text.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            if (lines[j].match(/Gurugram|Gurgaon|Pan India|Delhi|Mumbai|Bangalore|Noida/i)) {
                                location = lines[j].trim();
                                break;
                            }
                        }
                    }

                    var deptEl = card.querySelector('[class*="department"], [class*="dept"], [class*="team"], [class*="category"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';
                    if (!department) {
                        var lines = text.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            if (lines[j].match(/Technology|Data Science|Collections|Legal|Operations|Finance|HR/i)) {
                                department = lines[j].trim();
                                break;
                            }
                        }
                    }

                    var linkEl = card.querySelector('a[href]');
                    var url = linkEl ? linkEl.href : '';

                    if (title && title.length > 2 && title.length < 200 && !seen[title + location]) {
                        seen[title + location] = true;
                        results.push({title: title, location: location, department: department, url: url});
                    }
                }

                // Strategy 2: Accordion/expandable sections (common for Next.js career pages)
                if (results.length === 0) {
                    var sections = document.querySelectorAll('[class*="accordion"], [class*="expand"], [class*="collapse"], [class*="tab-content"], details, [class*="category"]');
                    for (var i = 0; i < sections.length; i++) {
                        var items = sections[i].querySelectorAll('li, [class*="item"], [class*="row"], div > div');
                        for (var j = 0; j < items.length; j++) {
                            var text = items[j].innerText.trim();
                            if (text.length < 5 || text.length > 500) continue;
                            var title = text.split('\\n')[0].trim();
                            if (title.length > 2 && title.length < 200 && !seen[title]) {
                                seen[title] = true;
                                var location = '';
                                if (text.match(/Gurugram|Gurgaon|Pan India|Delhi|Mumbai/i)) {
                                    var m = text.match(/(Gurugram|Gurgaon|Pan India|Delhi|Mumbai|Bangalore|Noida)/i);
                                    if (m) location = m[1];
                                }
                                results.push({title: title, location: location, department: '', url: ''});
                            }
                        }
                    }
                }

                // Strategy 3: Generic link-based extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href || '';
                        if (text.length > 5 && text.length < 200 && !seen[text]) {
                            if (href.includes('career') || href.includes('job') || href.includes('opening') || href.includes('position') || href.includes('apply')) {
                                if (!href.includes('login') && !href.includes('javascript:') && !href.includes('#')) {
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
                logger.info(f"Selenium extraction found {len(js_jobs)} jobs")
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
    scraper = AyeFinanceScraper()
    results = scraper.scrape()
    print(f"\nTotal jobs found: {len(results)}")
    for job in results[:10]:
        print(f"  - {job['title']} | {job['location']} | {job['department']} | {job['apply_url']}")

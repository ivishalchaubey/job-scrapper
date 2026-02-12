from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import traceback
from pathlib import Path
from datetime import datetime
import os
import stat


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('microsoft_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class MicrosoftScraper:
    def __init__(self):
        self.company_name = 'Microsoft'
        self.url = 'https://jobs.careers.microsoft.com/global/en/search?l=en_us&pg=1&pgSz=20&o=Relevance&flt=true&ref=cms&lc=India'
        # Microsoft careers moved to Eightfold AI PCSX platform (Nov 2026)
        self.search_url = 'https://apply.careers.microsoft.com/careers?hl=en&location=India'
        self.pcsx_api_path = '/api/pcsx/search?domain=microsoft.com&query=&location=India&start={start}&hl=en'
        self.base_job_url = 'https://apply.careers.microsoft.com/careers/job'

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

        driver_path = CHROMEDRIVER_PATH
        if not os.path.exists(driver_path):
            logger.warning(f"Fresh chromedriver not found at {driver_path}, trying system chromedriver")
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()
            driver_path_obj = Path(driver_path)
            if driver_path_obj.name != 'chromedriver':
                parent = driver_path_obj.parent
                actual_driver = parent / 'chromedriver'
                if actual_driver.exists():
                    driver_path = str(actual_driver)
                else:
                    for file in parent.rglob('chromedriver'):
                        if file.is_file() and not file.name.endswith('.zip'):
                            driver_path = str(file)
                            break

        try:
            current_permissions = os.stat(driver_path).st_mode
            os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            logger.warning(f"Could not set permissions on chromedriver: {str(e)}")

        try:
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"Service driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs - try Selenium PCSX API first, then DOM scraping fallback."""
        # Primary method: Selenium + in-browser PCSX API calls
        try:
            api_jobs = self._scrape_via_pcsx_api(max_pages)
            if api_jobs:
                logger.info(f"PCSX API method returned {len(api_jobs)} jobs")
                return api_jobs
            else:
                logger.warning("PCSX API returned 0 jobs, falling back to DOM scraping")
        except Exception as e:
            logger.warning(f"PCSX API failed: {str(e)}, falling back to DOM scraping")

        # Fallback: Selenium DOM scraping with PCSX selectors
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_pcsx_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Use Selenium to load the Eightfold PCSX page, then call the PCSX search API from browser context."""
        driver = None
        all_jobs = []
        scraped_ids = set()
        page_size = 10  # PCSX API returns 10 per page

        try:
            driver = self.setup_driver()

            # Visit the Eightfold-powered careers search page to establish session
            logger.info(f"Loading Microsoft PCSX careers page: {self.search_url}")
            driver.get(self.search_url)
            time.sleep(15)  # SPA needs time to render and establish auth

            logger.info(f"Page loaded: {driver.current_url}, title: {driver.title}")

            page = 0
            while page < max_pages:
                start = page * page_size
                api_path = self.pcsx_api_path.format(start=start)
                logger.info(f"PCSX API: fetching start={start} (page {page + 1}/{max_pages})")

                # Call the PCSX search API from within the browser context (has session cookies)
                js_code = f"""
                    try {{
                        var xhr = new XMLHttpRequest();
                        xhr.open('GET', '{api_path}', false);
                        xhr.setRequestHeader('Accept', 'application/json');
                        xhr.send();
                        if (xhr.status === 200) {{
                            return JSON.parse(xhr.responseText);
                        }}
                        return {{'_error': true, 'status': xhr.status, 'text': xhr.responseText.substring(0, 300)}};
                    }} catch(e) {{
                        return {{'_error': true, 'message': e.message}};
                    }}
                """

                try:
                    data = driver.execute_script(js_code)
                except Exception as e:
                    logger.error(f"JS execution failed: {str(e)}")
                    break

                if not data or not isinstance(data, dict):
                    logger.warning("PCSX API returned empty or invalid response")
                    break

                if data.get('_error'):
                    logger.warning(f"PCSX API error: status={data.get('status')}, {data.get('text', data.get('message', ''))}")
                    break

                # Parse the PCSX response: {status, error, data: {positions: [...]}}
                positions = data.get('data', {}).get('positions', [])

                if not positions:
                    logger.info(f"No more positions at start={start}")
                    break

                logger.info(f"PCSX API returned {len(positions)} positions at start={start}")

                new_count = 0
                for pos in positions:
                    try:
                        job_data = self._parse_pcsx_position(pos)
                        if job_data and job_data['external_id'] not in scraped_ids:
                            all_jobs.append(job_data)
                            scraped_ids.add(job_data['external_id'])
                            new_count += 1
                    except Exception as e:
                        logger.error(f"Error parsing position: {str(e)}")
                        continue

                logger.info(f"Page {page + 1}: {new_count} new jobs (total: {len(all_jobs)})")

                # If we got fewer than page_size, no more results
                if len(positions) < page_size:
                    logger.info("Received fewer positions than page size, done.")
                    break

                page += 1

        except Exception as e:
            logger.error(f"PCSX API scraping failed: {str(e)}")
            logger.error(traceback.format_exc())
        finally:
            if driver:
                driver.quit()

        logger.info(f"PCSX API total: {len(all_jobs)}")
        return all_jobs

    def _parse_pcsx_position(self, pos):
        """Parse a single position from the PCSX search API response."""
        name = pos.get('name', '').strip()
        if not name:
            return None

        job_id = str(pos.get('id', ''))
        if not job_id:
            job_id = f"ms_pcsx_{hashlib.md5(name.encode()).hexdigest()[:8]}"

        # Build apply URL
        position_url = pos.get('positionUrl', '')
        if position_url:
            apply_url = f"https://apply.careers.microsoft.com{position_url}?hl=en"
        else:
            apply_url = f"{self.base_job_url}/{job_id}?hl=en"

        # Location
        locations = pos.get('locations', [])
        if isinstance(locations, list) and locations:
            location = locations[0] if isinstance(locations[0], str) else str(locations[0])
        elif isinstance(locations, str):
            location = locations
        else:
            location = 'India'

        # Department
        department = pos.get('department', '')

        # Work location option (onsite, remote, hybrid)
        work_location = pos.get('workLocationOption', '')

        # Posted date from timestamp
        posted_ts = pos.get('postedTs', 0)
        posted_date = ''
        if posted_ts:
            try:
                posted_date = datetime.fromtimestamp(posted_ts).strftime('%Y-%m-%d')
            except Exception:
                pass

        loc = self.parse_location(location)

        return {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'company_name': self.company_name,
            'title': name,
            'description': '',
            'location': location,
            'city': loc.get('city', ''),
            'state': loc.get('state', ''),
            'country': loc.get('country', 'India'),
            'employment_type': '',
            'department': department,
            'apply_url': apply_url,
            'posted_date': posted_date,
            'job_function': '',
            'experience_level': '',
            'salary_range': '',
            'remote_type': work_location,
            'status': 'active'
        }

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: scrape Microsoft jobs using Selenium DOM scraping with PCSX selectors."""
        driver = None
        all_jobs = []
        scraped_ids = set()
        page_size = 20  # DOM shows ~20 cards per page

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium DOM scraping")

            for page in range(max_pages):
                start = page * page_size
                page_url = f"{self.search_url}&start={start}"
                logger.info(f"Loading page {page + 1}: {page_url}")

                driver.get(page_url)

                # SPA rendering wait
                time.sleep(15)

                # Scroll to trigger lazy loading
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)

                logger.info(f"Page loaded: {driver.current_url}")

                # Extract job cards using JS with PCSX-specific selectors
                jobs = driver.execute_script("""
                    var results = [];
                    var cards = document.querySelectorAll('a[class*="card-"]');
                    for (var i = 0; i < cards.length; i++) {
                        var card = cards[i];
                        var href = card.href || '';
                        if (!href.includes('/careers/job/')) continue;

                        var title_el = card.querySelector('div[class*="title-"]');
                        var location_el = card.querySelector('div[class*="fieldValue-"]');
                        var date_el = card.querySelector('div[class*="subData-"]');

                        var title = title_el ? title_el.innerText.trim() : '';
                        if (!title) {
                            // Fallback: first line of card text
                            var text = card.innerText || '';
                            title = text.split('\\n')[0].trim();
                        }
                        if (!title || title.length < 3) continue;

                        results.push({
                            title: title,
                            location: location_el ? location_el.innerText.trim() : '',
                            posted_date: date_el ? date_el.innerText.trim() : '',
                            url: href,
                            job_id: href.split('/job/')[1] ? href.split('/job/')[1].split('?')[0] : ''
                        });
                    }
                    return results;
                """)

                if not jobs:
                    logger.warning(f"No job cards found on page {page + 1}")
                    # Try alternative selectors
                    jobs = driver.execute_script("""
                        var results = [];
                        var links = document.querySelectorAll('a[href*="/careers/job/"]');
                        for (var i = 0; i < links.length; i++) {
                            var link = links[i];
                            var text = (link.innerText || '').trim();
                            var href = link.href || '';
                            if (text.length < 3 || !href) continue;

                            var lines = text.split('\\n');
                            results.push({
                                title: lines[0].trim(),
                                location: lines.length > 1 ? lines[1].trim() : '',
                                posted_date: lines.length > 2 ? lines[2].trim() : '',
                                url: href,
                                job_id: href.split('/job/')[1] ? href.split('/job/')[1].split('?')[0] : ''
                            });
                        }
                        return results;
                    """)

                if not jobs:
                    logger.warning(f"No jobs found on page {page + 1} with any selector, stopping")
                    break

                new_count = 0
                for job in jobs:
                    job_id = job.get('job_id', '')
                    if not job_id:
                        job_id = f"ms_dom_{hashlib.md5(job['url'].encode()).hexdigest()[:12]}"

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue
                    scraped_ids.add(ext_id)

                    location = job.get('location', '') or 'India'
                    loc = self.parse_location(location)

                    all_jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': job['title'],
                        'description': '',
                        'location': location,
                        'city': loc.get('city', ''),
                        'state': loc.get('state', ''),
                        'country': loc.get('country', 'India'),
                        'employment_type': '',
                        'department': '',
                        'apply_url': job['url'],
                        'posted_date': job.get('posted_date', ''),
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
                    new_count += 1

                logger.info(f"Page {page + 1}: {new_count} new jobs (total: {len(all_jobs)})")

                if new_count == 0:
                    logger.info("No new jobs found, stopping pagination")
                    break

            logger.info(f"Total jobs scraped via Selenium DOM: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during Selenium DOM scraping: {str(e)}")
            logger.error(traceback.format_exc())
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

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


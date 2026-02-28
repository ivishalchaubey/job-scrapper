from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
from pathlib import Path
import os
import stat

try:
    import requests
except ImportError:
    requests = None

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('lgelectronics_scraper')

FRESH_CHROMEDRIVER = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class LGElectronicsScraper:
    def __init__(self):
        self.company_name = 'LG Electronics'
        # Eightfold AI platform (LG Corp / LG CNS)
        self.url = 'https://lgcns.eightfold.ai/careers'
        self.api_domain = 'lgcns.com'

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

        driver_path = FRESH_CHROMEDRIVER

        try:
            if os.path.exists(driver_path):
                try:
                    current_permissions = os.stat(driver_path).st_mode
                    os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except Exception as e:
                    logger.warning(f"Could not set permissions on chromedriver: {str(e)}")
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Service driver failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        # Primary method: Eightfold AI API via requests
        if requests is not None:
            try:
                api_jobs = self._scrape_via_api(max_pages)
                if api_jobs:
                    logger.info(f"API method returned {len(api_jobs)} jobs")
                    return api_jobs
                else:
                    logger.warning("API method returned 0 jobs (no India jobs currently available)")
                    # For LG, 0 India jobs is a valid state -- don't fall through to Selenium
                    # unless API itself failed. We confirmed via API the count is 0.
                    return api_jobs
            except Exception as e:
                logger.error(f"API method failed: {str(e)}, falling back to Selenium")
        else:
            logger.warning("requests library not available, using Selenium only")

        # Fallback: Selenium-based scraping
        return self._scrape_via_selenium(max_pages)

    def _scrape_via_api(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape LG Electronics jobs using Eightfold AI API directly."""
        all_jobs = []
        num_per_page = 10
        scraped_ids = set()

        api_url = 'https://lgcns.eightfold.ai/api/apply/v2/jobs'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://lgcns.eightfold.ai/careers',
        }

        # First try with India location filter
        start = 0
        page = 1
        total_count = None
        location_filter = 'India'

        while page <= max_pages:
            params = {
                'domain': self.api_domain,
                'location': location_filter,
                'sort_by': 'relevance',
                'num': num_per_page,
                'start': start,
            }

            logger.info(f"API request page {page}: start={start}, num={num_per_page}, location={location_filter}")

            try:
                response = requests.get(api_url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed at start={start}: {str(e)}")
                break
            except ValueError as e:
                logger.error(f"Failed to parse API JSON response: {str(e)}")
                break

            positions = data.get('positions', [])

            if total_count is None:
                total_count = data.get('count', 0)
                logger.info(f"Total jobs available for location={location_filter}: {total_count}")

            if not positions:
                logger.info(f"No positions returned at start={start}")
                break

            logger.info(f"API page {page}: received {len(positions)} positions")

            for pos in positions:
                try:
                    job_data = self._parse_api_position(pos)
                    if job_data and job_data['external_id'] not in scraped_ids:
                        all_jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                except Exception as e:
                    logger.error(f"Error parsing API position: {str(e)}")
                    continue

            # Check if we've fetched all available jobs
            start += len(positions)
            if total_count and start >= total_count:
                logger.info("Reached end of available jobs")
                break
            if len(positions) == 0:
                break

            page += 1

        logger.info(f"API total jobs scraped: {len(all_jobs)}")
        return all_jobs

    def _parse_api_position(self, pos):
        """Parse a single position from the Eightfold AI API response."""
        title = pos.get('name', '').strip()
        if not title:
            return None

        # Build job ID from the position id
        job_id = str(pos.get('id', ''))
        if not job_id:
            job_id = f"lg_api_{hashlib.md5(title.encode()).hexdigest()[:8]}"

        # Build the apply URL
        apply_url = pos.get('canonicalPositionUrl', '')
        if not apply_url:
            apply_url = f"https://lgcns.eightfold.ai/careers?pid={job_id}&domain={self.api_domain}"

        # Extract location
        location = pos.get('location', '')
        if isinstance(location, list) and location:
            location = location[0] if isinstance(location[0], str) else str(location[0])
        elif not isinstance(location, str):
            location = ''

        # Extract other fields
        department = pos.get('department', '') or pos.get('business_unit', '') or ''
        if isinstance(department, list) and department:
            department = department[0]

        employment_type = pos.get('type', '') or ''
        if isinstance(employment_type, list) and employment_type:
            employment_type = employment_type[0]

        description = pos.get('job_description', '') or pos.get('description', '') or ''
        if description:
            description = description[:3000]

        posted_date = pos.get('t_create', '') or ''

        experience_level = pos.get('experience', '') or pos.get('experience_level', '') or ''

        # Work location option
        remote_type = ''
        work_option = pos.get('work_location_option', '') or pos.get('location_flexibility', '') or ''
        if isinstance(work_option, str):
            if 'remote' in work_option.lower():
                remote_type = 'Remote'
            elif 'hybrid' in work_option.lower():
                remote_type = 'Hybrid'
            elif 'onsite' in work_option.lower() or 'on-site' in work_option.lower():
                remote_type = 'On-site'

        job_data = {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'company_name': self.company_name,
            'title': title,
            'apply_url': apply_url,
            'location': location,
            'department': str(department),
            'employment_type': str(employment_type),
            'description': description,
            'posted_date': str(posted_date),
            'city': '',
            'state': '',
            'country': 'India',
            'job_function': '',
            'experience_level': str(experience_level),
            'salary_range': '',
            'remote_type': remote_type,
            'status': 'active'
        }

        location_parts = self.parse_location(location)
        job_data.update(location_parts)

        return job_data

    def _scrape_via_selenium(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Fallback: Scrape LG Electronics jobs using Selenium with Eightfold AI selectors."""
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} Selenium scraping from {self.url}")

            # Load page with India filter
            driver.get(f"{self.url}?location=India")

            # Wait for page to render
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'div.position-card, [class*="position-card"]'
                    ))
                )
                logger.info("Position cards detected")
            except Exception as e:
                logger.warning(f"No position cards found: {str(e)}")
                # Check if "0 open jobs" message is shown
                try:
                    body_text = driver.execute_script("return document.body ? document.body.innerText.substring(0, 500) : ''")
                    if '0 open jobs' in body_text:
                        logger.info("Page confirms 0 open jobs in India")
                        return []
                except Exception:
                    pass
                time.sleep(5)

            # Click "Show More Positions" to load more jobs
            max_show_more_clicks = (max_pages - 1) * 2
            for click_num in range(max_show_more_clicks):
                try:
                    loaded = driver.execute_script("""
                        var btn = document.querySelector('.show-more-positions');
                        if (btn && btn.offsetParent !== null) {
                            btn.click();
                            return true;
                        }
                        return false;
                    """)
                    if not loaded:
                        break
                    time.sleep(1.5)
                except Exception:
                    break

            # Extract jobs from React fiber state
            scraped_ids = set()
            all_jobs = self._extract_jobs_from_react(driver, scraped_ids)

            if not all_jobs:
                all_jobs = self._extract_jobs_from_dom(driver, scraped_ids)

            logger.info(f"Total jobs scraped via Selenium: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during Selenium scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _extract_jobs_from_react(self, driver, scraped_ids):
        """Extract job data directly from React fiber props."""
        jobs = []
        try:
            js_results = driver.execute_script("""
                var cards = document.querySelectorAll('div.position-card.pointer');
                var results = [];
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var reactKey = Object.keys(card).find(function(k) {
                        return k.startsWith('__reactInternalInstance') || k.startsWith('__reactFiber');
                    });
                    if (!reactKey) continue;
                    try {
                        var fiber = card[reactKey];
                        var current = fiber;
                        for (var depth = 0; depth < 10; depth++) {
                            if (current && current.memoizedProps && current.memoizedProps.position) {
                                var pos = current.memoizedProps.position;
                                results.push({
                                    id: pos.id || '',
                                    name: pos.name || '',
                                    location: pos.location || '',
                                    department: pos.department || '',
                                    business_unit: pos.business_unit || '',
                                    type: pos.type || '',
                                    t_create: pos.t_create || '',
                                    job_description: (pos.job_description || '').substring(0, 3000),
                                    canonical: pos.canonicalPositionUrl || '',
                                    work_location_option: pos.work_location_option || ''
                                });
                                break;
                            }
                            if (current) current = current.return;
                            else break;
                        }
                    } catch(e) {}
                }
                return results;
            """)

            if js_results:
                logger.info(f"React extraction found {len(js_results)} positions")
                for pos in js_results:
                    try:
                        title = pos.get('name', '').strip()
                        if not title:
                            continue
                        job_id = str(pos.get('id', ''))
                        if not job_id:
                            job_id = f"lg_react_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                        ext_id = self.generate_external_id(job_id, self.company_name)
                        if ext_id in scraped_ids:
                            continue

                        apply_url = pos.get('canonical', '')
                        if not apply_url:
                            apply_url = f"https://lgcns.eightfold.ai/careers?pid={job_id}&domain={self.api_domain}"

                        location = pos.get('location', '')

                        remote_type = ''
                        work_option = pos.get('work_location_option', '')
                        if isinstance(work_option, str):
                            if 'remote' in work_option.lower():
                                remote_type = 'Remote'
                            elif 'hybrid' in work_option.lower():
                                remote_type = 'Hybrid'

                        job_data = {
                            'external_id': ext_id,
                            'company_name': self.company_name,
                            'title': title,
                            'apply_url': apply_url,
                            'location': location,
                            'department': pos.get('department', '') or pos.get('business_unit', ''),
                            'employment_type': pos.get('type', ''),
                            'description': pos.get('job_description', ''),
                            'posted_date': str(pos.get('t_create', '')),
                            'city': '',
                            'state': '',
                            'country': 'India',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        }

                        location_parts = self.parse_location(location)
                        job_data.update(location_parts)

                        jobs.append(job_data)
                        scraped_ids.add(ext_id)
                    except Exception as e:
                        logger.error(f"Error parsing React position: {str(e)}")
                        continue

        except Exception as e:
            logger.error(f"React extraction error: {str(e)}")

        return jobs

    def _extract_jobs_from_dom(self, driver, scraped_ids):
        """Fallback: Extract job data from DOM text content."""
        jobs = []
        try:
            js_results = driver.execute_script("""
                var cards = document.querySelectorAll('div.position-card.pointer');
                var results = [];
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var titleEl = card.querySelector('.position-title');
                    var locEl = card.querySelector('[class*="position-location"], [class*="location"]');
                    var title = titleEl ? titleEl.innerText.trim() : '';
                    var location = locEl ? locEl.innerText.trim() : '';
                    if (title) {
                        results.push({title: title, location: location});
                    }
                }
                return results;
            """)

            if js_results:
                logger.info(f"DOM extraction found {len(js_results)} cards")
                for idx, item in enumerate(js_results):
                    title = item.get('title', '').strip()
                    location = item.get('location', '').strip()
                    if not title:
                        continue

                    job_id = f"lg_dom_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue

                    job_data = {
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': self.url,
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

                    jobs.append(job_data)
                    scraped_ids.add(ext_id)

        except Exception as e:
            logger.error(f"DOM extraction error: {str(e)}")

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
    scraper = LGElectronicsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

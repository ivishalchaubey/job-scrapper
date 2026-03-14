from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import html
import json
import re
import subprocess
import time
import traceback
from pathlib import Path
from datetime import datetime
import os
import stat
from urllib.request import Request, urlopen

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE
from scrapers.csv_url_resolver import get_company_url

logger = setup_logger('microsoft_scraper')

class MicrosoftScraper:
    def __init__(self):
        self.company_name = "Microsoft"
        default_url = "https://apply.careers.microsoft.com/careers?location=India&hl=en"
        self.url = get_company_url(self.company_name, default_url)
        # Microsoft careers moved to Eightfold AI PCSX platform (Nov 2026)
        self.search_url = self.url
        self.pcsx_api_path = '/api/pcsx/search?domain=microsoft.com&query=&location=India&start={start}&hl=en'
        self.base_job_url = 'https://apply.careers.microsoft.com/careers/job'
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _clean_text(self, value):
        if not value:
            return ''
        text = html.unescape(value)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<li[^>]*>', '\n- ', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'[ \t\r\f\v]+', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        return text.strip()[:15000]

    def _fetch_text(self, url):
        try:
            request = Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                },
            )
            with urlopen(request, timeout=SCRAPE_TIMEOUT) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception:
            pass

        try:
            result = subprocess.run(
                ['curl', '-L', '-s', url],
                capture_output=True,
                text=True,
                timeout=SCRAPE_TIMEOUT,
                check=False,
            )
            if result.stdout:
                return result.stdout
        except Exception:
            pass

        return ''

    def _fetch_job_details_from_html(self, apply_url):
        details = {}
        page = self._fetch_text(apply_url)
        if not page:
            return details

        ld_match = re.search(
            r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
            page,
            flags=re.DOTALL,
        )
        if ld_match:
            try:
                payload = json.loads(ld_match.group(1))
                description = self._clean_text(payload.get('description', ''))
                if description:
                    details['description'] = description

                employment_type = payload.get('employmentType', '')
                if isinstance(employment_type, list):
                    employment_type = ', '.join([str(item) for item in employment_type if item])
                if employment_type:
                    details['employment_type'] = str(employment_type).replace('_', '-').title()
            except Exception:
                pass

        if not details.get('description'):
            meta_match = re.search(r'<meta name="description" content="([^"]+)"', page, flags=re.IGNORECASE)
            if meta_match:
                description = self._clean_text(meta_match.group(1))
                if description:
                    details['description'] = description

        return details

    def _fetch_job_details(self, driver, apply_url):
        details = {}
        original_window = None

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(apply_url)

            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '#pcsx, main, [role="main"]'))
            )

            # Ensure the job description tab content is rendered, not just the page shell.
            try:
                WebDriverWait(driver, 20).until(
                    lambda d: 'Overview' in d.find_element(By.TAG_NAME, 'body').text
                    or 'Responsibilities' in d.find_element(By.TAG_NAME, 'body').text
                )
            except Exception:
                try:
                    driver.execute_script("""
                        const candidates = Array.from(document.querySelectorAll('button,a,[role="tab"]'));
                        const tab = candidates.find(el => (el.innerText || '').trim() === 'Job description');
                        if (tab) tab.click();
                    """)
                    WebDriverWait(driver, 15).until(
                        lambda d: 'Overview' in d.find_element(By.TAG_NAME, 'body').text
                        or 'Responsibilities' in d.find_element(By.TAG_NAME, 'body').text
                    )
                except Exception:
                    time.sleep(2)

            page_text = driver.execute_script("""
                const root = document.querySelector('main,[role="main"],#pcsx') || document.body;
                return root ? root.innerText : '';
            """) or ''

            if page_text:
                start_idx = page_text.find('Overview')
                if start_idx == -1:
                    start_idx = page_text.find('Responsibilities')
                if start_idx != -1:
                    description = page_text[start_idx:]
                else:
                    description = page_text

                end_markers = [
                    '\nSimilar jobs',
                    '\nExplore other jobs',
                    '\nBenefits/perks',
                    '\nShare this job',
                    '\nYour Privacy Choices',
                    '\nEnglish (United States)',
                ]
                for marker in end_markers:
                    marker_idx = description.find(marker)
                    if marker_idx != -1:
                        description = description[:marker_idx]
                        break

                description = self._clean_text(description)
                if description:
                    details['description'] = description

            # Extract employment type from rendered detail fields if present.
            rendered_text = page_text or ''
            emp_match = re.search(r'Employment type\s+([^\n]+)', rendered_text)
            if emp_match:
                details['employment_type'] = emp_match.group(1).strip()

        except Exception as exc:
            logger.debug(f"Rendered Microsoft detail extraction failed for {apply_url}: {exc}")
        finally:
            try:
                if driver.current_window_handle != original_window:
                    driver.close()
                    driver.switch_to.window(original_window)
            except Exception:
                try:
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                except Exception:
                    pass

        if not details.get('description') or not details.get('employment_type'):
            fallback = self._fetch_job_details_from_html(apply_url)
            if fallback:
                details.update({k: v for k, v in fallback.items() if v and not details.get(k)})

        return details

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
            # Smart wait: return as soon as page content appears instead of blind sleep
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[class*="card-"], div[class*="position-card"], [class*="job"]'))
                )
                time.sleep(1)  # Brief settle for SPA to finish rendering
            except Exception:
                time.sleep(5)  # Fallback if selectors not found

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
                        job_data = self._parse_pcsx_position(pos, driver=driver)
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

    def _parse_pcsx_position(self, pos, driver=None):
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
            location = ''

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

        job_data = {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'job_id': job_id,
            'company_name': self.company_name,
            'title': name,
            'description': '',
            'location': location,
            'city': loc.get('city', ''),
            'state': loc.get('state', ''),
            'country': loc.get('country', ''),
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

        if driver is not None and apply_url:
            details = self._fetch_job_details(driver, apply_url)
            if details:
                job_data.update(details)

        return job_data

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

                # Smart wait: return as soon as job cards appear instead of blind sleep
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'a[class*="card-"], a[href*="/careers/job/"], div[class*="position-card"]'))
                    )
                    time.sleep(1)  # Brief settle for SPA rendering
                except Exception:
                    time.sleep(5)  # Fallback if selectors not found

                # Quick scroll to trigger lazy loading (single scroll instead of 3)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.5)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.3)

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

                    location = job.get('location', '') or ''
                    loc = self.parse_location(location)

                    job_data = {
                        'external_id': ext_id,
                        'job_id': job_id,
                        'company_name': self.company_name,
                        'title': job['title'],
                        'description': '',
                        'location': location,
                        'city': loc.get('city', ''),
                        'state': loc.get('state', ''),
                        'country': loc.get('country', ''),
                        'employment_type': '',
                        'department': '',
                        'apply_url': job['url'],
                        'posted_date': job.get('posted_date', ''),
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    if job['url']:
                        details = self._fetch_job_details(driver, job['url'])
                        if details:
                            job_data.update(details)

                    all_jobs.append(job_data)
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
        result = {'city': '', 'state': '', 'country': ''}
        if not location_str:
            return result

        location_str = location_str.strip()
        parts = [p.strip() for p in location_str.split(',')]

        if not parts:
            return result

        if parts[0].upper() in ('IN', 'IND', 'INDIA'):
            result['country'] = 'India'
            if len(parts) >= 2:
                result['city'] = parts[1]
            if len(parts) >= 3:
                result['state'] = parts[2]
            return result

        if len(parts) >= 4:
            result['city'] = parts[-2]
            if parts[-1].upper() in ('IN', 'IND', 'INDIA'):
                result['country'] = 'India'
            else:
                result['country'] = parts[-1]
        elif len(parts) == 3:
            result['city'] = parts[0]
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['city'] = parts[0]
            if parts[1].upper() in ('IN', 'IND', 'INDIA'):
                result['country'] = 'India'
            else:
                result['state'] = parts[1]
        else:
            result['city'] = parts[0]

        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'

        return result

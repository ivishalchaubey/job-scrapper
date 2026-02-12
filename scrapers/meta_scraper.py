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


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('meta_scraper')


class MetaScraper:
    def __init__(self):
        self.company_name = 'Meta'
        self.url = 'https://www.metacareers.com/jobs?offices[0]=Mumbai%2C%20India&offices[1]=Gurgaon%2C%20India&offices[2]=Bangalore%2C%20India'

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

        driver_path = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

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

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            driver.get(self.url)

            # SPA rendering wait - Meta's React app needs extra time to hydrate
            logger.info("Waiting 20s for SPA rendering...")
            time.sleep(20)

            # Log page state for debugging
            page_title = driver.title
            current_url = driver.current_url
            logger.info(f"Page title: {page_title}, URL: {current_url}")

            # Aggressive scrolling to trigger lazy loading of job cards
            for i in range(8):
                driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {(i + 1) / 8});")
                time.sleep(1.5)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Use JavaScript to extract all jobs from the page
            # Meta uses atomic CSS classes that change, so we target by href pattern
            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page/scroll {current_page}")

                jobs = self._extract_jobs_via_js(driver)
                new_jobs = [j for j in jobs if j['external_id'] not in {x['external_id'] for x in all_jobs}]
                all_jobs.extend(new_jobs)
                logger.info(f"Scroll {current_page}: found {len(new_jobs)} new jobs (total: {len(all_jobs)})")

                if current_page < max_pages:
                    # Count current job links before scrolling (broader patterns)
                    prev_count = driver.execute_script("""
                        var count = 0;
                        var links = document.querySelectorAll('a[href]');
                        for (var i = 0; i < links.length; i++) {
                            var href = links[i].href || '';
                            if (href.indexOf('/jobs/') !== -1 || href.indexOf('/job_details/') !== -1 ||
                                href.indexOf('/profile/job_details/') !== -1 || href.indexOf('/v2/jobs/') !== -1) {
                                count++;
                            }
                        }
                        return count;
                    """)
                    # Scroll down for more results
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(3)
                    # Click "Show more" / "See more jobs" button if present
                    try:
                        driver.execute_script("""
                            var buttons = document.querySelectorAll('button, a[role="button"], div[role="button"]');
                            for (var i = 0; i < buttons.length; i++) {
                                var text = (buttons[i].innerText || '').toLowerCase();
                                if (text.includes('show more') || text.includes('see more') ||
                                    text.includes('load more') || text.includes('view more')) {
                                    buttons[i].click();
                                    break;
                                }
                            }
                        """)
                        time.sleep(3)
                    except:
                        pass
                    new_count = driver.execute_script("""
                        var count = 0;
                        var links = document.querySelectorAll('a[href]');
                        for (var i = 0; i < links.length; i++) {
                            var href = links[i].href || '';
                            if (href.indexOf('/jobs/') !== -1 || href.indexOf('/job_details/') !== -1 ||
                                href.indexOf('/profile/job_details/') !== -1 || href.indexOf('/v2/jobs/') !== -1) {
                                count++;
                            }
                        }
                        return count;
                    """)
                    if new_count == prev_count:
                        logger.info("No more jobs to load after scrolling")
                        break

                current_page += 1

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _extract_jobs_via_js(self, driver):
        """Extract jobs using JavaScript to query the DOM directly.

        Meta uses atomic/hashed CSS classes that change between builds,
        so we rely on the stable href pattern: /profile/job_details/{id}

        The link text contains: Title\nLocation, Country\n(dot)Category1\n(dot)Category2
        """
        jobs = []
        scraped_ids = set()

        try:
            # Strategy 1: Known Meta job URL patterns (broader search)
            js_results = driver.execute_script("""
                var results = [];
                var seen = {};
                var links = document.querySelectorAll('a[href]');
                var patterns = ['/profile/job_details/', '/v2/jobs/', '/jobs/'];

                for (var i = 0; i < links.length; i++) {
                    var link = links[i];
                    var href = link.href || '';
                    if (!href || seen[href]) continue;

                    var isJobLink = false;
                    for (var p = 0; p < patterns.length; p++) {
                        if (href.indexOf(patterns[p]) !== -1) {
                            isJobLink = true;
                            break;
                        }
                    }
                    if (!isJobLink) continue;
                    seen[href] = true;

                    var fullText = (link.innerText || '').trim();
                    var heading = link.querySelector('h1, h2, h3, h4, h5, h6');
                    var title = '';
                    if (heading) {
                        title = (heading.innerText || heading.textContent || '').trim();
                    }
                    if (!title && fullText) {
                        title = fullText.split('\\n')[0].trim();
                    }
                    // Check parent for title if link has no text
                    if (!title) {
                        var parent = link.closest('div, li, article');
                        if (parent) {
                            var h = parent.querySelector('h1, h2, h3, h4, h5, h6');
                            if (h) title = (h.innerText || '').trim();
                        }
                    }

                    if (title && title.length > 2 && title.length < 300) {
                        results.push({
                            title: title,
                            url: href,
                            fullText: fullText || title
                        });
                    }
                }
                return results;
            """)

            if not js_results:
                logger.warning("Strategy 1 found 0 jobs. Trying metacareers.com numeric ID fallback...")
                # Strategy 2: Look for links with numeric IDs on metacareers.com
                js_results = driver.execute_script("""
                    var results = [];
                    var seen = {};
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var link = allLinks[i];
                        var href = link.href || '';
                        if (!href || seen[href]) continue;
                        if (href.indexOf('metacareers.com') === -1) continue;
                        // Check for numeric job ID in path
                        var pathParts = href.split('/');
                        var hasNumericId = false;
                        for (var j = 0; j < pathParts.length; j++) {
                            if (/^\\d{5,}$/.test(pathParts[j])) {
                                hasNumericId = true;
                                break;
                            }
                        }
                        if (!hasNumericId) continue;
                        seen[href] = true;
                        var fullText = (link.innerText || '').trim();
                        var title = fullText.split('\\n')[0].trim();
                        if (!title || title.length < 3) {
                            var parent = link.closest('div, li, article');
                            if (parent) {
                                var h = parent.querySelector('h1, h2, h3, h4, h5, h6');
                                if (h) title = (h.innerText || '').trim();
                            }
                        }
                        if (title && title.length > 3) {
                            results.push({
                                title: title,
                                url: href,
                                fullText: fullText || title
                            });
                        }
                    }
                    return results;
                """)

            if not js_results:
                logger.warning("Strategy 2 found 0 jobs. Trying deep DOM scan for job cards...")
                # Strategy 3: Look for list items with location text (job card-like elements)
                js_results = driver.execute_script("""
                    var results = [];
                    var seen = {};
                    var items = document.querySelectorAll('li, div[role="link"], [data-testid*="job"], [data-testid*="result"]');
                    var cities = ['Mumbai', 'Bangalore', 'Bengaluru', 'Gurgaon', 'Gurugram', 'India', 'Hyderabad', 'Delhi', 'Remote', 'Noida'];
                    for (var i = 0; i < items.length; i++) {
                        var elem = items[i];
                        var text = (elem.innerText || '').trim();
                        if (!text || text.length < 10 || text.length > 500) continue;
                        var lines = text.split('\\n').filter(function(l) { return l.trim().length > 0; });
                        if (lines.length < 2) continue;
                        var hasLocation = false;
                        for (var c = 0; c < cities.length; c++) {
                            if (text.indexOf(cities[c]) !== -1) { hasLocation = true; break; }
                        }
                        if (!hasLocation) continue;
                        var title = lines[0].trim();
                        if (title.length < 5 || title.length > 200) continue;
                        var lowerTitle = title.toLowerCase();
                        if (lowerTitle.includes('cookie') || lowerTitle.includes('privacy') || lowerTitle.includes('sign in')) continue;
                        var innerLink = elem.querySelector('a[href]');
                        var href = innerLink ? (innerLink.href || '') : '';
                        if (!href) {
                            var closestLink = elem.closest('a[href]');
                            href = closestLink ? (closestLink.href || '') : '';
                        }
                        if (seen[title]) continue;
                        seen[title] = true;
                        results.push({ title: title, url: href || '', fullText: text });
                    }
                    return results;
                """)

            if not js_results:
                logger.warning("All JS strategies found 0 job links on page")
                try:
                    body_text = driver.execute_script("return document.body ? document.body.innerText.substring(0, 1000) : '';")
                    logger.info(f"Page body preview: {body_text[:500]}")
                    link_count = driver.execute_script("return document.querySelectorAll('a').length;")
                    logger.info(f"Total links on page: {link_count}")
                except:
                    pass
                return jobs

            logger.info(f"JS extraction found {len(js_results)} job link elements")

            for item in js_results:
                try:
                    title = item.get('title', '').strip()
                    job_url = item.get('url', '').strip()
                    full_text = item.get('fullText', '').strip()

                    if not title or not job_url:
                        continue

                    # Extract job ID from URL (multiple patterns)
                    job_id = ""
                    url_patterns = ['/profile/job_details/', '/v2/jobs/', '/jobs/']
                    for pattern in url_patterns:
                        if pattern in job_url:
                            parts = job_url.split(pattern)[-1].split('/')
                            candidate = parts[0].split('?')[0].strip()
                            if candidate:
                                job_id = candidate
                                break
                    if not job_id and job_url:
                        # Try to find any numeric segment >= 5 digits
                        path_parts = job_url.split('/')
                        for part in path_parts:
                            cleaned = part.split('?')[0].strip()
                            if cleaned.isdigit() and len(cleaned) >= 5:
                                job_id = cleaned
                                break

                    if not job_id:
                        job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

                    if job_id in scraped_ids:
                        continue
                    scraped_ids.add(job_id)

                    # Parse location and department from full text
                    # Format: "Title\nLocation, Country\n(dot-sep)Category1\n(dot-sep)Category2"
                    location = ""
                    department = ""
                    lines = full_text.split('\n')
                    for line in lines[1:]:  # Skip the title line
                        line_s = line.strip()
                        if not line_s:
                            continue
                        # Location line typically contains a city/country
                        if any(city in line_s for city in ['Mumbai', 'Gurgaon', 'Bangalore', 'Hyderabad',
                                                           'New Delhi', 'India', 'Remote', 'Noida']):
                            # Clean up dot separators - location may have trailing category
                            # e.g. "Bangalore, India⋅Software Engineering"
                            for sep in ['\u22c5', '\u00b7', '\u2022', '\u2219']:
                                if sep in line_s:
                                    loc_parts = line_s.split(sep)
                                    line_s = loc_parts[0].strip()
                                    # Remaining parts are categories/departments
                                    if not department and len(loc_parts) > 1:
                                        department = loc_parts[1].strip()
                                    break
                            location = line_s
                        elif not department and line_s and len(line_s) < 80:
                            # This is likely a category/department line
                            # Clean leading dot separators
                            for sep in ['\u22c5', '\u00b7', '\u2022', '\u2219']:
                                line_s = line_s.lstrip(sep).strip()
                            if line_s and not line_s.startswith('http'):
                                department = line_s

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': job_url,
                        'location': location,
                        'department': department,
                        'employment_type': '',
                        'description': '',
                        'posted_date': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': 'Remote' if 'Remote' in full_text else '',
                        'status': 'active'
                    }

                    # Parse location into city/state/country
                    location_parts = self.parse_location(job_data.get('location', ''))
                    job_data.update(location_parts)

                    jobs.append(job_data)
                    logger.info(f"Extracted job {len(jobs)}: {title} | {location}")

                except Exception as e:
                    logger.error(f"Error processing job item: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error in JS extraction: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result

        location_str = location_str.strip()

        # Handle "+" notation like "Mumbai, India + 2 more"
        if '+' in location_str:
            location_str = location_str.split('+')[0].strip()

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
    scraper = MetaScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

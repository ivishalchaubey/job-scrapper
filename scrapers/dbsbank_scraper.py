from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from pathlib import Path


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('dbsbank_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class DBSBankScraper:
    def __init__(self):
        self.company_name = 'DBS Bank'
        self.url = 'https://www.dbs.com/careers/jobs.page?market=India'
        self.base_url = 'https://www.dbs.com'

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
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Auto-detect failed: {str(e)}, trying explicit path")
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
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

            # Step 1: Visit the main jobs page to get category links
            driver.get(self.url)
            time.sleep(15)

            # Extract category page URLs from the main page
            # Each category has 3 links: empty (image), category name, "N Jobs" text
            # We only want the one with the actual category name
            category_urls = driver.execute_script("""
                var urls = [];
                var seen = {};
                var links = document.querySelectorAll('a[href*="job-listing.page"][href*="market=India"]');
                for (var i = 0; i < links.length; i++) {
                    var href = links[i].href;
                    if (!href || !href.includes('category=')) continue;
                    var text = links[i].innerText.trim();
                    // Skip empty links, "N Jobs" / "N Job" links
                    if (!text || text.match(/^\\d+\\s+Jobs?$/i)) continue;
                    if (seen[href]) continue;
                    seen[href] = true;
                    urls.push({url: href, category: text});
                }
                return urls;
            """)

            if not category_urls:
                logger.warning("No category URLs found on main page, trying direct extraction")
                # Fallback: try to extract jobs from the main page itself
                page_jobs = self._extract_jobs_from_page(driver)
                all_jobs.extend(page_jobs)
            else:
                logger.info(f"Found {len(category_urls)} category pages to scrape")

                # Step 2: Visit each category page and extract jobs
                seen_job_ids = set()
                for cat_info in category_urls:
                    cat_url = cat_info.get('url', '')
                    cat_name = cat_info.get('category', 'Unknown')
                    if not cat_url:
                        continue

                    logger.info(f"Scraping category: {cat_name} - {cat_url}")
                    try:
                        driver.get(cat_url)
                        time.sleep(10)

                        # Click "Load More" button repeatedly to load all jobs
                        for load_attempt in range(50):  # Safety limit
                            try:
                                load_more_clicked = driver.execute_script("""
                                    var btn = document.querySelector('button.loadmore, button[class*="loadmore"]');
                                    if (btn && btn.offsetParent !== null) {
                                        btn.scrollIntoView();
                                        btn.click();
                                        return true;
                                    }
                                    return false;
                                """)
                                if not load_more_clicked:
                                    break
                                time.sleep(3)
                            except Exception:
                                break

                        # Scroll to ensure all content is visible
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)

                        page_jobs = self._extract_jobs_from_page(driver, department=cat_name)

                        # Deduplicate by job ID (WD number)
                        for job in page_jobs:
                            job_key = job.get('external_id', '')
                            if job_key and job_key not in seen_job_ids:
                                seen_job_ids.add(job_key)
                                all_jobs.append(job)
                            elif not job_key:
                                all_jobs.append(job)

                        logger.info(f"  Category '{cat_name}': {len(page_jobs)} jobs found (total unique: {len(all_jobs)})")
                    except Exception as e:
                        logger.error(f"Error scraping category {cat_name}: {str(e)}")
                        continue

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _extract_jobs_from_page(self, driver, department=''):
        """Extract job listings from a DBS category page."""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // DBS-specific: job cards are div.job with p.title, p.desc, p.post-date
                var jobCards = document.querySelectorAll('div.job');
                for (var i = 0; i < jobCards.length; i++) {
                    var card = jobCards[i];
                    var titleEl = card.querySelector('p.title');
                    var descEl = card.querySelector('p.desc');
                    var dateEl = card.querySelector('p.post-date');
                    var applyLink = card.querySelector('a[href*="taleo"], a.btn');

                    var title = titleEl ? titleEl.innerText.trim() : '';
                    if (!title || title.length < 3) continue;

                    var location = descEl ? descEl.innerText.trim() : '';
                    // Clean up location: replace bullet separators
                    location = location.replace(/\\s*●\\s*/g, ', ').replace(/^,\\s*/, '').replace(/,\\s*$/, '');

                    var date = dateEl ? dateEl.innerText.trim() : '';
                    // Clean up date: remove "Posting Date " prefix
                    date = date.replace(/^Posting Date\\s*/i, '');

                    var url = applyLink ? applyLink.href : '';
                    if (!url) continue;

                    // Extract WD job ID from Taleo URL or title
                    var jobId = '';
                    if (url.includes('job=')) {
                        jobId = url.split('job=')[1].split('&')[0];
                    }
                    if (!jobId) {
                        var match = title.match(/\\(([A-Z]{2}\\d+)\\)/);
                        if (match) jobId = match[1];
                    }

                    // Deduplicate by job ID or URL
                    var key = jobId || url;
                    if (seen[key]) continue;
                    seen[key] = true;

                    results.push({
                        title: title,
                        location: location,
                        url: url,
                        date: date,
                        jobId: jobId
                    });
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Extracted {len(js_jobs)} jobs from page")
                for jdata in js_jobs:
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    date = jdata.get('date', '').strip()
                    job_id = jdata.get('jobId', '').strip()

                    if not title or len(title) < 3:
                        continue

                    # Clean title: remove the (WD...) suffix for cleaner display
                    clean_title = title
                    if job_id and f'({job_id})' in clean_title:
                        clean_title = clean_title.replace(f'({job_id})', '').strip().rstrip(' -').strip()

                    if not job_id:
                        job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]

                    loc_data = self.parse_location(location)
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name, 'title': clean_title,
                        'apply_url': url or self.url, 'location': location,
                        'department': department, 'employment_type': '', 'description': '',
                        'posted_date': date, 'city': loc_data.get('city', ''),
                        'state': loc_data.get('state', ''),
                        'country': loc_data.get('country', 'India'),
                        'job_function': '', 'experience_level': '', 'salary_range': '',
                        'remote_type': '', 'status': 'active'
                    })

            if not jobs:
                logger.warning("No jobs found on this page")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error extracting jobs: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str: return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1: result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str: result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = DBSBankScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
                print(f"- {job['title']} | {job['location']}")

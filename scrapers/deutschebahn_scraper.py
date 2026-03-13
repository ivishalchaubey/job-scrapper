import requests
import hashlib
from bs4 import BeautifulSoup

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('deutschebahn_scraper')

class DeutscheBahnScraper:
    def __init__(self):
        self.company_name = "Deutsche Bahn"
        self.url = "https://db.jobs/service/search/en-en/5379744?query=International%20Jobs%20DB%20E.C.O.%20Group%20Deutsche%20bahn%20international%20operations%20gmbh&location_awe=&qli=true&sort=pubExternalDate_tdt"
        self.base_url = 'https://db.jobs'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        """Generate stable external ID."""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        """Parse location string into dict with city, state, country."""
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        location_str = location_str.strip()
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            if parts[1] in ['IN', 'IND', 'India']:
                result['country'] = 'India'
            else:
                result['state'] = parts[1]
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result

    def _is_india_job(self, metadata_text, location_text):
        """Check if a job is India-based from metadata and location text."""
        india_keywords = [
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
            'pune', 'hyderabad', 'noida', 'gurgaon', 'gurugram',
            'chennai', 'kolkata', 'jaipur', 'ahmedabad', 'lucknow',
            'new delhi'
        ]
        combined = f"{metadata_text} {location_text}".lower()
        return any(kw in combined for kw in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Deutsche Bahn CoreMedia CMS site."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            for page in range(max_pages):
                # Build URL with page parameter
                if page == 0:
                    url = self.url
                else:
                    # CoreMedia typically uses page parameter or offset in URL
                    url = f"{self.url}?page={page + 1}"

                logger.info(f"Fetching page {page + 1}: {url}")

                try:
                    response = requests.get(url, headers=self.headers, timeout=30)
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request failed on page {page + 1}: {str(e)}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # CoreMedia CMS: job listings are <a class="m-search-hit"> elements
                job_items = soup.select('a.m-search-hit')

                if not job_items:
                    # Fallback: look for wrapper divs containing search hits
                    wrappers = soup.select('div.o-searchpage__item--careers')
                    if wrappers:
                        job_items = []
                        for w in wrappers:
                            hit = w.select_one('a.m-search-hit')
                            if hit:
                                job_items.append(hit)

                if not job_items:
                    job_items = soup.select('[class*="search-hit"]')

                if not job_items:
                    logger.info(f"No job items found on page {page + 1}, stopping pagination")
                    break

                logger.info(f"Page {page + 1}: found {len(job_items)} job items")
                page_jobs = 0

                for item in job_items:
                    try:
                        # The item should be an <a> element directly
                        link = item if item.name == 'a' else item.select_one('a.m-search-hit')
                        if not link:
                            link = item.select_one('a[href]')
                        if not link:
                            continue

                        # Extract job ID from data attribute
                        job_id = link.get('data-job-id', '')

                        # Extract title from span.m-search-hit__title-text
                        title = ''
                        title_el = link.select_one('span.m-search-hit__title-text')
                        if title_el:
                            title = title_el.get_text(strip=True)
                        else:
                            title_h3 = link.select_one('h3.m-search-hit__title')
                            if title_h3:
                                title = title_h3.get_text(strip=True)

                        if not title:
                            continue

                        # Extract structured metadata from the bookmark button's JSON
                        # The button has @click with embedded JSON containing location, country, etc.
                        location = ''
                        department = ''
                        employment_type = ''
                        posted_date = ''
                        metadata_text = ''

                        # BeautifulSoup cannot use CSS selectors for Vue @click attrs;
                        # use find() with attrs dict instead
                        bookmark_btn = link.find('button', attrs={'@click': True})
                        if not bookmark_btn:
                            bookmark_btn = link.select_one('button')
                        if bookmark_btn:
                            click_attr = bookmark_btn.get('@click', '')
                            if click_attr:
                                import json as json_mod
                                # Extract JSON from the @click handler
                                json_match = None
                                try:
                                    # The @click value is like:
                                    # addToBookmarkListHandler(0, '{\n \"key\": ...}')
                                    # BS4 gives us literal \\n and \\" which need decoding
                                    # Extract the JSON substring between the first '{' and last '}'
                                    brace_start = click_attr.find('{')
                                    brace_end = click_attr.rfind('}')
                                    if brace_start >= 0 and brace_end > brace_start:
                                        json_str = click_attr[brace_start:brace_end + 1]
                                        # Decode the escaped characters
                                        json_str = json_str.replace('\\"', '"').replace('\\n', '\n')
                                        json_str = json_str.replace('&quot;', '"').replace('&amp;', '&')
                                        json_match = json_mod.loads(json_str)
                                except Exception:
                                    pass

                                if json_match:
                                    location = json_match.get('location', '')
                                    department = json_match.get('legalEntity', '')
                                    employment_type = json_match.get('fullPartTime', '')
                                    start_date = json_match.get('startDate', '')
                                    if start_date:
                                        posted_date = start_date
                                    metadata_text = f"{location} {json_match.get('country', '')}"

                        # Fallback: extract metadata from list items using icon aria-labels
                        if not location:
                            metadata_items = link.select('ul.m-search-hit__items li.m-search-hit__item')
                            for li in metadata_items:
                                text = li.get_text(strip=True)
                                metadata_text += ' ' + text
                                # Use icon aria-label to identify the field
                                icon = li.select_one('i[aria-label]')
                                aria = icon.get('aria-label', '').lower() if icon else ''
                                if aria == 'place of work' or (not location and not aria):
                                    location = text
                                elif aria == 'employer':
                                    department = text
                                elif 'entry date' in text.lower() or 'start' in aria:
                                    posted_date = text.replace('Entry date:', '').strip()

                        # Filter for India jobs
                        if not self._is_india_job(metadata_text, location):
                            continue

                        # Extract URL
                        href = link.get('href', '')
                        if href and href.startswith('/'):
                            href = self.base_url + href

                        # Generate job ID if not from data attribute
                        if not job_id:
                            job_id = hashlib.md5((href or title).encode()).hexdigest()[:12]

                        external_id = self.generate_external_id(job_id, self.company_name)
                        if external_id in seen_ids:
                            continue

                        location_parts = self.parse_location(location)

                        job_data = {
                            'external_id': external_id,
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': location_parts['city'],
                            'state': location_parts['state'],
                            'country': location_parts['country'],
                            'employment_type': employment_type,
                            'department': department,
                            'apply_url': href if href else self.url,
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }

                        all_jobs.append(job_data)
                        seen_ids.add(external_id)
                        page_jobs += 1
                        logger.info(f"Extracted: {title} | {location}")

                    except Exception as e:
                        logger.error(f"Error parsing job item: {str(e)}")
                        continue

                logger.info(f"Page {page + 1}: extracted {page_jobs} new jobs (total: {len(all_jobs)})")

                if page_jobs == 0:
                    logger.info("No new jobs found on this page, stopping")
                    break

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

if __name__ == "__main__":
    scraper = DeutscheBahnScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['apply_url']}")

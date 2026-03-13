import requests
import hashlib
from bs4 import BeautifulSoup

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('haptik_scraper')

class HaptikScraper:
    def __init__(self):
        self.company_name = "Haptik"
        self.url = "https://haptik.freshteam.com/jobs?__hstc=233858945.0eecb6901547789a76a8150b48139b47.1650872173205.1656650197197.1656654941825.85&__hssc=233858945.2.1656654941825&__hsfp=&hsCtaTracking=be1d0f38-8578-466c-a65e-7dba125d958a%7C852c3dbe-26c9-4a01-a174-ad02a06686d9&_gl=1*efxtfg*_gcl_au*Nzc1MDMyODQ4LjE3NzE1OTQwMTE.*_ga*ODU2MzA1MTQ2LjE3NzE1OTQwMTA.*_ga_TL7ZLD0W5B*czE3NzE1OTQwMDkkbzEkZzAkdDE3NzE1OTQwMDkkajYwJGwwJGgw"
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Haptik Freshteam career page."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Freshteam platform: a.heading with data attributes
            job_links = soup.select('a.heading[data-portal-title]')

            if not job_links:
                # Fallback: try broader selectors for Freshteam
                job_links = soup.select('a[data-portal-title]')

            if not job_links:
                # Broader fallback for Freshteam job listings
                job_links = soup.select('a[class*="heading"]')

            logger.info(f"Found {len(job_links)} job links on page")

            # Also try to get department info from section headers
            # Freshteam often groups jobs by department with h5 headers
            department_map = {}
            role_sections = soup.select('div[class*="role-title"], div[class*="department"]')
            for section in role_sections:
                dept_el = section.select_one('h5')
                if dept_el:
                    dept_name = dept_el.get_text(strip=True)
                    # Map all subsequent job links in this section
                    links_in_section = section.find_next_siblings('a', limit=50)
                    for link in links_in_section:
                        link_id = id(link)
                        department_map[link_id] = dept_name

            for link in job_links:
                try:
                    # Extract data from Freshteam data attributes
                    title = link.get('data-portal-title', '').strip()
                    location = link.get('data-portal-location', '').strip()
                    job_type = link.get('data-portal-job-type', '').strip()

                    if not title:
                        # Fallback to text content
                        title_el = link.select_one('div.job-title')
                        if title_el:
                            title = title_el.get_text(strip=True)
                        else:
                            title = link.get_text(strip=True)

                    if not title:
                        continue

                    # Extract location from data attribute or nested element
                    if not location:
                        loc_el = link.select_one('div.location-info, [class*="location"]')
                        if loc_el:
                            location = loc_el.get_text(strip=True)

                    # Extract department from nearby h5 or parent context
                    department = department_map.get(id(link), '')
                    if not department:
                        # Try parent or preceding sibling for department
                        parent = link.find_parent('div')
                        if parent:
                            dept_el = parent.select_one('h5')
                            if dept_el:
                                department = dept_el.get_text(strip=True)

                    # Extract URL
                    href = link.get('href', '')
                    if href and href.startswith('/'):
                        href = 'https://haptik.freshteam.com' + href

                    # Generate job ID from URL or title
                    if href and '/jobs/' in href:
                        # Extract numeric ID from Freshteam URL
                        parts = href.rstrip('/').split('/')
                        job_id = parts[-1] if parts else hashlib.md5(title.encode()).hexdigest()[:12]
                    else:
                        job_id = hashlib.md5((title + location).encode()).hexdigest()[:12]

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
                        'employment_type': job_type,
                        'department': department,
                        'apply_url': href if href else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    all_jobs.append(job_data)
                    seen_ids.add(external_id)
                    logger.info(f"Extracted: {title} | {location} | {department}")

                except Exception as e:
                    logger.error(f"Error parsing job link: {str(e)}")
                    continue

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

if __name__ == "__main__":
    scraper = HaptikScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

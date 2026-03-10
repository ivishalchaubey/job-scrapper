import requests
from bs4 import BeautifulSoup
import hashlib
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('fynd_scraper')


class FyndScraper:
    def __init__(self):
        self.company_name = "Fynd"
        self.careers_url = 'https://www.fynd.com/careers'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'

    def _is_india_location(self, location_str):
        """Check if a location string indicates India."""
        if not location_str:
            return False
        india_keywords = [
            'india', 'mumbai', 'bangalore', 'bengaluru', 'hyderabad',
            'chennai', 'delhi', 'pune', 'kolkata', 'gurgaon', 'gurugram',
            'noida', 'ahmedabad', 'new delhi'
        ]
        location_lower = location_str.lower()
        return any(keyword in location_lower for keyword in india_keywords)

    def _scrape_careers_page(self):
        """Scrape the Fynd careers page directly.
        The page at fynd.com/careers is Webflow-powered, and the open positions
        section is rendered server-side as Webflow CMS dynamic content.
        """
        jobs = []
        try:
            # Fetch the careers/roles page which has Webflow CMS items
            urls_to_try = [
                'https://www.fynd.com/careers',
                'https://careers.fynd.com/roles-at-fynd',
            ]

            for url in urls_to_try:
                logger.info(f"Fetching: {url}")
                try:
                    response = self.session.get(url, timeout=30, allow_redirects=True)
                    response.raise_for_status()
                except Exception as e:
                    logger.warning(f"Failed to fetch {url}: {e}")
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Look for job/role cards - Webflow CMS items typically have w-dyn-item class
                # or specific role/job card classes
                job_cards = soup.select('.w-dyn-item')

                # Filter out non-job dynamic items (like announcement bars)
                job_cards = [card for card in job_cards
                             if not card.select_one('.announcement-bar, .announcement-wrapper')]

                # Also try looking for job-specific containers
                if not job_cards:
                    job_cards = soup.select('[class*="role-card"], [class*="job-card"], [class*="opening-card"], [class*="position-card"]')

                # Try links to individual job/role pages
                if not job_cards:
                    role_links = soup.select('a[href*="/roles/"], a[href*="/jobs/"], a[href*="/openings/"]')
                    for link in role_links:
                        title = link.get_text(strip=True)
                        href = link.get('href', '')
                        if title and len(title) > 3 and href:
                            if href.startswith('/'):
                                href = f"https://www.fynd.com{href}"
                            job_id = hashlib.md5(href.encode()).hexdigest()[:12]
                            jobs.append({
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name,
                                'title': title,
                                'description': '',
                                'location': 'Mumbai, India',
                                'city': 'Mumbai',
                                'state': 'Maharashtra',
                                'country': 'India',
                                'employment_type': '',
                                'department': '',
                                'apply_url': href,
                                'posted_date': '',
                                'job_function': '',
                                'experience_level': '',
                                'salary_range': '',
                                'remote_type': '',
                                'status': 'active'
                            })

                logger.info(f"Found {len(job_cards)} job card elements on {url}")

                for card in job_cards:
                    try:
                        # Title from heading or link
                        title_el = card.select_one('h1, h2, h3, h4, h5, [class*="title"], [class*="heading"]')
                        if not title_el:
                            title_el = card.find('a')
                        title = title_el.get_text(strip=True) if title_el else ''
                        if not title or len(title) < 3:
                            continue

                        # Link
                        link = card.select_one('a[href]')
                        href = ''
                        if link:
                            href = link.get('href', '')
                            if href.startswith('/'):
                                href = f"https://www.fynd.com{href}"

                        # Location
                        location = ''
                        loc_el = card.select_one('[class*="location"], [class*="place"], [class*="city"]')
                        if loc_el:
                            location = loc_el.get_text(strip=True)

                        # Department
                        department = ''
                        dept_el = card.select_one('[class*="department"], [class*="team"], [class*="category"]')
                        if dept_el:
                            department = dept_el.get_text(strip=True)

                        if not location:
                            location = 'Mumbai, India'

                        if 'india' not in location.lower():
                            location = f"{location}, India"

                        city, state, country = self.parse_location(location)

                        job_id = hashlib.md5((href or title).encode()).hexdigest()[:12]

                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city if city else 'Mumbai',
                            'state': state if state else 'Maharashtra',
                            'country': 'India',
                            'employment_type': '',
                            'department': department,
                            'apply_url': href or url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })
                        logger.info(f"Extracted: {title} | {location}")
                    except Exception as e:
                        logger.warning(f"Error parsing card: {e}")
                        continue

                if jobs:
                    break

        except Exception as e:
            logger.error(f"Error scraping careers page: {e}")
        return jobs

    def _scrape_smartrecruiters(self, max_pages):
        """Try SmartRecruiters API as fallback (company slug: Fynd1)."""
        jobs = []
        url = 'https://api.smartrecruiters.com/v1/companies/Fynd1/postings'
        limit = 100
        offset = 0
        page = 0

        while page < max_pages:
            params = {'limit': limit, 'offset': offset}
            logger.info(f"SmartRecruiters: Fetching page {page + 1} (offset={offset})")
            try:
                response = self.session.get(url, params=params, timeout=30,
                                            headers={'Accept': 'application/json'})
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.warning(f"SmartRecruiters API error: {e}")
                break

            content = data.get('content', [])
            if not content:
                break

            for job_data in content:
                try:
                    job_id = job_data.get('id', '')
                    title = job_data.get('name', '').strip()
                    if not title:
                        continue

                    location_obj = job_data.get('location', {})
                    country_code = location_obj.get('country', '')

                    # Filter for India
                    if country_code and country_code.lower() not in ('in', 'ind', 'india'):
                        continue

                    city_name = location_obj.get('city', '')
                    region = location_obj.get('region', '')
                    location_parts = [p for p in [city_name, region] if p]
                    location = ', '.join(location_parts) + ', India' if location_parts else 'India'

                    dept_obj = job_data.get('department', {})
                    department = dept_obj.get('label', '') if dept_obj else ''

                    apply_url = f"https://careers.smartrecruiters.com/Fynd1/{job_id}" if job_id else url

                    posted_date = job_data.get('releasedDate', '') or job_data.get('createdOn', '')

                    employment_type = ''
                    type_of_emp = job_data.get('typeOfEmployment')
                    if isinstance(type_of_emp, dict):
                        employment_type = type_of_emp.get('label', '')

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city_name,
                        'state': region,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': apply_url,
                        'posted_date': posted_date,
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': 'Remote' if location_obj.get('remote') else '',
                        'status': 'active'
                    })
                except Exception as e:
                    logger.warning(f"Error parsing SR job: {e}")
                    continue

            if len(content) < limit:
                break
            offset += limit
            page += 1

        return jobs

    def _scrape_wellfound(self):
        """Scrape Fynd jobs from Wellfound (AngelList) as a fallback source."""
        jobs = []
        try:
            url = 'https://wellfound.com/company/gofynd/jobs'
            logger.info(f"Fetching Wellfound: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for job listings
            job_links = soup.select('a[href*="/jobs/"]')
            seen = set()
            for link in job_links:
                href = link.get('href', '')
                if '/jobs/' not in href or href in seen:
                    continue
                seen.add(href)

                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                if href.startswith('/'):
                    href = f"https://wellfound.com{href}"

                job_id = hashlib.md5(href.encode()).hexdigest()[:12]
                jobs.append({
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': 'Mumbai, India',
                    'city': 'Mumbai',
                    'state': 'Maharashtra',
                    'country': 'India',
                    'employment_type': '',
                    'department': '',
                    'apply_url': href,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                })
        except Exception as e:
            logger.warning(f"Wellfound scrape failed: {e}")
        return jobs

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Fynd jobs using multiple sources with fallback.

        Strategy:
        1. Try scraping the Webflow-powered careers page at fynd.com/careers
        2. Try SmartRecruiters API (Fynd1 slug) - filters for India
        3. Fall back to Wellfound (AngelList) as last resort
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")

            # Strategy 1: Scrape the Fynd careers page
            jobs = self._scrape_careers_page()
            if jobs:
                logger.info(f"Got {len(jobs)} jobs from careers page")
                return jobs

            # Strategy 2: SmartRecruiters API
            jobs = self._scrape_smartrecruiters(max_pages)
            if jobs:
                logger.info(f"Got {len(jobs)} jobs from SmartRecruiters")
                return jobs

            # Strategy 3: Wellfound (AngelList)
            jobs = self._scrape_wellfound()
            if jobs:
                logger.info(f"Got {len(jobs)} jobs from Wellfound")
                return jobs

            logger.warning(f"No jobs found for {self.company_name} from any source")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs


if __name__ == "__main__":
    scraper = FyndScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

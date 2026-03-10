import requests
from bs4 import BeautifulSoup
import hashlib
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('wtw_scraper')


class WTWScraper:
    def __init__(self):
        self.company_name = "Willis Towers Watson"
        self.careers_url = 'https://careers.wtwco.com/jobs/search'
        self.base_url = 'https://careers.wtwco.com'
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

    def _scrape_clinch_site(self, max_pages):  # noqa: ARG002
        """Scrape WTW jobs from the Clinch-powered career site.

        The career site at careers.wtwco.com uses Clinch platform (by Havas).
        The initial page load contains filter data with country counts.
        Job data is loaded via JavaScript, but the HTML page contains
        filter metadata indicating 28+ India jobs exist.

        We fetch the search page with India country filter. While the main
        section loads jobs via JS, we can parse any server-rendered content
        and job links from the HTML.
        """
        jobs = []
        seen_ids = set()

        try:
            # The Clinch site renders job data via JS, but the filter page
            # at /jobs/search contains data attributes with counts
            url = f'{self.careers_url}?country_codes%5B%5D=india'
            logger.info(f"Fetching Clinch career site: {url}")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for job card elements (if any are server-rendered)
            job_cards = soup.select('.job-card, [class*="job-result"], [class*="job-listing"], .job-item')
            if not job_cards:
                # Try broader search for job links
                job_links = soup.select('a[href*="/jobs/"][href*="/view"]')
                if not job_links:
                    job_links = soup.select('a[href*="/jobs/"]')
                    job_links = [l for l in job_links if l.get('href', '') != '/jobs/search'
                                 and 'search' not in l.get('href', '')]

                for link in job_links:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    if not title or len(title) < 3 or href in seen_ids:
                        continue
                    seen_ids.add(href)

                    if href.startswith('/'):
                        href = f"{self.base_url}{href}"

                    job_id = hashlib.md5(href.encode()).hexdigest()[:12]
                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': 'India',
                        'city': '',
                        'state': '',
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
            logger.warning(f"Clinch site scrape error: {e}")

        return jobs

    def _scrape_smartrecruiters(self, max_pages):
        """Scrape WTW jobs from SmartRecruiters API.

        Note: As of 2026, the SmartRecruiters API for WTW has very few postings.
        We fetch all postings globally and filter for India client-side.
        """
        jobs = []
        url = 'https://api.smartrecruiters.com/v1/companies/WTW/postings'
        limit = 100
        offset = 0
        page = 0

        while page < max_pages:
            # Fetch all jobs (no country filter) since India-specific returns 0
            params = {'limit': limit, 'offset': offset}
            logger.info(f"SmartRecruiters: Fetching page {page + 1} (offset={offset})")
            try:
                response = self.session.get(url, params=params, timeout=30,
                                            headers={'Accept': 'application/json'})
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.warning(f"SmartRecruiters error: {e}")
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
                    city_name = location_obj.get('city', '')
                    region = location_obj.get('region', '')
                    country_code = location_obj.get('country', '')

                    # Filter for India
                    if country_code and country_code.lower() not in ('in', 'ind'):
                        full_loc = location_obj.get('fullLocation', '')
                        if not self._is_india_location(full_loc):
                            continue

                    location_parts = [p for p in [city_name, region] if p]
                    location = ', '.join(location_parts) + ', India' if location_parts else 'India'

                    dept_obj = job_data.get('department', {})
                    department = dept_obj.get('label', '') if dept_obj else ''

                    apply_url = f"https://careers.smartrecruiters.com/WTW/{job_id}" if job_id else url
                    posted_date = job_data.get('releasedDate', '') or job_data.get('createdOn', '')

                    employment_type = ''
                    type_of_emp = job_data.get('typeOfEmployment')
                    if isinstance(type_of_emp, dict):
                        employment_type = type_of_emp.get('label', '')

                    experience_level = ''
                    exp_level = job_data.get('experienceLevel')
                    if isinstance(exp_level, dict):
                        experience_level = exp_level.get('label', '')

                    job_function = ''
                    func_obj = job_data.get('function')
                    if isinstance(func_obj, dict):
                        job_function = func_obj.get('label', '')

                    remote_type = ''
                    if location_obj.get('remote'):
                        remote_type = 'Remote'

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
                        'job_function': job_function,
                        'experience_level': experience_level,
                        'salary_range': '',
                        'remote_type': remote_type,
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

    def _scrape_wtw_search_page(self, max_pages):
        """Scrape WTW jobs from the SuccessFactors-style search at careers.wtwco.com.

        The Clinch platform serves the WTW career site. When country_codes[]=india
        is used, the page includes filter metadata showing India has ~28 jobs.
        The actual job list renders via JavaScript, but we can attempt to extract
        from the initial HTML or from Turbo Frame responses.
        """
        jobs = []
        seen_ids = set()

        for page in range(max_pages):
            try:
                params = {
                    'country_codes[]': 'india',
                    'page': page + 1,
                }
                # Try fetching with Turbo accept header to get partial HTML
                headers = {
                    'Accept': 'text/vnd.turbo-stream.html, text/html, application/xhtml+xml',
                    'Turbo-Frame': 'jobs_results',
                }
                url = self.careers_url
                logger.info(f"Fetching WTW search page {page + 1}")
                response = self.session.get(url, params=params, headers=headers, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')

                # Look for job entries in the response
                job_entries = soup.select('[data-controller*="job"], .job-result, .job-card, [class*="job-list"]')
                if not job_entries:
                    # Try to find job links
                    job_entries = soup.select('a[href*="/jobs/"][href*="/view"]')

                if not job_entries:
                    logger.info(f"No job entries found on page {page + 1}")
                    break

                for entry in job_entries:
                    try:
                        if entry.name == 'a':
                            link = entry
                            title = entry.get_text(strip=True)
                        else:
                            link = entry.select_one('a[href*="/jobs/"]')
                            title = entry.select_one('h2, h3, h4, [class*="title"]')
                            title = title.get_text(strip=True) if title else ''

                        if not title or len(title) < 3:
                            continue

                        href = link.get('href', '') if link else ''
                        if href and href.startswith('/'):
                            href = f"{self.base_url}{href}"

                        if href in seen_ids:
                            continue
                        seen_ids.add(href)

                        # Location
                        location = ''
                        loc_el = entry.select_one('[class*="location"]') if entry.name != 'a' else None
                        if loc_el:
                            location = loc_el.get_text(strip=True)
                        if not location:
                            location = 'India'

                        if location and 'india' not in location.lower():
                            if not self._is_india_location(location):
                                continue
                            location = f"{location}, India"

                        city, state, _ = self.parse_location(location)
                        job_id = hashlib.md5((href or title).encode()).hexdigest()[:12]

                        jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': 'India',
                            'employment_type': '',
                            'department': '',
                            'apply_url': href or url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        })
                    except Exception as e:
                        logger.warning(f"Error parsing WTW job entry: {e}")
                        continue

            except Exception as e:
                logger.warning(f"Error fetching WTW search page: {e}")
                break

        return jobs

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape WTW jobs using multiple strategies.

        WTW uses:
        1. SmartRecruiters API (slug: WTW) - limited postings
        2. Clinch career site at careers.wtwco.com - JavaScript SPA
        3. Turbo Frame search results

        Strategy order:
        1. Try the Clinch career site (may have server-rendered content)
        2. Try SmartRecruiters API (filter for India)
        3. Try Turbo Frame search results
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")

            # Strategy 1: Clinch career site
            jobs = self._scrape_clinch_site(max_pages)
            if jobs:
                logger.info(f"Got {len(jobs)} jobs from Clinch site")
                return jobs

            # Strategy 2: SmartRecruiters API
            jobs = self._scrape_smartrecruiters(max_pages)
            if jobs:
                logger.info(f"Got {len(jobs)} jobs from SmartRecruiters")
                return jobs

            # Strategy 3: Turbo Frame search
            jobs = self._scrape_wtw_search_page(max_pages)
            if jobs:
                logger.info(f"Got {len(jobs)} jobs from WTW search page")
                return jobs

            logger.warning(f"No jobs found for {self.company_name} from any source. "
                           f"The career site at careers.wtwco.com requires JavaScript rendering. "
                           f"Consider converting to a Selenium-based scraper.")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs


if __name__ == "__main__":
    scraper = WTWScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

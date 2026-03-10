import requests
from bs4 import BeautifulSoup
import hashlib
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('axtria_scraper')


class AxtriaScraper:
    def __init__(self):
        self.company_name = "Axtria"
        self.url = "https://www.axtria.com/axtria-careers/"
        self.base_url = 'https://axtriainc.applytojob.com'
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
        """Check if a location indicates India."""
        if not location_str:
            return False
        india_keywords = [
            'india', 'mumbai', 'bangalore', 'bengaluru', 'hyderabad',
            'chennai', 'delhi', 'pune', 'kolkata', 'gurgaon', 'gurugram',
            'noida', 'ahmedabad', 'new delhi', 'navi mumbai', 'thane',
            'ghaziabad', 'faridabad', 'greater noida'
        ]
        location_lower = location_str.lower()
        return any(keyword in location_lower for keyword in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            seen_ids = set()

            # JazzHR hosted job board - fetch the main job listing page
            logger.info(f"Fetching job listings from {self.url}")
            try:
                response = self.session.get(self.url, timeout=30)
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Failed to fetch job listings: {str(e)}")
                return jobs

            soup = BeautifulSoup(response.text, 'html.parser')

            # Strategy 1: JazzHR standard job list selectors
            job_items = soup.select('.jhr-opening, .jhr-job-listing, .job-listing')

            # Strategy 2: Look for job link items in standard JazzHR markup
            if not job_items:
                job_items = soup.select('div.job-opening, div.opening, li.job-item')

            # Strategy 3: Look for links to job detail pages (JazzHR pattern)
            if not job_items:
                job_links = soup.select('a[href*="/apply/"], a[href*="/job/"], a[href*="/jobs/"]')
                # Wrap links in containers for uniform processing
                job_items = []
                for link in job_links:
                    parent = link.find_parent(['div', 'li', 'tr', 'article'])
                    if parent and parent not in job_items:
                        job_items.append(parent)
                    elif not parent:
                        job_items.append(link)

            # Strategy 4: Try JazzHR API endpoint
            if not job_items:
                logger.info("Trying JazzHR API endpoint for job data")
                try:
                    api_url = f"{self.base_url}/api/jobs"
                    api_response = self.session.get(api_url, timeout=30)
                    if api_response.status_code == 200:
                        try:
                            api_data = api_response.json()
                            if isinstance(api_data, list):
                                for jd in api_data:
                                    self._process_api_job(jd, jobs, seen_ids)
                            elif isinstance(api_data, dict):
                                for jd in api_data.get('jobs', []) or api_data.get('results', []) or api_data.get('data', []):
                                    self._process_api_job(jd, jobs, seen_ids)
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"API endpoint failed: {str(e)}")

            # Strategy 5: Look for embedded JSON data in script tags
            if not job_items and not jobs:
                import json
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and ('jobs' in script.string or 'openings' in script.string or 'positions' in script.string):
                        try:
                            text = script.string
                            # Look for JSON data structures
                            for pattern in ['var jobs = ', 'var openings = ', '"jobs":', '"openings":']:
                                if pattern in text:
                                    start = text.index(pattern) + len(pattern)
                                    remaining = text[start:].strip()
                                    if remaining.startswith('['):
                                        bracket_count = 0
                                        end = 0
                                        for i, ch in enumerate(remaining):
                                            if ch == '[':
                                                bracket_count += 1
                                            elif ch == ']':
                                                bracket_count -= 1
                                                if bracket_count == 0:
                                                    end = i + 1
                                                    break
                                        if end > 0:
                                            json_str = remaining[:end]
                                            embedded_jobs = json.loads(json_str)
                                            for ej in embedded_jobs:
                                                self._process_api_job(ej, jobs, seen_ids)
                        except (json.JSONDecodeError, ValueError, IndexError):
                            continue

            logger.info(f"Found {len(job_items)} job elements in HTML")

            for item in job_items:
                try:
                    # Handle direct link elements
                    if item.name == 'a':
                        link = item
                        title = item.get_text(strip=True).split('\n')[0].strip()
                    else:
                        # Title
                        title_el = item.select_one('a.jhr-opening-link, h3, h4, h2, a[href*="/apply/"], .job-title, [class*="title"]')
                        title = title_el.get_text(strip=True) if title_el else ''
                        link = item.find('a', href=True)

                    if not title or len(title) < 3:
                        continue

                    # URL
                    job_url = ''
                    if link:
                        href = link.get('href', '')
                        if href.startswith('/'):
                            job_url = f"{self.base_url}{href}"
                        elif href.startswith('http'):
                            job_url = href

                    # Job ID
                    job_id = ''
                    if job_url:
                        url_parts = job_url.rstrip('/').split('/')
                        for part in reversed(url_parts):
                            if part and len(part) > 5 and not part.startswith('apply'):
                                job_id = part
                                break
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    # Location
                    location = ''
                    loc_el = item.select_one('.jhr-opening-location, .job-location, [class*="location"]')
                    if loc_el:
                        location = loc_el.get_text(strip=True)

                    if not location:
                        # Try extracting from the item text
                        item_text = item.get_text(separator='|', strip=True)
                        parts = item_text.split('|')
                        for part in parts:
                            part = part.strip()
                            if part != title and self._is_india_location(part):
                                location = part
                                break

                    # Filter for India
                    if location and not self._is_india_location(location):
                        continue

                    if not location:
                        location = 'India'

                    # Department
                    department = ''
                    dept_el = item.select_one('.jhr-opening-department, .job-department, [class*="department"], [class*="team"]')
                    if dept_el:
                        department = dept_el.get_text(strip=True)

                    city, state, country = self.parse_location(location)

                    if location and 'india' not in location.lower():
                        location = f"{location}, India"

                    # Remote type
                    remote_type = ''
                    if 'remote' in title.lower() or 'remote' in location.lower():
                        remote_type = 'Remote'
                    elif 'hybrid' in title.lower() or 'hybrid' in location.lower():
                        remote_type = 'Hybrid'

                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': '',
                        'department': department,
                        'apply_url': job_url or self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': remote_type,
                        'status': 'active'
                    }
                    jobs.append(job)
                    logger.info(f"Extracted: {title} | {location} | {department}")
                except Exception as e:
                    logger.warning(f"Error parsing job item: {str(e)}")
                    continue

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs

    def _process_api_job(self, job_data, jobs, seen_ids):
        """Process a job from API/embedded JSON data."""
        try:
            title = job_data.get('title', '') or job_data.get('name', '')
            if not title:
                return

            job_id = str(job_data.get('id', '')) or job_data.get('board_code', '') or job_data.get('jobId', '')
            if not job_id:
                job_id = hashlib.md5(title.encode()).hexdigest()[:12]

            if job_id in seen_ids:
                return
            seen_ids.add(job_id)

            # Location
            location = ''
            loc_data = job_data.get('location', '')
            if isinstance(loc_data, dict):
                city = loc_data.get('city', '') or loc_data.get('name', '')
                state = loc_data.get('state', '') or loc_data.get('region', '')
                country = loc_data.get('country', '')
                location_parts = [p for p in [city, state, country] if p]
                location = ', '.join(location_parts) if location_parts else ''
            elif isinstance(loc_data, str):
                location = loc_data
                city, state, _ = self.parse_location(location)
            else:
                city = job_data.get('city', '')
                state = job_data.get('state', '')
                location_parts = [p for p in [city, state] if p]
                location = ', '.join(location_parts) if location_parts else ''

            # Filter for India
            if location and not self._is_india_location(location):
                return

            if not location:
                location = 'India'
            elif 'india' not in location.lower():
                location = f"{location}, India"

            if not isinstance(loc_data, dict):
                city, state, _ = self.parse_location(location)

            apply_url = job_data.get('url', '') or job_data.get('apply_url', '') or job_data.get('hosted_url', '') or self.url
            department = job_data.get('department', '') or job_data.get('team', '')
            if isinstance(department, dict):
                department = department.get('name', '') or department.get('label', '')
            employment_type = job_data.get('type', '') or job_data.get('employment_type', '')

            job = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'description': '',
                'location': location,
                'city': city if isinstance(city, str) else '',
                'state': state if isinstance(state, str) else '',
                'country': 'India',
                'employment_type': employment_type if isinstance(employment_type, str) else '',
                'department': department if isinstance(department, str) else '',
                'apply_url': apply_url,
                'posted_date': job_data.get('created_at', '') or job_data.get('datePosted', '') or '',
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': 'Remote' if 'remote' in title.lower() else '',
                'status': 'active'
            }
            jobs.append(job)
            logger.info(f"API Extracted: {title} | {location}")
        except Exception as e:
            logger.warning(f"Error processing API job: {str(e)}")


if __name__ == "__main__":
    scraper = AxtriaScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

import requests
from bs4 import BeautifulSoup
import hashlib
import re
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('rpggroup_scraper')


class RPGGroupScraper:
    def __init__(self):
        self.company_name = "RPG Group"
        self.url = "https://jobs.rpggroup.com/search/?createNewAlert=false&q="
        self.base_url = 'https://jobs.rpggroup.com'
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

    def _extract_job_id(self, job_url):
        """Extract job ID from a SuccessFactors URL like /job/Mumbai-.../12345/"""
        job_id = ''
        if '/job/' in job_url:
            parts = job_url.rstrip('/').split('/')
            for part in reversed(parts):
                if part.isdigit():
                    job_id = part
                    break
        if not job_id:
            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]
        return job_id

    def _extract_location_from_url(self, job_url):
        """Extract location from SuccessFactors URL path like /job/Mumbai-Some-Title-IN/..."""
        location = ''
        if '/job/' in job_url:
            try:
                path_part = job_url.split('/job/')[1].split('/')[0]
                # First segment before the first dash that looks like a city
                city_match = path_part.split('-')[0]
                if city_match and len(city_match) > 2:
                    location = city_match
            except (IndexError, AttributeError):
                pass
        return location

    def _is_india_location(self, location_str):
        """Check if a location indicates India."""
        if not location_str:
            return True  # Assume India for RPG Group (India-based company)
        india_keywords = [
            'india', 'in', 'mumbai', 'bangalore', 'bengaluru', 'hyderabad',
            'chennai', 'delhi', 'pune', 'kolkata', 'gurgaon', 'gurugram',
            'noida', 'ahmedabad', 'jaipur', 'lucknow', 'chandigarh',
            'kochi', 'thiruvananthapuram', 'coimbatore', 'nagpur', 'indore',
            'bhopal', 'vadodara', 'surat', 'rajkot', 'goa', 'nasik',
            'nashik', 'navi mumbai', 'thane', 'visakhapatnam'
        ]
        location_lower = location_str.lower().strip()
        return any(keyword in location_lower for keyword in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            per_page = 25
            seen_ids = set()

            for page in range(max_pages):
                offset = page * per_page
                params = {
                    'createNewAlert': 'false',
                    'q': '',
                    'sortColumn': 'referencedate',
                    'sortDirection': 'desc',
                    'startrow': offset,
                }

                logger.info(f"Fetching page {page + 1} (startrow={offset})")
                try:
                    response = self.session.get(self.url, params=params, timeout=30)
                    response.raise_for_status()
                except Exception as e:
                    logger.error(f"Failed to fetch page {page + 1}: {str(e)}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # Strategy 1: Find job rows in the search results table
                job_rows = soup.select('table#searchresults tr.data-row, table#searchresults tr[class*="data"]')

                # Strategy 2: Try broader selectors
                if not job_rows:
                    job_rows = soup.select('table.searchResults tr')
                    # Filter out header rows
                    job_rows = [row for row in job_rows if row.find('a', class_='jobTitle-link') or row.find('span', class_='jobTitle')]

                # Strategy 3: Find all job title links
                if not job_rows:
                    title_links = soup.select('a.jobTitle-link, span.jobTitle a')
                    job_rows = []
                    for link in title_links:
                        parent_row = link.find_parent('tr')
                        if parent_row:
                            job_rows.append(parent_row)

                if not job_rows:
                    logger.info(f"No job rows found on page {page + 1}, stopping pagination")
                    break

                page_count = 0
                for row in job_rows:
                    try:
                        # Title and URL
                        title_link = row.select_one('span.jobTitle a.jobTitle-link, a.jobTitle-link, span.jobTitle a')
                        if not title_link:
                            title_link = row.find('a', href=lambda h: h and '/job/' in h)
                        if not title_link:
                            continue

                        title = title_link.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue

                        href = title_link.get('href', '')
                        if href and href.startswith('/'):
                            job_url = f"{self.base_url}{href}"
                        elif href and href.startswith('http'):
                            job_url = href
                        else:
                            job_url = self.url

                        # Job ID
                        job_id = self._extract_job_id(job_url)
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        # Location
                        location = ''
                        loc_el = row.select_one('span.jobLocation')
                        if loc_el:
                            location = loc_el.get_text(strip=True)

                        if not location:
                            location = self._extract_location_from_url(job_url)

                        # Filter for India
                        if location and not self._is_india_location(location):
                            continue

                        # Department
                        department = ''
                        dept_el = row.select_one('span.jobDepartment')
                        if dept_el:
                            department = dept_el.get_text(strip=True)

                        if not department:
                            facility_el = row.select_one('span.jobFacility')
                            if facility_el:
                                department = facility_el.get_text(strip=True)

                        # Posted date
                        posted_date = ''
                        date_el = row.select_one('span.jobDate')
                        if date_el:
                            posted_date = date_el.get_text(strip=True)

                        # Employment type / Shift type
                        employment_type = ''
                        shift_el = row.select_one('span.jobShifttype')
                        if shift_el:
                            employment_type = shift_el.get_text(strip=True)

                        city, state, country = self.parse_location(location)

                        if location and 'india' not in location.lower():
                            location = f"{location}, India"
                        elif not location:
                            location = 'India'

                        job = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': 'India',
                            'employment_type': employment_type,
                            'department': department,
                            'apply_url': job_url,
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        jobs.append(job)
                        page_count += 1
                        logger.info(f"Extracted: {title} | {location} | {department}")
                    except Exception as e:
                        logger.warning(f"Error parsing job row: {str(e)}")
                        continue

                logger.info(f"Page {page + 1}: found {page_count} jobs (total: {len(jobs)})")

                if page_count == 0:
                    logger.info("No new jobs found on this page, stopping pagination")
                    break

                # Check if there are more pages
                if page_count < per_page:
                    logger.info("Fewer than 25 results on this page, likely last page")
                    break

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs


if __name__ == "__main__":
    scraper = RPGGroupScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

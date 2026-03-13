import re
import requests
from bs4 import BeautifulSoup
import hashlib
from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import MAX_PAGES_TO_SCRAPE, HEADLESS_MODE

logger = setup_logger('ametek_scraper')

class AmetekScraper:
    def __init__(self):
        self.company_name = "Ametek"
        self.url = "https://jobs.ametek.com/search/?q=&q2=&alertId=&title=&location=IN&date=#searchresults"
        self.base_url = 'https://jobs.ametek.com'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

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
        """Extract job ID from a SuccessFactors URL like /job/Bangalore-.../12345/"""
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
        """Extract location from SuccessFactors URL path like /job/Bangalore-Title-IN/..."""
        location = ''
        if '/job/' in job_url:
            try:
                path_part = job_url.split('/job/')[1].split('/')[0]
                city_match = path_part.split('-')[0]
                if city_match and len(city_match) > 2:
                    location = city_match
            except (IndexError, AttributeError):
                pass
        return location

    def _is_us_location(self, location_str):
        """Check if a location is in the US (particularly US-Indiana, not India).

        SuccessFactors location format: "City, StateCode, CountryCode, ZipCode"
        - India jobs:       "Bangalore, KA, IN, 560048"  (IN = country)
        - US-Indiana jobs:  "Pierceton, IN, US, 46562"   (IN = state, US = country)

        Key indicators of US location:
        1. Contains ", US," or ends with ", US"
        2. Contains a 5-digit US zip code after country code
        3. The location parts have US country code at position 3
        """
        if not location_str:
            return False

        location_upper = location_str.upper().strip()

        # Check for explicit ", US," or ", US" at end
        if ', US,' in location_upper or location_upper.endswith(', US'):
            return True

        # Check for ", USA" or ", UNITED STATES"
        if ', USA' in location_upper or 'UNITED STATES' in location_upper:
            return True

        # Parse comma-separated parts
        # India format:  "City, State, IN, Pincode"  (IN is 3rd part = country)
        # US-IN format:  "City, IN, US, Zipcode"     (IN is 2nd part = state)
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 3:
            # If 3rd part is "US" or "USA", it's a US job
            if parts[2].strip().upper() in ('US', 'USA'):
                return True

        # Check for US zip code pattern (5 digits, optionally followed by -4 digits)
        if re.search(r'\b\d{5}(-\d{4})?\b', location_str):
            # Also verify that this isn't an Indian pincode
            # Indian pincodes are 6 digits, US zips are 5
            # But some SuccessFactors entries have spaces in Indian pincodes like "600 002"
            if len(parts) >= 3 and parts[2].strip().upper() == 'IN':
                # IN is in 3rd position = country code India, not US
                return False
            if len(parts) >= 3 and parts[2].strip().upper() in ('US', 'USA'):
                return True

        return False

    def _is_india_location(self, location_str):
        """Check if a location is genuinely in India (not US-Indiana).

        Uses positive matching for known Indian cities and the location format
        from SuccessFactors where IN appears as country code (3rd position).
        """
        if not location_str:
            return False

        # First, rule out US locations
        if self._is_us_location(location_str):
            return False

        location_lower = location_str.lower()

        # Check for known Indian cities
        india_cities = [
            'bangalore', 'bengaluru', 'mumbai', 'delhi', 'new delhi',
            'hyderabad', 'chennai', 'pune', 'kolkata', 'gurgaon',
            'gurugram', 'noida', 'ahmedabad', 'jaipur', 'lucknow',
            'chandigarh', 'indore', 'bhopal', 'coimbatore', 'kochi',
            'thiruvananthapuram', 'visakhapatnam', 'nagpur', 'surat',
            'vadodara', 'mysore', 'mysuru', 'mangalore', 'mangaluru',
        ]
        if any(city in location_lower for city in india_cities):
            return True

        # Check for explicit India mention
        if 'india' in location_lower:
            return True

        # Check location format: "City, StateCode, IN, Pincode"
        # where IN in 3rd position (index 2) means country code India
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 3:
            country_part = parts[2].strip().upper()
            if country_part == 'IN':
                # IN in 3rd position = India country code
                # Verify it's not followed by US indicators
                if len(parts) >= 4:
                    # Check if the 4th part looks like an Indian pincode (6 digits)
                    pincode = parts[3].strip().replace(' ', '')
                    if len(pincode) == 6 and pincode.isdigit():
                        return True
                    # Could still be India even without proper pincode
                    return True
                return True

        # "Virtual, IN" - could be India virtual location
        if len(parts) == 2 and parts[1].strip().upper() == 'IN':
            # Ambiguous - could be Indiana or India. Check context.
            # For Ametek, "Virtual, IN" is ambiguous. Include it.
            return True

        return False

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Ametek India jobs from the SuccessFactors career site.

        IMPORTANT: The location parameter 'IN' matches both India (country code)
        and US-Indiana (state abbreviation). We must filter out US jobs
        post-extraction by examining the full location string.

        Location format from SuccessFactors:
        - India:       "Bangalore, KA, IN, 560048" (City, State, CountryCode, Pincode)
        - US-Indiana:  "Pierceton, IN, US, 46562"  (City, StateCode, CountryCode, Zip)
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            per_page = 25
            seen_ids = set()

            for page in range(max_pages):
                offset = page * per_page
                params = {
                    'q': '',
                    'location': 'IN',
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
                    job_rows = [row for row in job_rows if row.find('a', class_='jobTitle-link') or row.find('span', class_='jobTitle')]

                # Strategy 3: Find all job title links directly
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
                skipped_us = 0
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

                        # CRITICAL: Filter out US-Indiana jobs
                        # The 'IN' location parameter matches both India and US-Indiana
                        if self._is_us_location(location):
                            skipped_us += 1
                            logger.debug(f"Skipped US job: {title} | {location}")
                            continue

                        # Verify it's actually an India location
                        if location and not self._is_india_location(location):
                            # Unknown location - log and skip to be safe
                            logger.debug(f"Skipped non-India job: {title} | {location}")
                            skipped_us += 1
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

                logger.info(f"Page {page + 1}: found {page_count} India jobs, "
                            f"skipped {skipped_us} US jobs (total: {len(jobs)})")

                if page_count == 0 and skipped_us == 0:
                    logger.info("No jobs found on this page, stopping pagination")
                    break

                # Check if there are more pages (fewer results than page size)
                total_on_page = page_count + skipped_us
                if total_on_page < per_page:
                    logger.info("Fewer than 25 results on this page, likely last page")
                    break

            logger.info(f"Successfully scraped {len(jobs)} India jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs

if __name__ == "__main__":
    scraper = AmetekScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

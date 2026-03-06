import requests
from bs4 import BeautifulSoup
import hashlib
import re
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('bloomberg_scraper')


class BloombergScraper:
    def __init__(self):
        self.company_name = 'Bloomberg'
        self.url = 'https://bloomberg.avature.net/careers/SearchJobs/'
        self.base_url = 'https://bloomberg.avature.net'
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

    def _extract_job_id_from_url(self, job_url):
        """Extract job ID from an Avature URL like /careers/JobDetail/12345"""
        job_id = ''
        # Avature URLs often look like /careers/JobDetail/12345 or ?jobId=12345
        match = re.search(r'JobDetail[/\?](\d+)', job_url, re.IGNORECASE)
        if match:
            job_id = match.group(1)
        if not job_id:
            match = re.search(r'jobId=(\d+)', job_url)
            if match:
                job_id = match.group(1)
        if not job_id:
            # Try extracting any numeric ID from the URL
            parts = job_url.rstrip('/').split('/')
            for part in reversed(parts):
                if part.isdigit():
                    job_id = part
                    break
        if not job_id:
            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]
        return job_id

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Bloomberg India jobs from the Avature career site.

        Bloomberg uses Avature (server-rendered HTML) for their career portal at
        bloomberg.avature.net. The search page supports filtering by location IDs:
        - 1845=[162477,162478,162575] (India location filter IDs)
        - 1845_format=3996 (format parameter)
        - listFilterMode=1 (filter mode)
        - jobRecordsPerPage=25 (results per page)

        Pagination uses jobOffset=0, jobOffset=25, etc.

        Job elements are typically:
        - a[href*="JobDetail"] for job links
        - Title text within the link or adjacent heading
        - Location in nearby spans/divs
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            per_page = 25
            seen_ids = set()

            for page in range(max_pages):
                offset = page * per_page
                params = {
                    '1845': '162477,162478,162575',
                    '1845_format': '3996',
                    'listFilterMode': '1',
                    'jobRecordsPerPage': str(per_page),
                    'jobOffset': str(offset),
                }

                logger.info(f"Fetching page {page + 1} (jobOffset={offset})")
                try:
                    response = self.session.get(self.url, params=params, timeout=30)
                    response.raise_for_status()
                except Exception as e:
                    logger.error(f"Failed to fetch page {page + 1}: {str(e)}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # Strategy 1: Find job links with JobDetail in the href (Avature standard)
                job_links = soup.select('a[href*="JobDetail"]')

                # Strategy 2: Look for search result containers
                job_containers = []
                if job_links:
                    # Wrap links in their parent containers for context
                    for link in job_links:
                        parent = link.find_parent(['div', 'li', 'tr', 'article', 'section'])
                        if parent and parent not in job_containers:
                            job_containers.append(parent)
                        elif not parent:
                            job_containers.append(link)
                else:
                    # Try generic Avature selectors
                    job_containers = soup.select(
                        '[class*="search-result"], [class*="searchResult"], '
                        '[class*="job-result"], [class*="jobResult"], '
                        '[class*="job-listing"], [class*="job-card"], '
                        '.article-item, .list-item'
                    )

                # Strategy 3: Find any links with /careers/ paths that look like job detail pages
                if not job_containers:
                    all_links = soup.select('a[href*="/careers/"]')
                    for link in all_links:
                        href = link.get('href', '')
                        # Skip navigation/filter links
                        if 'SearchJobs' in href or 'Login' in href or '#' == href:
                            continue
                        title_text = link.get_text(strip=True)
                        if title_text and len(title_text) > 3 and len(title_text) < 200:
                            parent = link.find_parent(['div', 'li', 'tr', 'article'])
                            if parent and parent not in job_containers:
                                job_containers.append(parent)
                            elif not parent:
                                job_containers.append(link)

                if not job_containers:
                    logger.info(f"No job elements found on page {page + 1}, stopping pagination")
                    break

                page_count = 0
                for container in job_containers:
                    try:
                        # Find the job link
                        if container.name == 'a':
                            title_link = container
                        else:
                            title_link = container.select_one('a[href*="JobDetail"]')
                            if not title_link:
                                title_link = container.select_one('a[href*="/careers/"]')
                            if not title_link:
                                title_link = container.select_one('h2 a, h3 a, h4 a, a')

                        if not title_link:
                            continue

                        # Extract title
                        title = ''
                        # Try heading elements first
                        heading = container.select_one('h2, h3, h4, [class*="title"], [class*="Title"]')
                        if heading:
                            title = heading.get_text(strip=True)
                        if not title:
                            title = title_link.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue

                        # Clean title - remove "Apply" or "View" button text
                        title = title.split('\n')[0].strip()
                        if title.lower() in ('apply', 'view', 'read more', 'learn more'):
                            continue

                        # Extract URL
                        href = title_link.get('href', '')
                        if href and href.startswith('/'):
                            job_url = f"{self.base_url}{href}"
                        elif href and href.startswith('http'):
                            job_url = href
                        else:
                            continue

                        # Skip if URL is just a search page
                        if 'SearchJobs' in job_url and 'JobDetail' not in job_url:
                            continue

                        # Job ID
                        job_id = self._extract_job_id_from_url(job_url)
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        # Location
                        location = ''
                        loc_el = container.select_one(
                            '[class*="location"], [class*="Location"], '
                            'span[class*="loc"], div[class*="loc"]'
                        )
                        if loc_el:
                            location = loc_el.get_text(strip=True)

                        # If no location element found, look in the full text
                        if not location:
                            text = container.get_text(' ', strip=True)
                            india_cities = [
                                'Mumbai', 'Bangalore', 'Bengaluru', 'Delhi', 'New Delhi',
                                'Hyderabad', 'Chennai', 'Pune', 'Kolkata', 'Gurugram',
                                'Gurgaon', 'Noida', 'Ahmedabad', 'India'
                            ]
                            for city_name in india_cities:
                                if city_name in text:
                                    location = city_name
                                    break

                        # Department
                        department = ''
                        dept_el = container.select_one(
                            '[class*="department"], [class*="Department"], '
                            '[class*="category"], [class*="Category"]'
                        )
                        if dept_el:
                            department = dept_el.get_text(strip=True)

                        # Posted date
                        posted_date = ''
                        date_el = container.select_one(
                            '[class*="date"], [class*="Date"], '
                            '[class*="posted"], time'
                        )
                        if date_el:
                            posted_date = date_el.get_text(strip=True)
                            if not posted_date and date_el.get('datetime'):
                                posted_date = date_el.get('datetime', '')[:10]

                        city, state, country = self.parse_location(location)

                        if location and 'india' not in location.lower():
                            location = f"{location}, India"
                        elif not location:
                            location = 'India'

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
                            'apply_url': job_url,
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        }
                        jobs.append(job)
                        page_count += 1
                        logger.info(f"Extracted: {title} | {location} | {department}")
                    except Exception as e:
                        logger.warning(f"Error parsing job element: {str(e)}")
                        continue

                logger.info(f"Page {page + 1}: found {page_count} jobs (total: {len(jobs)})")

                if page_count == 0:
                    logger.info("No new jobs found on this page, stopping pagination")
                    break

                if page_count < per_page:
                    logger.info("Fewer results than page size, likely last page")
                    break

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs


if __name__ == "__main__":
    scraper = BloombergScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

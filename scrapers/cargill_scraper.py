import requests
from bs4 import BeautifulSoup
import hashlib
import re
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('cargill_scraper')


class CargillScraper:
    def __init__(self):
        self.company_name = 'Cargill'
        self.url = 'https://careers.cargill.com/en/search-jobs'
        self.base_url = 'https://careers.cargill.com'
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
            'noida', 'ahmedabad', 'navi mumbai', 'thane', 'indore',
            'goa', 'bhopal', 'lucknow', 'chandigarh', 'coimbatore',
            'nagpur', 'jaipur', 'kochi', 'surat', 'vadodara',
        ]
        location_lower = location_str.lower()
        return any(keyword in location_lower for keyword in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            seen_ids = set()

            # Radancy TalentBrew URLs - try India-specific patterns
            # TalentBrew uses URL patterns like /search-jobs/results?Country=India or numeric location codes
            urls_to_try = [
                # India location filter patterns used by Radancy
                f"{self.url}/India/891/2/1269750/22/79/50/2",
                f"{self.url}?flcountry=India",
                f"{self.url}/results?Country=India",
                f"{self.url}?k=&l=India",
                self.url,
            ]

            for page_idx, fetch_url in enumerate(urls_to_try):
                if page_idx >= max_pages:
                    break

                logger.info(f"Fetching: {fetch_url}")
                try:
                    response = self.session.get(fetch_url, timeout=30)
                    response.raise_for_status()
                except Exception as e:
                    logger.warning(f"Failed to fetch {fetch_url}: {str(e)}")
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Strategy 1: Radancy TalentBrew standard selectors
                job_items = soup.select('a[data-job-id]')

                # Strategy 2: Search results section
                if not job_items:
                    results_section = soup.select_one('section#search-results-list, #search-results-list')
                    if results_section:
                        job_items = results_section.select('li, a[href*="/job/"], a[href*="/en/"]')

                # Strategy 3: Job listing links
                if not job_items:
                    job_items = soup.select('a[href*="/en/job/"], a[href*="/job/"], li[class*="job"]')

                # Strategy 4: Generic job card patterns
                if not job_items:
                    job_items = soup.select('[class*="job-result"], [class*="search-result"] li, .job-list li')

                # Strategy 5: Look for embedded JSON data (TalentBrew often embeds data)
                if not job_items:
                    import json
                    scripts = soup.find_all('script')
                    for script in scripts:
                        if script.string and ('phApp.d498' in script.string or 'SearchPage' in script.string or 'jobResults' in script.string or 'data-results' in script.string):
                            try:
                                text = script.string
                                # Try to extract JSON job data
                                for pattern in ['"jobs":', '"results":', '"data":', '"JobData":']:
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
                                                    self._process_embedded_job(ej, jobs, seen_ids)
                            except (json.JSONDecodeError, ValueError, IndexError):
                                continue

                    # Also try JSON-LD structured data
                    ld_scripts = soup.find_all('script', type='application/ld+json')
                    for script in ld_scripts:
                        try:
                            ld_data = json.loads(script.string)
                            if isinstance(ld_data, dict) and ld_data.get('@type') == 'JobPosting':
                                self._process_jsonld_job(ld_data, jobs, seen_ids)
                            elif isinstance(ld_data, list):
                                for item in ld_data:
                                    if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                                        self._process_jsonld_job(item, jobs, seen_ids)
                        except (json.JSONDecodeError, TypeError):
                            continue

                logger.info(f"Found {len(job_items)} job elements")

                for item in job_items:
                    try:
                        # Handle different element types
                        if item.name == 'a':
                            link = item
                            # Title from inner elements or text
                            title_el = item.find(['h2', 'h3', 'h4', 'span'])
                            title = title_el.get_text(strip=True) if title_el else item.get_text(strip=True).split('\n')[0].strip()
                        elif item.name == 'li':
                            link = item.find('a', href=True)
                            title_el = item.find(['h2', 'h3', 'h4', '.job-title', 'a'])
                            title = title_el.get_text(strip=True) if title_el else ''
                        else:
                            link = item.find('a', href=True) or item
                            title_el = item.find(['h2', 'h3', 'h4'])
                            title = title_el.get_text(strip=True) if title_el else item.get_text(strip=True).split('\n')[0].strip()

                        if not title or len(title) < 3:
                            continue

                        # URL
                        job_url = ''
                        if link and link.name == 'a':
                            href = link.get('href', '')
                            if href.startswith('/'):
                                job_url = f"{self.base_url}{href}"
                            elif href.startswith('http'):
                                job_url = href

                        # Job ID - from data attribute or URL
                        job_id = ''
                        if item.name == 'a':
                            job_id = item.get('data-job-id', '')
                        if not job_id and link:
                            job_id = link.get('data-job-id', '')
                        if not job_id and job_url:
                            url_parts = job_url.rstrip('/').split('/')
                            for part in reversed(url_parts):
                                if part.isdigit():
                                    job_id = part
                                    break
                        if not job_id:
                            job_id = hashlib.md5((job_url or title).encode()).hexdigest()[:12]

                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        # Location
                        location = ''
                        loc_el = item.select_one('span.job-location, .job-location, [class*="location"]')
                        if loc_el:
                            location = loc_el.get_text(strip=True)

                        if not location:
                            # Try parent element
                            parent = item.find_parent(['li', 'div'])
                            if parent:
                                loc_el = parent.select_one('span.job-location, [class*="location"]')
                                if loc_el:
                                    location = loc_el.get_text(strip=True)

                        # Filter for India
                        if location and not self._is_india_location(location):
                            # If on India-filtered URL, include anyway (might be malformed)
                            if 'india' not in fetch_url.lower() and '1269750' not in fetch_url:
                                continue

                        if not location:
                            location = 'India'

                        # Department
                        department = ''
                        dept_el = item.select_one('[class*="department"], [class*="category"]')
                        if dept_el:
                            department = dept_el.get_text(strip=True)

                        # Date
                        posted_date = ''
                        date_el = item.select_one('[class*="date"], time')
                        if date_el:
                            posted_date = date_el.get_text(strip=True) or date_el.get('datetime', '')

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
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        }
                        jobs.append(job)
                        logger.info(f"Extracted: {title} | {location}")
                    except Exception as e:
                        logger.warning(f"Error parsing job item: {str(e)}")
                        continue

                # If we found jobs, stop trying other URL patterns
                if jobs:
                    # Try pagination within TalentBrew
                    for extra_page in range(1, max_pages - page_idx):
                        next_url = f"{fetch_url}?page={extra_page + 1}"
                        # Radancy also uses /page/N pattern
                        if '/page/' not in fetch_url:
                            alt_next = re.sub(r'/2$', f'/{extra_page + 1}', fetch_url) if fetch_url.endswith('/2') else f"{fetch_url}/page/{extra_page + 1}"

                        logger.info(f"Trying pagination: {next_url}")
                        try:
                            next_response = self.session.get(next_url, timeout=30)
                            if next_response.status_code == 200:
                                next_soup = BeautifulSoup(next_response.text, 'html.parser')
                                next_items = next_soup.select('a[data-job-id], section#search-results-list li a[href*="/job/"]')
                                if not next_items:
                                    break
                                page_count = 0
                                for ni in next_items:
                                    # Simplified extraction for pagination pages
                                    t_el = ni.find(['h2', 'h3', 'h4', 'span'])
                                    t = t_el.get_text(strip=True) if t_el else ni.get_text(strip=True).split('\n')[0].strip()
                                    if not t or len(t) < 3:
                                        continue
                                    jid = ni.get('data-job-id', '') or hashlib.md5(t.encode()).hexdigest()[:12]
                                    if jid in seen_ids:
                                        continue
                                    seen_ids.add(jid)
                                    href = ni.get('href', '')
                                    jurl = f"{self.base_url}{href}" if href.startswith('/') else href
                                    loc_el = ni.select_one('span.job-location, [class*="location"]')
                                    loc = loc_el.get_text(strip=True) if loc_el else 'India'
                                    c, s, _ = self.parse_location(loc)
                                    if loc and 'india' not in loc.lower():
                                        loc = f"{loc}, India"
                                    jobs.append({
                                        'external_id': self.generate_external_id(jid, self.company_name),
                                        'company_name': self.company_name,
                                        'title': t,
                                        'description': '',
                                        'location': loc,
                                        'city': c,
                                        'state': s,
                                        'country': 'India',
                                        'employment_type': '',
                                        'department': '',
                                        'apply_url': jurl or self.url,
                                        'posted_date': '',
                                        'job_function': '',
                                        'experience_level': '',
                                        'salary_range': '',
                                        'remote_type': '',
                                        'status': 'active'
                                    })
                                    page_count += 1
                                logger.info(f"Pagination page {extra_page + 1}: {page_count} jobs (total: {len(jobs)})")
                                if page_count == 0:
                                    break
                        except Exception as e:
                            logger.warning(f"Pagination failed: {str(e)}")
                            break
                    break

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs

    def _process_embedded_job(self, job_data, jobs, seen_ids):
        """Process an embedded JSON job object."""
        try:
            title = job_data.get('Title', '') or job_data.get('title', '') or job_data.get('name', '')
            if not title:
                return

            job_id = str(job_data.get('Id', '') or job_data.get('id', '') or job_data.get('jobId', ''))
            if not job_id:
                job_id = hashlib.md5(title.encode()).hexdigest()[:12]

            if job_id in seen_ids:
                return
            seen_ids.add(job_id)

            location = job_data.get('Location', '') or job_data.get('location', '') or job_data.get('city', '')
            if isinstance(location, dict):
                location = location.get('name', '') or location.get('city', '')

            if location and not self._is_india_location(location):
                return

            if not location:
                location = 'India'
            elif 'india' not in location.lower():
                location = f"{location}, India"

            city, state, _ = self.parse_location(location)
            apply_url = job_data.get('Url', '') or job_data.get('url', '') or job_data.get('apply_url', '')
            if apply_url and apply_url.startswith('/'):
                apply_url = f"{self.base_url}{apply_url}"

            department = job_data.get('Department', '') or job_data.get('department', '') or job_data.get('category', '')
            posted_date = job_data.get('DatePosted', '') or job_data.get('datePosted', '') or job_data.get('postedDate', '')

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
                'department': department if isinstance(department, str) else '',
                'apply_url': apply_url or self.url,
                'posted_date': posted_date,
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': 'Remote' if 'remote' in title.lower() else '',
                'status': 'active'
            }
            jobs.append(job)
            logger.info(f"Embedded Extracted: {title} | {location}")
        except Exception as e:
            logger.warning(f"Error processing embedded job: {str(e)}")

    def _process_jsonld_job(self, ld_data, jobs, seen_ids):
        """Process a JSON-LD JobPosting object."""
        try:
            title = ld_data.get('title', '')
            if not title:
                return

            job_id = ''
            identifier = ld_data.get('identifier')
            if isinstance(identifier, dict):
                job_id = identifier.get('value', '')
            if not job_id:
                job_id = hashlib.md5(title.encode()).hexdigest()[:12]

            if job_id in seen_ids:
                return
            seen_ids.add(job_id)

            city, state = '', ''
            location_data = ld_data.get('jobLocation', {})
            if isinstance(location_data, dict):
                address = location_data.get('address', {})
                if isinstance(address, dict):
                    city = address.get('addressLocality', '')
                    state = address.get('addressRegion', '')
                    country = address.get('addressCountry', '')
                    if country and country.lower() not in ('in', 'ind', 'india', ''):
                        return

            location_parts = [p for p in [city, state] if p]
            location = ', '.join(location_parts) + ', India' if location_parts else 'India'

            apply_url = ld_data.get('url', '') or self.url
            posted_date = ld_data.get('datePosted', '')

            job = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'description': '',
                'location': location,
                'city': city,
                'state': state,
                'country': 'India',
                'employment_type': ld_data.get('employmentType', '') if isinstance(ld_data.get('employmentType'), str) else '',
                'department': '',
                'apply_url': apply_url,
                'posted_date': posted_date,
                'job_function': '',
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }
            jobs.append(job)
            logger.info(f"JSON-LD Extracted: {title} | {location}")
        except Exception as e:
            logger.warning(f"Error processing JSON-LD job: {str(e)}")


if __name__ == "__main__":
    scraper = CargillScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

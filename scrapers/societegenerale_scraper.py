import requests
import hashlib
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('societegenerale_scraper')


class SocieteGeneraleScraper:
    def __init__(self):
        self.company_name = 'Societe Generale'
        # Algolia search backend discovered from careers.societegenerale.com main.js
        self.algolia_app_id = '1LDUTI39JZ'
        self.algolia_api_key = '2bd238230defca6327e7aae23105057d'
        self.algolia_index = 'prod_jobs_en'
        self.algolia_url = f'https://{self.algolia_app_id}-dsn.algolia.net/1/indexes/{self.algolia_index}/query'
        self.careers_url = 'https://careers.societegenerale.com/en/jobs'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
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

    def _scrape_algolia(self, max_pages):
        """Scrape jobs using the Algolia search API used by careers.societegenerale.com."""
        jobs = []
        seen_ids = set()
        hits_per_page = 100

        for page in range(max_pages):
            logger.info(f"Algolia: Fetching page {page + 1}")
            try:
                headers = {
                    'X-Algolia-Application-Id': self.algolia_app_id,
                    'X-Algolia-API-Key': self.algolia_api_key,
                    'Content-Type': 'application/json',
                }
                # Filter for India jobs using facet filters
                # The Algolia index uses jobLocation as a facet
                payload = {
                    'query': '',
                    'hitsPerPage': hits_per_page,
                    'page': page,
                    'facetFilters': [['jobLocation:IND']],
                }
                response = self.session.post(self.algolia_url, json=payload, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.warning(f"Algolia API error: {e}")
                # Try without facet filter, with text query instead
                try:
                    payload = {
                        'query': 'India',
                        'hitsPerPage': hits_per_page,
                        'page': page,
                    }
                    response = self.session.post(self.algolia_url, json=payload, headers=headers, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                except Exception as e2:
                    logger.error(f"Algolia fallback also failed: {e2}")
                    break

            hits = data.get('hits', [])
            if not hits:
                logger.info(f"No more hits at page {page}")
                break

            for hit in hits:
                try:
                    job_id = hit.get('objectID', '') or hit.get('id', '')
                    title = hit.get('title', '') or hit.get('jobTitle', '') or hit.get('name', '')
                    title = title.strip()
                    if not title:
                        continue

                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    # Location
                    location = hit.get('jobCity', '') or hit.get('city', '') or hit.get('location', '')
                    country = hit.get('jobCountry', '') or hit.get('country', '') or hit.get('jobLocation', '')

                    # Filter for India
                    if country and country.upper() not in ('IND', 'IN', 'INDIA'):
                        if not self._is_india_location(location):
                            continue

                    if location and 'india' not in location.lower():
                        location = f"{location}, India"
                    elif not location:
                        location = 'India'

                    city, state, _ = self.parse_location(location)

                    # Department
                    department = hit.get('jobDepartment', '') or hit.get('department', '') or hit.get('jobFamily', '')

                    # Apply URL
                    slug = hit.get('slug', '') or hit.get('url', '')
                    if slug and not slug.startswith('http'):
                        apply_url = f"https://careers.societegenerale.com/en/job-offer/{slug}"
                    elif slug:
                        apply_url = slug
                    else:
                        apply_url = self.careers_url

                    # Posted date
                    posted_date = hit.get('publicationDate', '') or hit.get('datePosted', '') or hit.get('createdAt', '')

                    # Employment type
                    employment_type = hit.get('contractType', '') or hit.get('employmentType', '')

                    # Experience level
                    experience_level = hit.get('experienceLevel', '') or hit.get('experience', '')

                    # Job function
                    job_function = hit.get('jobFunction', '') or hit.get('function', '')

                    # Remote
                    remote_type = ''
                    if hit.get('remote') or 'remote' in title.lower():
                        remote_type = 'Remote'
                    elif 'hybrid' in title.lower():
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
                        'employment_type': employment_type if isinstance(employment_type, str) else '',
                        'department': department if isinstance(department, str) else '',
                        'apply_url': apply_url,
                        'posted_date': posted_date,
                        'job_function': job_function if isinstance(job_function, str) else '',
                        'experience_level': experience_level if isinstance(experience_level, str) else '',
                        'salary_range': '',
                        'remote_type': remote_type,
                        'status': 'active'
                    }
                    jobs.append(job)
                    logger.info(f"Extracted: {title} | {location} | {department}")
                except Exception as e:
                    logger.warning(f"Error parsing Algolia hit: {e}")
                    continue

            logger.info(f"Page {page + 1}: {len(hits)} hits (total jobs: {len(jobs)})")

            if len(hits) < hits_per_page:
                break

        return jobs

    def _scrape_smartrecruiters(self, max_pages):
        """Fallback: Try SmartRecruiters API (company slug: SocieteGenerale4)."""
        jobs = []
        url = 'https://api.smartrecruiters.com/v1/companies/SocieteGenerale4/postings'
        limit = 100
        offset = 0
        page = 0

        while page < max_pages:
            params = {'limit': limit, 'offset': offset, 'country': 'IN'}
            logger.info(f"SmartRecruiters: Fetching page {page + 1}")
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

                    if country_code and country_code.lower() not in ('in', 'ind', 'india'):
                        continue

                    location_parts = [p for p in [city_name, region] if p]
                    location = ', '.join(location_parts) + ', India' if location_parts else 'India'

                    dept_obj = job_data.get('department', {})
                    department = dept_obj.get('label', '') if dept_obj else ''

                    apply_url = f"https://careers.smartrecruiters.com/SocieteGenerale4/{job_id}"
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Societe Generale jobs using Algolia API with SmartRecruiters fallback.

        The company's careers site at careers.societegenerale.com uses Algolia for search.
        Algolia credentials: appId=1LDUTI39JZ, apiKey=2bd238230defca6327e7aae23105057d
        Index: prod_jobs_en
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")

            # Strategy 1: Algolia API (primary source)
            jobs = self._scrape_algolia(max_pages)
            if jobs:
                logger.info(f"Got {len(jobs)} jobs from Algolia")
                return jobs

            # Strategy 2: SmartRecruiters API (fallback)
            logger.info("Algolia returned no jobs, trying SmartRecruiters...")
            jobs = self._scrape_smartrecruiters(max_pages)
            if jobs:
                logger.info(f"Got {len(jobs)} jobs from SmartRecruiters")
                return jobs

            logger.warning(f"No jobs found for {self.company_name} from any source")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs


if __name__ == "__main__":
    scraper = SocieteGeneraleScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

import requests
import hashlib
import re

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('gac_scraper')


class GACScraper:
    def __init__(self):
        self.company_name = "Guangzhou Automobile Group"
        self.api_url = 'https://career.gac.com/api/offers/'
        self.headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
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
        return result

    def _clean_html(self, html_str):
        """Strip HTML tags from a string."""
        if not html_str:
            return ''
        clean = re.sub(r'<[^>]+>', ' ', html_str)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean[:3000]

    def _is_india_job(self, offer):
        """Check if the job is located in India."""
        # Check multiple location fields
        location_fields = [
            offer.get('location', {}),
            offer.get('country', ''),
            offer.get('country_code', ''),
        ]

        # Check location object
        location = offer.get('location', {})
        if isinstance(location, dict):
            country = location.get('country', '')
            country_code = location.get('country_code', '')
            location_name = location.get('name', '') or location.get('city', '')
            if 'india' in country.lower() or country_code.upper() in ['IN', 'IND']:
                return True
            if 'india' in str(location_name).lower():
                return True

        # Check top-level fields
        country = str(offer.get('country', '')).lower()
        country_code = str(offer.get('country_code', '')).upper()
        if 'india' in country or country_code in ['IN', 'IND']:
            return True

        # Check location name string
        location_name = ''
        if isinstance(location, str):
            location_name = location
        elif isinstance(location, dict):
            location_name = location.get('name', '') or location.get('city', '')
        if 'india' in str(location_name).lower():
            return True

        # Check in tags/categories
        tags = offer.get('tags', [])
        if isinstance(tags, list):
            for tag in tags:
                if 'india' in str(tag).lower():
                    return True

        # Check in department or other fields
        for field_name in ['department', 'offices', 'regions']:
            field = offer.get(field_name, '')
            if 'india' in str(field).lower():
                return True

        return False

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        try:
            logger.info(f"Starting {self.company_name} scraping from API: {self.api_url}")

            try:
                response = requests.get(self.api_url, headers=self.headers, timeout=30)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed: {str(e)}")
                return all_jobs

            data = response.json()

            # Handle both direct array and nested structure
            if isinstance(data, list):
                offers = data
            elif isinstance(data, dict):
                offers = (
                    data.get('results', []) or
                    data.get('offers', []) or
                    data.get('data', []) or
                    data.get('jobs', []) or
                    []
                )
            else:
                logger.error(f"Unexpected API response type: {type(data)}")
                return all_jobs

            logger.info(f"Total offers from API: {len(offers)}")

            # Filter for India-based jobs
            seen_ids = set()
            india_count = 0
            other_count = 0

            for offer in offers:
                try:
                    if not self._is_india_job(offer):
                        other_count += 1
                        continue

                    india_count += 1
                    job_data = self._parse_offer(offer)
                    if job_data and job_data['external_id'] not in seen_ids:
                        all_jobs.append(job_data)
                        seen_ids.add(job_data['external_id'])
                        logger.info(f"Extracted: {job_data['title']} | {job_data['location']}")

                except Exception as e:
                    logger.error(f"Error parsing offer: {str(e)}")
                    continue

            logger.info(f"India jobs found: {india_count}, other locations: {other_count}")
            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _parse_offer(self, offer):
        """Parse a single offer from the API response."""
        # Title
        title = (
            offer.get('title', '') or
            offer.get('name', '') or
            offer.get('position', '') or
            ''
        ).strip()

        if not title:
            return None

        # Job ID
        job_id = str(
            offer.get('id', '') or
            offer.get('slug', '') or
            offer.get('offer_id', '') or
            ''
        ).strip()

        if not job_id:
            job_id = hashlib.md5(title.encode()).hexdigest()[:12]

        external_id = self.generate_external_id(job_id, self.company_name)

        # Description (may be HTML)
        description_raw = (
            offer.get('description', '') or
            offer.get('content', '') or
            offer.get('job_description', '') or
            ''
        )
        description = self._clean_html(description_raw)

        # Location
        location = ''
        location_obj = offer.get('location', {})
        if isinstance(location_obj, dict):
            location = (
                location_obj.get('name', '') or
                location_obj.get('city', '') or
                ''
            ).strip()
            if not location:
                city = location_obj.get('city', '')
                country = location_obj.get('country', '')
                if city and country:
                    location = f"{city}, {country}"
                elif city:
                    location = city
                elif country:
                    location = country
        elif isinstance(location_obj, str):
            location = location_obj.strip()

        location_parts = self.parse_location(location)

        # Department
        department = ''
        dept_obj = offer.get('department', {})
        if isinstance(dept_obj, dict):
            department = dept_obj.get('name', '') or dept_obj.get('title', '') or ''
        elif isinstance(dept_obj, str):
            department = dept_obj
        department = department.strip()

        # Employment type
        employment_type = (
            offer.get('employment_type', '') or
            offer.get('employment_type_code', '') or
            offer.get('contract_type', '') or
            offer.get('job_type', '') or
            ''
        ).strip()

        # Experience
        experience = ''
        min_exp = offer.get('min_experience', '') or offer.get('experience_min', '')
        max_exp = offer.get('max_experience', '') or offer.get('experience_max', '')
        if min_exp and max_exp:
            experience = f"{min_exp}-{max_exp} years"
        elif min_exp:
            experience = f"{min_exp}+ years"
        elif max_exp:
            experience = f"Up to {max_exp} years"

        # Salary
        salary = ''
        min_salary = offer.get('min_salary', '') or offer.get('salary_min', '')
        max_salary = offer.get('max_salary', '') or offer.get('salary_max', '')
        salary_currency = offer.get('salary_currency', '') or offer.get('currency', '')
        if min_salary and max_salary:
            salary = f"{salary_currency} {min_salary}-{max_salary}".strip()
        elif min_salary:
            salary = f"{salary_currency} {min_salary}+".strip()
        elif max_salary:
            salary = f"Up to {salary_currency} {max_salary}".strip()

        # Apply URL
        apply_url = (
            offer.get('careers_url', '') or
            offer.get('apply_url', '') or
            offer.get('url', '') or
            offer.get('career_url', '') or
            ''
        ).strip()
        if not apply_url:
            slug = offer.get('slug', '') or offer.get('id', '')
            if slug:
                apply_url = f"https://career.gac.com/o/{slug}"
            else:
                apply_url = 'https://career.gac.com/'

        # Posted date
        posted_date = (
            offer.get('created_at', '') or
            offer.get('published_at', '') or
            offer.get('posted_date', '') or
            ''
        ).strip()
        # Clean up ISO date format
        if posted_date and 'T' in posted_date:
            posted_date = posted_date.split('T')[0]

        # Remote type
        remote_type = ''
        remote = offer.get('remote', None) or offer.get('remote_type', '')
        if remote:
            if isinstance(remote, bool):
                remote_type = 'Remote' if remote else ''
            elif isinstance(remote, str):
                remote_type = remote.strip()

        return {
            'external_id': external_id,
            'company_name': self.company_name,
            'title': title,
            'description': description,
            'location': location,
            'city': location_parts['city'],
            'state': location_parts['state'],
            'country': location_parts['country'],
            'employment_type': employment_type,
            'department': department,
            'apply_url': apply_url,
            'posted_date': posted_date,
            'job_function': '',
            'experience_level': experience,
            'salary_range': salary,
            'remote_type': remote_type,
            'status': 'active'
        }


if __name__ == "__main__":
    scraper = GACScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

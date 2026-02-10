import requests
import hashlib
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('goldmansachs_scraper')


class GoldmanSachsScraper:
    def __init__(self):
        self.company_name = 'Goldman Sachs'
        # Original URL (S3 Access Denied, kept for reference)
        self.url = 'https://www.goldmansachs.com/careers/find-a-role/search-results.html?keyword=&location=India'
        # GraphQL API endpoint (discovered via network interception on higher.gs.com)
        self._api_url = 'https://api-higher.gs.com/gateway/api/v1/graphql'
        self._page_size = 20
        self._roles_base_url = 'https://higher.gs.com/roles'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _get_headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Origin': 'https://higher.gs.com',
            'Referer': 'https://higher.gs.com/',
        }

    def _get_roles_query(self):
        return """query GetRoles($searchQueryInput: RoleSearchQueryInput!) {
            roleSearch(searchQueryInput: $searchQueryInput) {
                totalCount
                items {
                    roleId
                    corporateTitle
                    jobTitle
                    jobFunction
                    locations {
                        primary
                        state
                        country
                        city
                    }
                    status
                    division
                    skills
                    jobType {
                        code
                        description
                    }
                    externalSource {
                        sourceId
                    }
                }
            }
        }"""

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Goldman Sachs India jobs via GraphQL API."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping via GraphQL API")
            headers = self._get_headers()
            query = self._get_roles_query()

            # Scrape both PROFESSIONAL and EARLY_CAREER experiences
            for experience in ['PROFESSIONAL', 'EARLY_CAREER']:
                page_number = 0
                pages_scraped = 0

                while pages_scraped < max_pages:
                    variables = {
                        "searchQueryInput": {
                            "page": {
                                "pageSize": self._page_size,
                                "pageNumber": page_number
                            },
                            "experiences": [experience],
                            "filters": [
                                {
                                    "filterCategoryType": "LOCATION",
                                    "filters": [{"filter": "India"}]
                                }
                            ]
                        }
                    }

                    try:
                        response = requests.post(
                            self._api_url,
                            headers=headers,
                            json={
                                'operationName': 'GetRoles',
                                'query': query,
                                'variables': variables
                            },
                            timeout=SCRAPE_TIMEOUT
                        )

                        if response.status_code != 200:
                            logger.warning(f"API returned status {response.status_code} for {experience} page {page_number}")
                            break

                        data = response.json()

                        if 'errors' in data:
                            error_msg = data['errors'][0].get('message', 'Unknown error')
                            logger.error(f"GraphQL error: {error_msg}")
                            break

                        role_search = data.get('data', {}).get('roleSearch', {})
                        total_count = role_search.get('totalCount', 0)
                        items = role_search.get('items', [])

                        if page_number == 0:
                            logger.info(f"{experience}: {total_count} total India jobs")

                        if not items:
                            logger.info(f"No more items for {experience} at page {page_number}")
                            break

                        new_count = 0
                        for item in items:
                            job_data = self._parse_role(item)
                            if job_data and job_data['external_id'] not in seen_ids:
                                all_jobs.append(job_data)
                                seen_ids.add(job_data['external_id'])
                                new_count += 1

                        logger.info(
                            f"{experience} page {page_number}: "
                            f"{len(items)} items, {new_count} new. Total: {len(all_jobs)}"
                        )

                        if new_count == 0:
                            break

                        # Check if we've fetched all available
                        fetched_so_far = (page_number + 1) * self._page_size
                        if fetched_so_far >= total_count:
                            logger.info(f"Reached end of {experience} results")
                            break

                        page_number += 1
                        pages_scraped += 1

                    except requests.exceptions.RequestException as e:
                        logger.error(f"Request failed for {experience} page {page_number}: {str(e)}")
                        break

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs

    def _parse_role(self, item):
        """Parse a single role item from GraphQL response."""
        try:
            job_title = item.get('jobTitle', '')
            if not job_title:
                return None

            role_id = item.get('roleId', '')
            # Extract the numeric source ID for the URL
            source_id = ''
            ext_source = item.get('externalSource')
            if ext_source:
                source_id = ext_source.get('sourceId', '')

            # Build the apply URL
            url_id = source_id if source_id else role_id
            apply_url = f'{self._roles_base_url}/{url_id}' if url_id else self.url

            # Build stable job ID
            job_id = role_id if role_id else f"gs_{hashlib.md5(job_title.encode()).hexdigest()[:10]}"

            # Parse locations
            locations = item.get('locations', [])
            location_parts = self._parse_locations(locations)
            location_str = location_parts.get('location', '')

            # Parse other fields
            division = item.get('division', '')
            corporate_title = item.get('corporateTitle', '')
            job_function = item.get('jobFunction', '')
            job_type = item.get('jobType', {})
            employment_type = job_type.get('description', '') if job_type else ''
            skills = item.get('skills', [])
            skills_str = ', '.join(skills) if skills else ''

            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': job_title,
                'description': skills_str,
                'location': location_str,
                'city': location_parts.get('city', ''),
                'state': location_parts.get('state', ''),
                'country': location_parts.get('country', 'India'),
                'employment_type': employment_type,
                'department': division,
                'apply_url': apply_url,
                'posted_date': '',
                'job_function': job_function,
                'experience_level': corporate_title,
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }

            return job_data

        except Exception as e:
            logger.error(f"Error parsing role: {str(e)}")
            return None

    def _parse_locations(self, locations):
        """Parse location list from GraphQL response into structured data."""
        result = {'location': '', 'city': '', 'state': '', 'country': 'India'}

        if not locations:
            return result

        # Use the primary location or first location
        primary_loc = None
        for loc in locations:
            if loc.get('primary'):
                primary_loc = loc
                break
        if not primary_loc:
            primary_loc = locations[0]

        city = primary_loc.get('city', '') or ''
        state = primary_loc.get('state', '') or ''
        country = primary_loc.get('country', '') or ''

        result['city'] = city
        result['state'] = state
        result['country'] = country if country else 'India'

        # Build location string
        parts = [p for p in [city, state, country] if p]
        result['location'] = ', '.join(parts)

        return result

    def parse_location(self, location_str):
        """Parse location string into city, state, country."""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'


if __name__ == "__main__":
    scraper = GoldmanSachsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs[:10]:
        print(f"- {job['title']} | {job['location']} | {job.get('experience_level', '')}")

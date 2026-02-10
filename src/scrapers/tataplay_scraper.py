import requests
import hashlib
import time
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('tataplay_scraper')


class TataPlayScraper:
    def __init__(self):
        self.company_name = 'Tata Play'
        self.url = 'https://hcoe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs?mode=location'
        self.api_url = 'https://hcoe.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions'
        self.site_number = 'CX_1001'
        self.page_size = 25
        self.job_detail_base_url = 'https://hcoe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job'

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Tata Play Oracle Cloud REST API with pagination"""
        all_jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name} via Oracle Cloud REST API")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            }

            current_page = 0
            total_jobs_count = None

            while current_page < max_pages:
                offset = current_page * self.page_size
                logger.info(f"Fetching page {current_page + 1} (offset={offset})")

                finder = (
                    f'findReqs;siteNumber={self.site_number},'
                    f'facetsList=LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;CATEGORIES;ORGANIZATIONS;POSTING_DATES;FLEX_FIELDS,'
                    f'limit={self.page_size},offset={offset},'
                    f'lastSelectedFacet=LOCATIONS'
                )

                params = {
                    'onlyData': 'true',
                    'expand': 'requisitionList.secondaryLocations,flexFieldsFacet.values',
                    'finder': finder,
                }

                try:
                    response = requests.get(
                        self.api_url,
                        params=params,
                        headers=headers,
                        timeout=30
                    )
                    response.raise_for_status()
                    data = response.json()
                except requests.exceptions.RequestException as e:
                    logger.error(f"API request failed on page {current_page + 1}: {str(e)}")
                    break
                except ValueError as e:
                    logger.error(f"Failed to parse JSON on page {current_page + 1}: {str(e)}")
                    break

                items = data.get('items', [])
                if not items:
                    logger.warning(f"No items in API response on page {current_page + 1}")
                    break

                item = items[0]

                if total_jobs_count is None:
                    total_jobs_count = item.get('TotalJobsCount', 0)
                    logger.info(f"Total jobs available: {total_jobs_count}")

                requisitions = item.get('requisitionList', [])
                if not requisitions:
                    logger.info(f"No more requisitions on page {current_page + 1}")
                    break

                logger.info(f"Page {current_page + 1}: {len(requisitions)} requisitions")

                for req in requisitions:
                    try:
                        job_data = self._parse_requisition(req)
                        if job_data:
                            all_jobs.append(job_data)
                    except Exception as e:
                        logger.error(f"Error parsing requisition: {str(e)}")
                        continue

                if offset + len(requisitions) >= total_jobs_count:
                    logger.info("Reached end of available jobs")
                    break

                current_page += 1
                time.sleep(1)

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _parse_requisition(self, req):
        """Parse a single requisition from the Oracle API response into a job dict"""
        job_id = req.get('Id', '')
        title = req.get('Title', '')

        if not title or not job_id:
            return None

        apply_url = f"{self.job_detail_base_url}/{job_id}"

        primary_location = req.get('PrimaryLocation', '')
        city, state, country = self.parse_location(primary_location)

        secondary_locs = req.get('secondaryLocations', [])
        secondary_loc_str = ''
        if secondary_locs:
            secondary_loc_str = '; '.join(
                loc.get('Name', '') for loc in secondary_locs if loc.get('Name')
            )

        description_parts = []
        short_desc = req.get('ShortDescriptionStr', '')
        if short_desc:
            description_parts.append(short_desc)
        ext_quals = req.get('ExternalQualificationsStr', '')
        if ext_quals:
            description_parts.append(f"Qualifications: {ext_quals}")
        ext_resp = req.get('ExternalResponsibilitiesStr', '')
        if ext_resp:
            description_parts.append(f"Responsibilities: {ext_resp}")
        description = '\n\n'.join(description_parts)[:3000]

        workplace_type = req.get('WorkplaceType', '') or ''
        remote_type = ''
        if 'remote' in workplace_type.lower():
            remote_type = 'Remote'
        elif 'hybrid' in workplace_type.lower():
            remote_type = 'Hybrid'
        elif workplace_type:
            remote_type = 'On-site'

        employment_type = ''
        worker_type = req.get('WorkerType', '') or ''
        contract_type = req.get('ContractType', '') or ''
        if worker_type:
            employment_type = worker_type
        elif contract_type:
            employment_type = contract_type

        department = req.get('Department', '') or req.get('Organization', '') or ''
        job_function = req.get('JobFunction', '') or req.get('JobFamily', '') or ''

        posted_date = req.get('PostedDate', '') or ''

        job_data = {
            'external_id': self.generate_external_id(str(job_id), self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': description,
            'location': primary_location,
            'city': city,
            'state': state,
            'country': country if country else 'India',
            'employment_type': employment_type,
            'department': department,
            'apply_url': apply_url,
            'posted_date': posted_date,
            'job_function': job_function,
            'experience_level': '',
            'salary_range': '',
            'remote_type': remote_type,
            'status': 'active'
        }

        return job_data

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        country = parts[2] if len(parts) > 2 else ''

        if not country and 'India' in location_str:
            country = 'India'

        return city, state, country


if __name__ == "__main__":
    scraper = TataPlayScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']} | {job['posted_date']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

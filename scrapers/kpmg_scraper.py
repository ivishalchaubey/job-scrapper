import hashlib
import html
import re
import time

import requests

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('kpmg_scraper')


class KPMGScraper:
    def __init__(self):
        self.company_name = 'KPMG'
        self.url = 'https://ejgk.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs?mode=location'
        self.api_url = 'https://ejgk.fa.em2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions'
        self.site_number = 'CX_1'
        self.page_size = 25
        self.job_detail_base_url = 'https://ejgk.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job'
        self.detail_api_url = 'https://ejgk.fa.em2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails'
        self.india_keywords = [
            'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi',
            'hyderabad', 'chennai', 'pune', 'gurugram', 'gurgaon',
            'noida', 'kolkata', 'ahmedabad', 'jaipur', 'kochi',
            'thiruvananthapuram', 'chandigarh', 'lucknow', 'indore',
            'new delhi', 'ncr', 'haryana', 'karnataka', 'maharashtra',
            'tamil nadu', 'telangana', 'gujarat', 'rajasthan',
            'uttar pradesh', 'west bengal', 'kerala'
        ]

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name} via Oracle Cloud REST API")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            }
            session = requests.Session()
            session.headers.update(headers)

            current_page = 0
            total_jobs_count = None

            while current_page < max_pages:
                offset = current_page * self.page_size
                logger.info(f"Fetching page {current_page + 1} (offset={offset})")

                finder = (
                    f'findReqs;siteNumber={self.site_number},'
                    f'facetsList=LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;CATEGORIES;ORGANIZATIONS;POSTING_DATES;FLEX_FIELDS,'
                    f'limit={self.page_size},offset={offset},'
                    f'sortBy=POSTING_DATES_DESC'
                )

                params = {
                    'onlyData': 'true',
                    'expand': 'requisitionList.secondaryLocations,flexFieldsFacet.values',
                    'finder': finder,
                }

                try:
                    response = session.get(self.api_url, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                except requests.exceptions.RequestException as exc:
                    logger.error(f"API request failed on page {current_page + 1}: {str(exc)}")
                    break
                except ValueError as exc:
                    logger.error(f"Failed to parse JSON on page {current_page + 1}: {str(exc)}")
                    break

                items = data.get('items', [])
                if not items:
                    logger.warning(f"No items in API response on page {current_page + 1}")
                    break

                item = items[0]

                if total_jobs_count is None:
                    total_jobs_count = item.get('TotalJobsCount', 0)
                    logger.info(f"Total jobs available: {total_jobs_count}")
                    if total_jobs_count == 0:
                        break

                requisitions = item.get('requisitionList', [])
                if not requisitions:
                    break

                logger.info(f"Page {current_page + 1}: {len(requisitions)} requisitions")

                for req in requisitions:
                    try:
                        job_data = self._parse_requisition(req, session)
                        if job_data:
                            all_jobs.append(job_data)
                    except Exception as exc:
                        logger.error(f"Error parsing requisition: {str(exc)}")
                        continue

                if offset + len(requisitions) >= total_jobs_count:
                    logger.info('Reached end of available jobs')
                    break

                current_page += 1
                time.sleep(1)

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as exc:
            logger.error(f"Error scraping {self.company_name}: {str(exc)}")

        return all_jobs

    def _parse_requisition(self, req, session):
        job_id = req.get('Id', '')
        title = req.get('Title', '')

        if not title or not job_id:
            return None

        primary_location = req.get('PrimaryLocation', '') or ''
        if not self._is_india_location(primary_location):
            return None

        detail = self._fetch_job_detail(session, job_id)
        detail_location = detail.get('location', '')
        if detail_location and self._is_india_location(detail_location):
            primary_location = detail_location

        apply_url = f"{self.job_detail_base_url}/{job_id}"
        city, state, country = self.parse_location(primary_location)

        description_parts = []
        if detail.get('description'):
            description_parts.append(detail['description'])
        elif req.get('ShortDescriptionStr'):
            description_parts.append(self._strip_html(req.get('ShortDescriptionStr', '')))

        if detail.get('responsibilities'):
            description_parts.append(f"Responsibilities:\n{detail['responsibilities']}")
        elif req.get('ExternalResponsibilitiesStr'):
            description_parts.append(
                f"Responsibilities:\n{self._strip_html(req.get('ExternalResponsibilitiesStr', ''))}"
            )

        if detail.get('qualifications'):
            description_parts.append(f"Qualifications:\n{detail['qualifications']}")
        elif req.get('ExternalQualificationsStr'):
            description_parts.append(
                f"Qualifications:\n{self._strip_html(req.get('ExternalQualificationsStr', ''))}"
            )

        description = '\n\n'.join(part for part in description_parts if part).strip()[:6000]

        workplace_type = detail.get('workplace_type') or req.get('WorkplaceType', '') or ''
        remote_type = ''
        workplace_type_lower = workplace_type.lower()
        if 'remote' in workplace_type_lower:
            remote_type = 'Remote'
        elif 'hybrid' in workplace_type_lower:
            remote_type = 'Hybrid'
        elif workplace_type:
            remote_type = 'On-site'

        employment_type = ''
        worker_type = detail.get('worker_type') or req.get('WorkerType', '') or ''
        contract_type = detail.get('contract_type') or req.get('ContractType', '') or ''
        if worker_type:
            employment_type = worker_type
        elif contract_type:
            employment_type = contract_type

        department = detail.get('department') or req.get('Department', '') or req.get('Organization', '') or ''
        job_function = detail.get('job_function') or req.get('JobFunction', '') or req.get('JobFamily', '') or ''
        posted_date = (
            detail.get('posted_date')
            or req.get('PostedDate', '')
            or self._format_date(req.get('ExternalPostedStartDate', ''))
        )
        experience_level = detail.get('experience_level', '')

        return {
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
            'experience_level': experience_level,
            'salary_range': '',
            'remote_type': remote_type,
            'status': 'active',
        }

    def _fetch_job_detail(self, session, job_id):
        finder = f'ById;Id="{job_id}",siteNumber={self.site_number}'
        params = {
            'expand': 'all',
            'onlyData': 'true',
            'finder': finder,
        }

        try:
            response = session.get(self.detail_api_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            items = data.get('items', [])
            if not items:
                return {}

            item = items[0]
            location_text = item.get('PrimaryLocation', '') or ''

            responsibilities = self._strip_html(item.get('ExternalResponsibilitiesStr', '') or '')
            qualifications = self._strip_html(item.get('ExternalQualificationsStr', '') or '')
            description = self._strip_html(item.get('ExternalDescriptionStr', '') or '')
            work_years = item.get('WorkYears')
            work_months = item.get('WorkMonths')
            experience_text = '\n'.join(part for part in [description, responsibilities, qualifications] if part)

            experience_level = ''
            if isinstance(work_years, int) and work_years > 0:
                experience_level = f"{work_years} years"
            elif isinstance(work_months, int) and work_months > 0:
                experience_level = f"{work_months} months"
            else:
                experience_level = self._extract_experience_level(experience_text)

            return {
                'description': description,
                'responsibilities': responsibilities,
                'qualifications': qualifications,
                'location': location_text,
                'posted_date': self._format_date(item.get('ExternalPostedStartDate', '')),
                'apply_before': self._format_date(item.get('ExternalPostedEndDate', '')),
                'department': item.get('Department', '') or item.get('Organization', '') or '',
                'job_function': item.get('JobFunction', '') or item.get('JobFamily', '') or '',
                'worker_type': item.get('WorkerType', '') or '',
                'contract_type': item.get('ContractType', '') or '',
                'workplace_type': item.get('WorkplaceType', '') or '',
                'experience_level': experience_level,
            }
        except Exception as exc:
            logger.debug(f"Failed to fetch details for {job_id}: {str(exc)}")
            return {}

    def _extract_experience_level(self, text):
        if not text:
            return ''

        normalized = re.sub(r'\s+', ' ', text)
        patterns = [
            r'\b(\d{1,2})\s*(?:to|-|–|—)\s*(\d{1,2})\s*(?:years?|yrs?)\b',
            r'\b(\d{1,2})\s*(?:years?|yrs?)\s*(?:to|-|–|—)\s*(\d{1,2})\s*(?:years?|yrs?)\b',
            r'\b(?:minimum of|minimum|at least|must have relevant experience of|must have experience of|relevant experience of)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b',
            r'\b(\d{1,2})\+\s*(?:years?|yrs?)\b',
            r'\bexperience\s*(?:of|in)?\s*(\d{1,2})\s*(?:to|-|–|—)\s*(\d{1,2})\s*(?:years?|yrs?)\b',
            r'\bexperience\s*(?:of|in)?\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b',
        ]

        for pattern in patterns[:2]:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                return f"{match.group(1)} to {match.group(2)} years"

        for pattern in patterns[2:4]:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                return f"{match.group(1)}+ years"

        match = re.search(patterns[4], normalized, re.IGNORECASE)
        if match:
            return f"{match.group(1)} to {match.group(2)} years"

        match = re.search(patterns[5], normalized, re.IGNORECASE)
        if match:
            return f"{match.group(1)}+ years"

        return ''

    def _strip_html(self, value):
        if not value:
            return ''
        text = re.sub(r'(?i)<br\s*/?>', '\n', value)
        text = re.sub(r'(?i)</p>', '\n\n', text)
        text = re.sub(r'(?i)</li>', '\n', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = text.replace('\r', '')
        text = re.sub(r'[ \t\f\v]+', ' ', text)
        text = re.sub(r' *\n *', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _format_date(self, value):
        if not value:
            return ''
        return str(value)[:10]

    def _is_india_location(self, location_text):
        if not location_text:
            return True
        location_lower = location_text.lower()
        if 'indiana' in location_lower:
            return False
        return any(keyword in location_lower for keyword in self.india_keywords)

    def parse_location(self, location_str):
        if not location_str:
            return '', '', 'India'

        parts = [part.strip() for part in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        country = parts[2] if len(parts) > 2 else ''

        if not country and 'india' in location_str.lower():
            country = 'India'

        return city, state, country

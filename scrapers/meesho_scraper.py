import hashlib
import html
import re
from datetime import datetime

import requests

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('meesho_scraper')


class MeeshoScraper:
    def __init__(self):
        self.company_name = 'Meesho'
        self.url = 'https://www.meesho.io/jobs'
        self.api_url = 'https://api.lever.co/v0/postings/meesho?mode=json'
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
        jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name} via Lever API")

            headers = {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            }

            response = requests.get(self.api_url, headers=headers, timeout=30)
            response.raise_for_status()
            postings = response.json()

            if not isinstance(postings, list):
                logger.error(f"Unexpected Meesho API response type: {type(postings)}")
                return jobs

            logger.info(f"Lever API returned {len(postings)} total postings")

            for posting in postings:
                try:
                    job_data = self._parse_posting(posting)
                    if job_data:
                        jobs.append(job_data)
                except Exception as exc:
                    logger.error(f"Error processing Meesho posting: {str(exc)}")
                    continue

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as exc:
            logger.error(f"Error scraping {self.company_name}: {str(exc)}")

        return jobs

    def _parse_posting(self, posting):
        title = posting.get('text', '') or ''
        if not title:
            return None

        categories = posting.get('categories', {}) or {}
        location = categories.get('location', '') or ''
        country = posting.get('country', '') or ''
        if not self._is_india_job(location, country):
            return None

        job_id = posting.get('id', '') or hashlib.md5(title.encode()).hexdigest()[:12]
        apply_url = posting.get('hostedUrl', '') or posting.get('applyUrl', '') or self.url
        description = self._build_description(posting)
        experience_level = self._extract_experience_level(description)
        posted_date = self._format_timestamp(posting.get('createdAt'))

        location_parts = self.parse_location(location)
        department = categories.get('department', '') or ''
        team = categories.get('team', '') or ''
        commitment = categories.get('commitment', '') or ''
        workplace_type = posting.get('workplaceType', '') or ''

        return {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': description,
            'location': location,
            'city': location_parts.get('city', ''),
            'state': location_parts.get('state', ''),
            'country': location_parts.get('country', 'India'),
            'employment_type': self._map_employment_type(commitment),
            'department': department,
            'apply_url': apply_url,
            'posted_date': posted_date,
            'job_function': team,
            'experience_level': experience_level,
            'salary_range': '',
            'remote_type': self._map_remote_type(workplace_type),
            'status': 'active'
        }

    def _build_description(self, posting):
        sections = []

        description_plain = self._clean_text(posting.get('descriptionPlain', '') or posting.get('description', ''))
        if description_plain:
            sections.append(description_plain)

        opening_plain = self._clean_text(posting.get('openingPlain', '') or posting.get('opening', ''))
        if opening_plain and opening_plain not in sections:
            sections.append(opening_plain)

        for item in posting.get('lists', []) or []:
            heading = self._clean_text(item.get('text', '') or '')
            content = self._clean_text(item.get('content', '') or '')
            if heading and content:
                sections.append(f"{heading}:\n{content}")
            elif content:
                sections.append(content)
            elif heading:
                sections.append(heading)

        description = '\n\n'.join(section for section in sections if section).strip()
        return description[:6000]

    def _extract_experience_level(self, text):
        if not text:
            return ''

        normalized = re.sub(r'\s+', ' ', text)
        patterns = [
            r'\b(\d{1,2})\s*(?:to|-|–|—)\s*(\d{1,2})\s*(?:years?|yrs?|yr)\b',
            r'\b(\d{1,2})\s*(?:years?|yrs?|yr)\s*(?:to|-|–|—)\s*(\d{1,2})\s*(?:years?|yrs?|yr)\b',
            r'\b(\d{1,2})\s*\+\s*(?:years?|yrs?|yr)\b',
            r'\b(?:minimum of|minimum|at least|must have|relevant experience of|experience of|experience in)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?|yr)\b',
            r'\b(\d{1,2})\s*(?:months?)\b',
        ]

        for pattern in patterns[:2]:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                return f"{match.group(1)} to {match.group(2)} years"

        match = re.search(patterns[2], normalized, re.IGNORECASE)
        if match:
            return f"{match.group(1)}+ years"

        match = re.search(patterns[3], normalized, re.IGNORECASE)
        if match:
            return f"{match.group(1)}+ years"

        match = re.search(patterns[4], normalized, re.IGNORECASE)
        if match:
            return f"{match.group(1)} months"

        return ''

    def _map_employment_type(self, commitment):
        if not commitment:
            return ''

        commitment_lower = commitment.lower()
        if 'full' in commitment_lower:
            return 'Full Time'
        if 'part' in commitment_lower:
            return 'Part Time'
        if 'intern' in commitment_lower:
            return 'Intern'
        if 'contract' in commitment_lower:
            return 'Contract'
        return commitment

    def _map_remote_type(self, workplace_type):
        workplace_type_lower = (workplace_type or '').lower()
        if workplace_type_lower == 'remote':
            return 'Remote'
        if workplace_type_lower == 'hybrid':
            return 'Hybrid'
        if workplace_type_lower == 'onsite':
            return 'On-site'
        return ''

    def _format_timestamp(self, timestamp_ms):
        if not timestamp_ms:
            return ''
        try:
            return datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d')
        except Exception:
            return ''

    def _clean_text(self, value):
        if not value:
            return ''
        text = re.sub(r'(?i)<br\s*/?>', '\n', value)
        text = re.sub(r'(?i)</p>', '\n\n', text)
        text = re.sub(r'(?i)</li>', '\n', text)
        text = re.sub(r'(?i)</div>', '\n', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = text.replace('\r', '')
        text = re.sub(r'[ \t\f\v]+', ' ', text)
        text = re.sub(r' *\n *', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _is_india_job(self, location, country):
        location_lower = (location or '').lower()
        if 'indiana' in location_lower:
            return False
        return country == 'IN' or any(keyword in location_lower for keyword in self.india_keywords)

    def parse_location(self, location_str):
        if not location_str:
            return {'city': '', 'state': '', 'country': 'India'}

        parts = [part.strip() for part in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        country = parts[2] if len(parts) > 2 else ''
        if not country:
            country = 'India'

        return {'city': city, 'state': state, 'country': country}
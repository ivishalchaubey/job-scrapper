import hashlib
import html
import json
import re
import time

import requests

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE
from scrapers.csv_url_resolver import get_company_url

logger = setup_logger('jll_scraper')


class JLLScraper:
    def __init__(self):
        self.company_name = "JLL"
        default_url = (
            "https://jll.wd1.myworkdayjobs.com/en-GB/jllcareers"
            "?locationCountry=c4f78be1a8f14da0ab49ce1162348a5e"
        )
        self.url = get_company_url(self.company_name, default_url)
        self.api_url = "https://jll.wd1.myworkdayjobs.com/wday/cxs/jll/jllcareers/jobs"
        self.base_job_url = "https://jll.wd1.myworkdayjobs.com/jllcareers"
        self._detail_cache = {}

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': ''}
        if not location_str:
            return result

        normalized = location_str.replace('IND-CORP', '').replace('|', ',').strip(' ,')
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        if not normalized:
            return result

        # Workday India often uses "City, ST"
        direct_match = re.match(r'^([^,]+),\s*([A-Za-z]{2})$', normalized)
        if direct_match:
            result['city'] = direct_match.group(1).strip()
            result['state'] = direct_match.group(2).upper()
            return result

        # Handle "City-..." patterns
        if ',' not in normalized and '-' in normalized:
            segments = [seg.strip() for seg in normalized.split('-') if seg.strip()]
            if segments:
                result['city'] = segments[0]
            if len(segments) > 1 and len(segments[1]) == 2:
                result['state'] = segments[1].upper()
            return result

        parts = [p.strip() for p in normalized.split(',') if p.strip()]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 2:
            result['state'] = parts[1]
        if len(parts) >= 3:
            result['country'] = parts[2]
        return result

    def _format_location(self, city, state, country):
        parts = [p for p in [city, state, country] if p]
        return ', '.join(parts) if parts else ''

    def _extract_job_id(self, external_path, bullet_fields, title):
        for field in bullet_fields or []:
            if isinstance(field, str):
                match = re.search(r'(REQ\d+)', field, re.IGNORECASE)
                if match:
                    return match.group(1).upper()
        if external_path:
            match = re.search(r'(REQ\d+)', external_path, re.IGNORECASE)
            if match:
                return match.group(1).upper()
            tail = external_path.strip('/').split('/')[-1]
            if tail:
                return tail
        return ''

    def _clean_text(self, value):
        if not value:
            return ''
        text = html.unescape(str(value))
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _extract_json_ld(self, html_text):
        match = re.search(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return {}
        raw = match.group(1).strip()
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                        return item
                return {}
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {}
        return {}

    def _extract_meta_content(self, html_text, prop_name):
        pattern = (
            r'<meta[^>]*'
            + rf'(?:name|property)=["\']{re.escape(prop_name)}["\'][^>]*'
            + r'content=["\'](.*?)["\'][^>]*>'
        )
        match = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
        if not match:
            return ''
        return self._clean_text(match.group(1))

    def _extract_experience(self, description_text):
        if not description_text:
            return ''
        patterns = [
            r'(\d+\s*-\s*\d+\s+years?)',
            r'(\d+\+?\s+years?\s+professional\s+experience)',
            r'(\d+\+?\s+years?\s+experience)',
        ]
        for pattern in patterns:
            match = re.search(pattern, description_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ''

    def _fetch_job_details(self, session, apply_url):
        if apply_url in self._detail_cache:
            return self._detail_cache[apply_url]

        details = {
            'description': '',
            'employment_type': '',
            'department': '',
            'posted_date': '',
            'location': '',
            'city': '',
            'state': '',
            'country': '',
            'experience_level': '',
        }

        try:
            response = session.get(
                apply_url,
                headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'User-Agent': session.headers.get('User-Agent', 'Mozilla/5.0'),
                },
                timeout=30,
            )
            response.raise_for_status()
            page_html = response.text
        except Exception as e:
            logger.warning(f"Failed detail fetch for {apply_url}: {str(e)}")
            self._detail_cache[apply_url] = details
            return details

        job_posting = self._extract_json_ld(page_html)
        og_description = self._extract_meta_content(page_html, 'og:description')
        description = self._clean_text(job_posting.get('description', '')) or og_description
        if description:
            details['description'] = description[:15000]
            details['experience_level'] = self._extract_experience(description)

        employment_type = self._clean_text(job_posting.get('employmentType', ''))
        if employment_type:
            details['employment_type'] = employment_type

        date_posted = self._clean_text(job_posting.get('datePosted', ''))
        if date_posted:
            details['posted_date'] = date_posted

        hiring_org = job_posting.get('hiringOrganization') or {}
        if isinstance(hiring_org, dict):
            dept = self._clean_text(hiring_org.get('name', ''))
            if dept:
                details['department'] = dept

        job_location = job_posting.get('jobLocation') or {}
        if isinstance(job_location, dict):
            address = job_location.get('address') or {}
            if isinstance(address, dict):
                locality = self._clean_text(address.get('addressLocality', ''))
                country = self._clean_text(address.get('addressCountry', ''))
                if locality:
                    details['location'] = locality
                    loc_parts = self.parse_location(locality)
                    details['city'] = loc_parts.get('city', '')
                    details['state'] = loc_parts.get('state', '')
                if country:
                    details['country'] = country

        self._detail_cache[apply_url] = details
        return details

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        limit = 20
        max_results = max_pages * limit
        session = requests.Session()
        session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            ),
        })

        offset = 0
        while offset < max_results:
            payload = {
                "appliedFacets": {"locationCountry": ["c4f78be1a8f14da0ab49ce1162348a5e"]},
                "limit": limit,
                "offset": offset,
                "searchText": ""
            }
            try:
                logger.info(f"Fetching API page offset={offset}")
                response = session.post(self.api_url, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                total = data.get('total', 0)
                postings = data.get('jobPostings', [])

                if not postings:
                    logger.info(f"No more postings at offset {offset}")
                    break

                logger.info(f"API returned {len(postings)} postings (total: {total})")

                for posting in postings:
                    try:
                        title = posting.get('title', '')
                        if not title:
                            continue

                        external_path = posting.get('externalPath', '')
                        apply_url = f"{self.base_job_url}{external_path}" if external_path else self.url
                        location = posting.get('locationsText', '')
                        posted_date = posting.get('postedOn', '')
                        bullet_fields = posting.get('bulletFields', [])
                        job_id = self._extract_job_id(external_path, bullet_fields, title)
                        if not job_id:
                            logger.warning(f"Skipping job without scraped job_id: {title}")
                            continue
                        remote_type = posting.get('remoteType', '')
                        employment_type = ''
                        for field in bullet_fields:
                            if isinstance(field, str):
                                field_clean = field.strip()
                                if ('On-site' in field_clean or 'Remote' in field_clean or
                                        'Hybrid' in field_clean):
                                    if not remote_type:
                                        remote_type = field_clean
                                elif ('Full' in field_clean or 'Part' in field_clean or
                                      'Contract' in field_clean or 'Intern' in field_clean):
                                    employment_type = field_clean

                        detail_data = self._fetch_job_details(session, apply_url)
                        list_loc = self.parse_location(location)
                        detail_loc = {
                            'city': detail_data.get('city', ''),
                            'state': detail_data.get('state', ''),
                            'country': detail_data.get('country', ''),
                        }

                        city = detail_loc.get('city', '') or list_loc.get('city', '')
                        state = detail_loc.get('state', '') or list_loc.get('state', '')
                        country = detail_loc.get('country', '') or list_loc.get('country', '')
                        formatted_location = self._format_location(city, state, country) or self._clean_text(location)

                        all_jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'job_id': job_id,
                            'company_name': self.company_name,
                            'title': title,
                            'description': detail_data.get('description', ''),
                            'location': formatted_location,
                            'city': city,
                            'state': state,
                            'country': country,
                            'employment_type': detail_data.get('employment_type', '') or employment_type,
                            'department': detail_data.get('department', ''),
                            'apply_url': apply_url,
                            'posted_date': detail_data.get('posted_date', '') or posted_date,
                            'job_function': '',
                            'experience_level': detail_data.get('experience_level', ''),
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        })
                        time.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Error processing posting: {str(e)}")
                        continue

                offset += limit
                if offset >= total:
                    logger.info(f"Fetched all {total} available jobs")
                    break
            except Exception as e:
                logger.error(f"API request failed at offset {offset}: {str(e)}")
                break

        logger.info(f"Total jobs scraped: {len(all_jobs)}")
        return all_jobs

# Updated: Switched from Selenium-based scraping to Spire2Grow REST API
# The Myntra careers site (jobs.myntra.com) is a Flutter Web SPA powered by
# the Spire2Grow career portal platform. Flutter renders to HTML/canvas which
# makes DOM extraction unreliable. Instead, we call the same REST API that
# the Flutter app uses internally.
import requests
import hashlib
import re
from datetime import datetime

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE

logger = setup_logger('myntra_scraper')

# Spire2Grow API backing the Flutter Web SPA at jobs.myntra.com
API_BASE = 'https://io.spire2grow.com/ies/v1/p'
WORKSPACE_ID = 'MYNTRA-93as3'
PAGE_SIZE = 20


class MyntraScraper:
    def __init__(self):
        self.company_name = "Myntra"
        self.url = "https://jobs.myntra.com/home"  # kept for reference / apply_url fallback
        self.api_search_url = f'{API_BASE}/requisition/_search'
        self.api_count_url = f'{API_BASE}/requisition/_count'
        self.headers = {
            'Content-Type': 'application/json',
            'WorkspaceId': WORKSPACE_ID,
            'language': 'en',
            'Referer': 'https://jobs.myntra.com/',
            'Origin': 'https://jobs.myntra.com',
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def generate_external_id(self, job_id, company):
        """Generate a stable external ID from company + job identifier."""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    @staticmethod
    def _strip_html(html_str):
        """Remove HTML tags and collapse whitespace."""
        if not html_str:
            return ''
        text = re.sub(r'<[^>]+>', ' ', html_str)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _format_experience(exp_obj):
        """Convert requiredExperienceInMonths object to a human-readable string."""
        if not exp_obj:
            return ''
        from_months = exp_obj.get('from', 0) or 0
        to_months = exp_obj.get('to', 0) or 0
        from_years = from_months // 12
        to_years = to_months // 12
        if from_years and to_years:
            return f'{from_years}-{to_years} years'
        if from_years:
            return f'{from_years}+ years'
        if to_years:
            return f'0-{to_years} years'
        return ''

    @staticmethod
    def _format_employment_type(raw):
        """Normalise the employmentType value coming from the API."""
        if not raw:
            return ''
        mapping = {
            'FULL_TIME': 'Full-time',
            'PART_TIME': 'Part-time',
            'CONTRACT': 'Contract',
            'INTERNSHIP': 'Internship',
            'TEMPORARY': 'Temporary',
        }
        return mapping.get(raw.upper(), raw.replace('_', ' ').title())

    @staticmethod
    def _epoch_to_date(epoch_ms):
        """Convert epoch milliseconds to YYYY-MM-DD string."""
        if not epoch_ms:
            return ''
        try:
            return datetime.utcfromtimestamp(epoch_ms / 1000).strftime('%Y-%m-%d')
        except Exception:
            return ''

    # ------------------------------------------------------------------
    # Core scraping logic
    # ------------------------------------------------------------------
    def _get_total_count(self):
        """Hit the count endpoint to know the total number of active jobs."""
        try:
            resp = requests.get(
                self.api_count_url,
                headers=self.headers,
                timeout=SCRAPE_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get('totalCount', 0)
        except Exception as e:
            logger.warning(f"Could not fetch job count: {e}")
            return 0

    def _fetch_page(self, page):
        """Fetch a single page of job requisitions from the Spire2Grow API."""
        params = {
            'page': page,
            'size': PAGE_SIZE,
            'selectedSortOrder': 'desc',
            'selectedSortField': 'postedOn',
        }
        resp = requests.get(
            self.api_search_url,
            headers=self.headers,
            params=params,
            timeout=SCRAPE_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape all Myntra jobs from the Spire2Grow API with pagination."""
        all_jobs = []

        try:
            total_count = self._get_total_count()
            logger.info(f"Myntra reports {total_count} total active jobs")

            page = 1
            while page <= max_pages:
                logger.info(f"Fetching page {page} (size={PAGE_SIZE})")
                data = self._fetch_page(page)
                entities = data.get('entities', [])

                if not entities:
                    logger.info(f"No more entities on page {page}, stopping")
                    break

                for job in entities:
                    try:
                        parsed = self._parse_job(job)
                        if parsed:
                            all_jobs.append(parsed)
                    except Exception as e:
                        logger.error(f"Error parsing job: {e}")
                        continue

                logger.info(f"Parsed {len(entities)} jobs from page {page}")

                # Stop early when we've fetched everything
                if len(all_jobs) >= total_count:
                    break

                page += 1

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {e}")
            raise

        logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")
        return all_jobs

    # ------------------------------------------------------------------
    # Job parsing
    # ------------------------------------------------------------------
    def _parse_job(self, job):
        """Transform a single API entity into the standard job dict."""
        title = job.get('jobTitle', '').strip()
        if not title:
            return None

        # IDs
        display_id = job.get('displayId', '')
        internal_id = job.get('id', display_id)
        job_id = display_id or internal_id

        # Location
        locations = job.get('jobLocation', [])
        if locations:
            loc = locations[0]
            city = loc.get('city', '')
            state = loc.get('state', '')
            country = loc.get('country', 'India')
            location = loc.get('fqLocationName', '')
            if not location:
                location = ', '.join(filter(None, [city, state, country]))
        else:
            city, state, country, location = '', '', 'India', ''

        # Description (HTML -> plain text, capped at 5000 chars)
        description = self._strip_html(job.get('jobDescription', ''))[:5000]

        # Department — strip the internal code suffix like "(F1121)"
        department_raw = job.get('departmentName', '')
        department = re.sub(r'\s*\(F\d+\)\s*$', '', department_raw).strip()

        # Employment type
        employment_type = self._format_employment_type(job.get('employmentType', ''))

        # Posted date
        posted_epoch = (job.get('jobPosting') or {}).get('startDate')
        posted_date = self._epoch_to_date(posted_epoch)

        # Experience
        experience_level = self._format_experience(job.get('requiredExperienceInMonths'))

        # Skills as a comma-separated string (useful as job_function)
        skills = job.get('skills', [])
        skills_str = ', '.join(
            s.get('skill', '') for s in skills if s.get('skill')
        )

        # Apply URL — deep-link into the Flutter SPA
        apply_url = f"https://jobs.myntra.com/jobDescription/{display_id}" if display_id else self.url

        return {
            'external_id': self.generate_external_id(str(job_id), self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': description,
            'location': location,
            'city': city,
            'state': state,
            'country': country,
            'employment_type': employment_type,
            'department': department,
            'apply_url': apply_url,
            'posted_date': posted_date,
            'job_function': skills_str,
            'experience_level': experience_level,
            'salary_range': '',
            'remote_type': '',
            'status': 'active',
        }

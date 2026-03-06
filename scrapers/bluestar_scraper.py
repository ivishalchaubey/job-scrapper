import hashlib
import json

try:
    import requests
except ImportError:
    requests = None

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('bluestar_scraper')


class BlueStarScraper:
    def __init__(self):
        self.company_name = 'Blue Star'
        self.url = 'https://bluestar.workline.hr/CPortal/GeneralOpening.aspx'
        self.base_url = 'https://bluestar.workline.hr'
        self.api_url = 'https://bluestar.workline.hr/CPortal/GeneralOpening.aspx/GetCurrentopening'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Blue Star jobs via the Workline HR ASP.NET AJAX API.

        The Workline HR platform loads jobs via a server-side WebMethod
        (GetCurrentopening) that returns JSON with obj1 containing all
        job listings. We call this directly with requests, bypassing
        the JS alert issue in the browser.
        """
        all_jobs = []

        if requests is None:
            logger.error("requests library not available, cannot scrape Blue Star")
            return all_jobs

        try:
            all_jobs = self._scrape_via_api(max_pages)
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")

        logger.info(f"Total jobs scraped: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_api(self, max_pages):
        """Call the Workline HR GetCurrentopening WebMethod directly."""
        all_jobs = []
        scraped_ids = set()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
            'Referer': self.url,
        }

        payload = {
            'JDFileName': '',
            'OrgCode': '',
            'KeyName': '',
            'Type': 'D',
            'StateCode': '',
        }

        logger.info(f"Calling Workline HR API: {self.api_url}")

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"API request failed: {str(e)}")
            return all_jobs

        d = data.get('d', {})
        if not isinstance(d, dict):
            logger.error("Unexpected API response format")
            return all_jobs

        try:
            obj1_raw = d.get('obj1', '[]')
            obj1 = json.loads(obj1_raw) if isinstance(obj1_raw, str) else obj1_raw
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse obj1 JSON: {str(e)}")
            return all_jobs

        if not obj1:
            logger.warning("No jobs in API response")
            return all_jobs

        logger.info(f"API returned {len(obj1)} total job listings")

        # Apply pagination limit
        per_page = 20
        max_items = max_pages * per_page

        for idx, item in enumerate(obj1):
            if idx >= max_items:
                logger.info(f"Reached max_pages limit ({max_pages} pages, {max_items} items)")
                break

            job = self._parse_job(item)
            if job and job['external_id'] not in scraped_ids:
                all_jobs.append(job)
                scraped_ids.add(job['external_id'])

        return all_jobs

    def _parse_job(self, item):
        """Parse a single job from the Workline HR API response."""
        if not isinstance(item, dict):
            return None

        title = (item.get('Position_Name', '') or '').strip()
        if not title or len(title) < 3:
            return None

        # Build job ID from ERFCode or Req_No
        erf_code = str(item.get('ERFCode', '') or item.get('ERF_Code', ''))
        req_no = str(item.get('Req_No', ''))
        job_id = erf_code or req_no
        if not job_id:
            job_id = hashlib.md5(title.encode()).hexdigest()[:12]

        # Location
        city = (item.get('City_Name', '') or item.get('LOCATIONNAME', '') or '').strip()
        state = (item.get('state_name', '') or item.get('State', '') or '').strip()
        country = (item.get('Country_Name', '') or '').strip() or 'India'

        location_parts = [p for p in [city, state, country] if p]
        location = ', '.join(location_parts)

        # Build apply URL from TrackToken
        track_token = item.get('TrackToken', '')
        search_keyword = item.get('SearchKeyWord', '')
        if track_token and search_keyword:
            apply_url = f"{self.base_url}/CandidatePortal/{track_token}/{search_keyword}"
        else:
            apply_url = self.url

        # Department
        department = (item.get('Field1', '') or item.get('business_name', '') or '').strip()
        company_name_field = (item.get('Company_Name', '') or '').strip()

        # Experience
        exp_from = item.get('JobExp_from', 0)
        exp_to = item.get('JobExp_To', 0)
        experience = ''
        if exp_from or exp_to:
            # Convert months to years
            from_years = exp_from // 12 if isinstance(exp_from, int) else 0
            to_years = exp_to // 12 if isinstance(exp_to, int) else 0
            if from_years and to_years:
                experience = f"{from_years}-{to_years} years"
            elif to_years:
                experience = f"Up to {to_years} years"

        # Posted date
        posted_date = (item.get('PublishDate', '') or '').strip()
        time_diff = (item.get('TimeDiff', '') or '').strip()

        return {
            'external_id': self.generate_external_id(job_id, self.company_name),
            'company_name': self.company_name,
            'title': title,
            'description': '',
            'location': location,
            'city': city,
            'state': state,
            'country': country,
            'employment_type': '',
            'department': department or company_name_field,
            'apply_url': apply_url,
            'posted_date': posted_date or time_diff,
            'job_function': '',
            'experience_level': experience,
            'salary_range': '',
            'remote_type': '',
            'status': 'active'
        }

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
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = BlueStarScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

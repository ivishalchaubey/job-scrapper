import hashlib
import html
import json
import re
import subprocess
import uuid
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    requests = None

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE, HEADLESS_MODE
from scrapers.csv_url_resolver import get_company_url

logger = setup_logger('ey_scraper')

class EYScraper:
    def __init__(self):
        self.company_name = "EY"
        default_url = "https://eyglobal.yello.co/job_boards/c1riT--B2O-KySgYWsZO1Q?locale=en"
        raw_url = get_company_url(self.company_name, default_url)
        self.url = self._normalize_url(raw_url, default_url)

        match = re.search(r'/job_boards/([^?\s/]+)', self.url)
        self.job_board_id = match.group(1) if match else "c1riT--B2O-KySgYWsZO1Q"
        self.base_url = "https://eyglobal.yello.co"
        self.search_url = f"{self.base_url}/job_boards/{self.job_board_id}/search"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def _normalize_url(self, raw_url, fallback_url):
        candidates = [line.strip() for line in (raw_url or '').splitlines() if line.strip()]
        for candidate in candidates:
            if candidate.startswith('http'):
                return candidate
        return fallback_url

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        seen_external_ids = set()
        tab_id = str(uuid.uuid4())

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            logger.info(f"Using EY search URL: {self.search_url}")

            for page in range(1, max_pages + 1):
                params = {
                    'query': '',
                    'filters': '',
                    'job_board_tab_identifier': tab_id,
                    'locale': 'en',
                }
                if page > 1:
                    params['page_number'] = page

                payload = self._fetch_json(self.search_url, params=params)
                if not payload:
                    logger.warning(f"No EY payload for page {page}; stopping")
                    break

                html_block = payload.get('html', '')
                if not html_block:
                    logger.warning(f"No EY listing HTML for page {page}; stopping")
                    break

                page_jobs = self._parse_listing_html(html_block)
                new_count = 0
                for job in page_jobs:
                    ext_id = job.get('external_id')
                    if not ext_id or ext_id in seen_external_ids:
                        continue
                    seen_external_ids.add(ext_id)
                    jobs.append(job)
                    new_count += 1

                logger.info(f"Page {page}: scraped {len(page_jobs)} jobs, {new_count} new. Total: {len(jobs)}")

                if not payload.get('more_requisitions'):
                    logger.info("EY endpoint indicates no more pages")
                    break

                if payload.get('count_on_page', 0) == 0:
                    logger.info("EY endpoint returned zero jobs on this page")
                    break

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
            return jobs

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            return jobs

    def _parse_listing_html(self, html_block):
        jobs = []
        item_pattern = re.compile(r'<li class="search-results__item">(.*?)</li>', re.DOTALL)

        for block in item_pattern.findall(html_block):
            try:
                title_match = re.search(
                    r'<a class="search-results__req_title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    block,
                    flags=re.DOTALL,
                )
                if not title_match:
                    continue

                raw_href = html.unescape(title_match.group(1).strip())
                raw_title = title_match.group(2)
                title = self._strip_html(raw_title)
                if not title:
                    continue

                job_id_match = re.search(r'<span>(\d+)</span>', block)
                job_id = job_id_match.group(1) if job_id_match else hashlib.md5(raw_href.encode()).hexdigest()[:12]

                apply_url = self._to_abs_url(raw_href)

                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'job_id': job_id,
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': '',
                    'city': '',
                    'state': '',
                    'country': '',
                    'employment_type': '',
                    'department': '',
                    'apply_url': apply_url,
                    'posted_date': '',
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active',
                }

                details = self._fetch_job_details(apply_url)
                if details:
                    job_data.update(details)

                jobs.append(job_data)
            except Exception as e:
                logger.debug(f"Error parsing EY listing item: {str(e)}")
                continue

        return jobs

    def _fetch_job_details(self, job_url):
        details = {}
        page = self._fetch_text(job_url)
        if not page:
            return details

        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', page, flags=re.DOTALL)
        if title_match:
            title = self._strip_html(title_match.group(1))
            if title:
                details['title'] = title

        desc_match = re.search(
            r'<section class="job-details__description[^>]*>\s*<div class="inner[^>]*">(.*?)</div>\s*</section>',
            page,
            flags=re.DOTALL,
        )
        if desc_match:
            description = self._clean_rich_text(desc_match.group(1))
            if description:
                details['description'] = description

        spans = re.findall(r'<div class="details-top__title">(.*?)</div>', page, flags=re.DOTALL)
        if spans:
            top_block = spans[0]
            top_spans = re.findall(r'<span>(.*?)</span>', top_block, flags=re.DOTALL)
            # Usually: requisition id then location token like IND-Noida
            if len(top_spans) >= 2:
                loc_candidate = self._strip_html(top_spans[1])
                if loc_candidate:
                    details['location'] = loc_candidate
                    city, state, country = self.parse_location(loc_candidate)
                    details['city'] = city
                    details['state'] = state
                    details['country'] = country

        group_pattern = re.compile(
            r'<div class="secondary-details__group">\s*<span class="secondary-details__title">(.*?)</span>\s*<span class="secondary-details__content">(.*?)</span>\s*</div>',
            re.DOTALL,
        )
        for raw_label, raw_value in group_pattern.findall(page):
            label = self._strip_html(raw_label).lower()
            value = self._strip_html(raw_value)
            if not value:
                continue
            if 'service line' in label or 'business area' in label:
                details['department'] = value
            elif 'country' in label and not details.get('country'):
                details['country'] = value

        return details

    def parse_location(self, location_str):
        if not location_str:
            return '', '', ''

        cleaned = location_str.strip()
        if cleaned.upper().startswith('IND-'):
            city = cleaned.split('-', 1)[1].strip() if '-' in cleaned else ''
            return city, '', 'India'

        parts = [p.strip() for p in cleaned.split(',') if p.strip()]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        country = parts[-1] if len(parts) >= 3 else ''
        return city, state, country

    def _to_abs_url(self, href):
        if href.startswith('http://') or href.startswith('https://'):
            return href
        if href.startswith('/'):
            return self.base_url + href
        return self.base_url + '/' + href

    def _clean_rich_text(self, value):
        text = html.unescape(value)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<li[^>]*>', '\n- ', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'[ \t\r\f\v]+', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        return text.strip()[:15000]

    def _strip_html(self, value):
        text = html.unescape(value)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _fetch_json(self, url, params=None):
        body = self._fetch_text(url, params=params)
        if not body:
            return None
        try:
            return json.loads(body)
        except Exception as e:
            logger.warning(f"EY JSON parse failed: {str(e)}")
            return None

    def _fetch_text(self, url, params=None):
        if requests is not None:
            try:
                response = requests.get(url, params=params, timeout=SCRAPE_TIMEOUT)
                if response.status_code == 200:
                    return response.text
                logger.debug(f"requests.get returned {response.status_code} for {url}")
            except Exception as e:
                logger.debug(f"requests.get failed for {url}: {str(e)}")

        curl_cmd = ['curl', '-s']
        final_url = url
        if params:
            query = urlencode(params, doseq=True)
            separator = '&' if '?' in final_url else '?'
            final_url = f"{final_url}{separator}{query}"
        curl_cmd.append(final_url)

        try:
            proc = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=SCRAPE_TIMEOUT)
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except Exception as e:
            logger.debug(f"curl failed for {url}: {str(e)}")

        return ''

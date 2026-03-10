import hashlib
import time

import requests

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('autodesk_scraper')


class AutodeskScraper:
    def __init__(self):
        self.company_name = "Autodesk"
        self.url = "https://autodesk.wd1.myworkdayjobs.com/Ext?_gl=1*1oqsxil*_gcl_au*MTgxNzc2NTUxMy4xNzcxNDk3MzE0*_ga*MTUyMTAyMzU2MC4xNzcxNDk3MzEz*_ga_NZSJ72N6RX*czE3NzE0OTczMTMkbzEkZzEkdDE3NzE0OTczMTMkajYwJGwwJGgw&State_Region=701eb5584934425d930bc84b9e8b04eb&State_Region=a3c37012f51642f4a7b3dafc8ac37801"
        self.api_url = 'https://autodesk.wd1.myworkdayjobs.com/wday/cxs/autodesk/Ext/jobs'
        self.base_job_url = 'https://autodesk.wd1.myworkdayjobs.com/Ext'

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
        if len(parts) == 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        limit = 20
        max_results = max_pages * limit

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        }

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
                response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
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

                        job_id = ''
                        if external_path:
                            parts = external_path.strip('/').split('/')
                            if parts:
                                job_id = parts[-1]
                        if not job_id:
                            job_id = f"autodesk_{hashlib.md5(title.encode()).hexdigest()[:12]}"

                        bullet_fields = posting.get('bulletFields', [])
                        remote_type = ''
                        employment_type = ''
                        for field in bullet_fields:
                            if isinstance(field, str):
                                if 'On-site' in field or 'Remote' in field or 'Hybrid' in field:
                                    remote_type = field
                                elif 'Full' in field or 'Part' in field or 'Contract' in field:
                                    employment_type = field

                        location_parts = self.parse_location(location)

                        all_jobs.append({
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': location_parts.get('city', ''),
                            'state': location_parts.get('state', ''),
                            'country': location_parts.get('country', 'India'),
                            'employment_type': employment_type,
                            'department': '',
                            'apply_url': apply_url,
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        })

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

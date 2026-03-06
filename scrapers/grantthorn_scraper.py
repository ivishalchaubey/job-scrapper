import requests
import hashlib
import json
import base64
import time

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('grantthorn_scraper')

# TalentRecruit NaCl encryption keys (from career page JS source)
# These are public constants embedded in the client-side JavaScript bundle
_NACL_SERVER_PK = bytes([242, 8, 47, 175, 149, 35, 187, 175, 15, 102, 147, 108,
                         250, 50, 59, 103, 116, 38, 49, 216, 28, 239, 57, 194,
                         136, 144, 66, 131, 175, 53, 235, 118])
_NACL_CLIENT_SK = bytes([98, 89, 42, 106, 113, 112, 94, 50, 73, 100, 114, 53,
                         108, 83, 52, 52, 87, 73, 89, 98, 75, 56, 121, 90,
                         57, 86, 68, 86, 94, 68, 85, 113])

PAGE_SIZE = 25


class GrantThorntonScraper:
    def __init__(self):
        self.company_name = 'Grant Thornton'
        self.url = 'https://gtprod.talentrecruit.com/career-page'
        self.base_url = 'https://gtprod.talentrecruit.com'
        self.api_url = 'https://app.api.talentrecruit.com/api/v1/career/template/job/list'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'shortname': 'https://gtprod.talentrecruit.com',
            'Referer': 'https://appcareer.talentrecruit.com/career-page/?sortName=gtprod',
            'Origin': 'https://appcareer.talentrecruit.com',
        })

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
            result['country'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result

    def _decrypt_response(self, encrypted_data):
        """Decrypt NaCl box-encrypted API response from TalentRecruit."""
        try:
            from nacl.public import PrivateKey, PublicKey, Box

            ciphertext = base64.b64decode(encrypted_data['text'])
            nonce = base64.b64decode(encrypted_data['key'])
            sender_pk = base64.b64decode(encrypted_data['iv'])

            private_key = PrivateKey(_NACL_CLIENT_SK)
            public_key = PublicKey(sender_pk)
            box = Box(private_key, public_key)
            plaintext = box.decrypt(ciphertext, nonce)
            return json.loads(plaintext.decode('utf-8'))
        except ImportError:
            logger.error("PyNaCl not installed. Run: pip install pynacl")
            return None
        except Exception as e:
            logger.error(f"Decryption error: {str(e)}")
            return None

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        try:
            logger.info(f"Starting {self.company_name} scraping via TalentRecruit API")

            offset = 0
            for page in range(1, max_pages + 1):
                url = f"{self.api_url}?limit={PAGE_SIZE}&offset={offset}"
                logger.info(f"Fetching page {page} (offset={offset}): {url}")

                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                encrypted = response.json()

                # TalentRecruit encrypts all API responses with NaCl
                if not isinstance(encrypted, dict) or 'text' not in encrypted:
                    logger.warning("Unexpected response format (not encrypted)")
                    break

                result = self._decrypt_response(encrypted)
                if not result:
                    logger.error("Failed to decrypt API response")
                    break

                # Navigate nested structure: result.data.data.data
                inner_data = result.get('data', {}).get('data', {})
                total_count = inner_data.get('noOfTotalRecords', {}).get('count', 0)
                job_list = inner_data.get('data', [])

                if page == 1:
                    logger.info(f"Total jobs available: {total_count}")

                if not job_list:
                    logger.info(f"No more jobs on page {page}, stopping.")
                    break

                page_jobs = self._extract_jobs(job_list)
                all_jobs.extend(page_jobs)
                logger.info(f"Page {page}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

                # Check if we've fetched all available jobs
                if len(all_jobs) >= total_count:
                    break

                offset += PAGE_SIZE
                if page < max_pages:
                    time.sleep(1)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")

        return all_jobs

    def _extract_jobs(self, job_list):
        """Parse job objects from decrypted API response."""
        jobs = []
        seen_codes = set()

        for item in job_list:
            if not isinstance(item, dict):
                continue

            title = (item.get('title') or '').strip()
            if not title or len(title) < 3:
                continue

            # Use job code for deduplication (unique per requisition)
            code = str(item.get('code', '')).strip()
            if code in seen_codes:
                continue
            if code:
                seen_codes.add(code)

            city = (item.get('city') or item.get('joblocation') or '').strip()
            state = (item.get('state') or '').strip()
            country = (item.get('country') or 'India').strip()

            # Build location string
            location_parts = []
            if city:
                location_parts.append(city)
            if state and state != city:
                location_parts.append(state)
            if country and country != 'India':
                location_parts.append(country)
            location = ', '.join(location_parts) if location_parts else ''

            department = (item.get('name') or '').strip()  # 'name' = department name
            published = (item.get('publishedtime') or '').strip()

            # Experience range
            exp_from = item.get('experiencefrom', '')
            exp_to = item.get('experienceto', '')
            experience = ''
            if exp_from or exp_to:
                exp_from_str = str(exp_from).replace('.00', '') if exp_from else ''
                exp_to_str = str(exp_to).replace('.00', '') if exp_to else ''
                if exp_from_str and exp_to_str:
                    experience = f"{exp_from_str}-{exp_to_str} years"
                elif exp_from_str:
                    experience = f"{exp_from_str}+ years"

            # Remote job flag
            is_remote = item.get('isremotejob', False)
            remote_type = 'Remote' if is_remote else ''

            # Build apply URL using the career page with job code
            apply_url = f"{self.url}?jobid={code}" if code else self.url

            # Build description from available fields
            desc_parts = []
            if item.get('description'):
                desc_parts.append(item['description'].strip())
            if item.get('qualificationcriteria'):
                desc_parts.append(f"Qualifications: {item['qualificationcriteria'].strip()}")
            if item.get('additionalinformation'):
                desc_parts.append(f"Additional Info: {item['additionalinformation'].strip()}")
            description = ' | '.join(desc_parts)

            # Job type
            employment_type = ''
            job_nature = item.get('jobnatureid', '')
            if job_nature:
                employment_type = str(job_nature)

            job_id = code if code else hashlib.md5(title.encode()).hexdigest()[:12]

            jobs.append({
                'external_id': self.generate_external_id(job_id, self.company_name),
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
                'posted_date': published,
                'job_function': department,
                'experience_level': experience,
                'salary_range': '',
                'remote_type': remote_type,
                'status': 'active'
            })

        return jobs


if __name__ == "__main__":
    scraper = GrantThorntonScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

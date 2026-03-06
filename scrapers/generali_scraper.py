import requests
import hashlib
import time

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('generali_scraper')


class GeneraliScraper:
    def __init__(self):
        self.company_name = 'Generali'
        self.url = 'https://www.generalicentralinsurance.com/current-openings'
        self.base_url = 'https://www.generalicentralinsurance.com'
        self.api_url = 'https://www.generalicentralinsurance.com/content/futuregeneraliindiainsurancecoltd/api/mdm/job-role.json'

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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        try:
            logger.info(f"Starting {self.company_name} scraping via API: {self.api_url}")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Content-Type': 'application/json',
                'Referer': 'https://www.generalicentralinsurance.com/current-openings',
                'Origin': 'https://www.generalicentralinsurance.com',
                'Accept': 'application/json, text/plain, */*',
            }

            payload = {
                'requestJson': {
                    'searchData': ''
                }
            }

            response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            master_list = data.get('Master', [])
            if not master_list:
                logger.warning("API returned no jobs in Master array")
                return all_jobs

            logger.info(f"API returned {len(master_list)} job entries")

            seen_keys = set()
            for job_data in master_list:
                title = job_data.get('job-title', '').strip()
                if not title or len(title) < 3:
                    continue

                city = job_data.get('city', '').strip()
                state = job_data.get('state', '').strip()
                location = job_data.get('location', '').strip()
                category = job_data.get('category', '').strip()
                job_function = job_data.get('job-function', '').strip()
                post_date = job_data.get('job-post-date', '').strip()
                email = job_data.get('email-id', '').strip()
                experience = job_data.get('work-experience', '').strip()
                education = job_data.get('education', '').strip()

                # Build a full location string
                location_parts = []
                if city:
                    location_parts.append(city)
                if state and state != city:
                    location_parts.append(state)
                full_location = ', '.join(location_parts) if location_parts else location

                # Create unique key from title + location to deduplicate
                dedup_key = f"{title}|{full_location}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                job_id = hashlib.md5(dedup_key.encode()).hexdigest()[:12]

                # Build apply URL using the same pattern the site uses
                title_slug = title.replace(' ', '-')
                apply_url = f"{self.base_url}/content/futuregeneraliindiainsurancecoltd/us/en/share-cv.html?jobrole={title_slug}"

                # Build description from available fields
                desc_parts = []
                if job_data.get('purpose-of-role', '').strip():
                    desc_parts.append(f"Purpose: {job_data['purpose-of-role'].strip()}")
                if education:
                    desc_parts.append(f"Education: {education}")
                if experience:
                    desc_parts.append(f"Experience: {experience}")
                description = ' | '.join(desc_parts)

                all_jobs.append({
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': description,
                    'location': full_location,
                    'city': city,
                    'state': state,
                    'country': 'India',
                    'employment_type': category,
                    'department': job_function,
                    'apply_url': apply_url,
                    'posted_date': post_date,
                    'job_function': job_function,
                    'experience_level': experience,
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                })

            logger.info(f"Total jobs scraped: {len(all_jobs)}")

        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")

        return all_jobs


if __name__ == "__main__":
    scraper = GeneraliScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

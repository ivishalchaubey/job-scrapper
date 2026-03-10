import requests
import hashlib
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('easemytrip_scraper')


class EaseMyTripScraper:
    def __init__(self):
        self.company_name = "EaseMyTrip"
        self.url = "https://www.easemytrip.com/career.html#work"
        self.base_url = 'https://www.easemytrip.com'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

    def generate_external_id(self, job_id, company):
        """Generate stable external ID."""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        """Parse location string into dict with city, state, country."""
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        location_str = location_str.strip()
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
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from EaseMyTrip static HTML career page."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Primary selector: div.jobs container with div.jb-item rows
            jobs_container = soup.select_one('div.jobs')
            if jobs_container:
                job_items = jobs_container.select('div.jb-item')
            else:
                # Fallback: try direct selection
                job_items = soup.select('div.jb-item')

            if not job_items:
                # Broader fallback
                job_items = soup.select('[class*="jb-item"], [class*="job-item"], [class*="career-item"]')

            logger.info(f"Found {len(job_items)} job items on page")

            for idx, item in enumerate(job_items):
                try:
                    # Extract fields from div.w-33 children
                    w33_divs = item.select('div.w-33')

                    title = ''
                    location = ''
                    experience = ''

                    if len(w33_divs) >= 1:
                        title = w33_divs[0].get_text(strip=True)
                    if len(w33_divs) >= 2:
                        location = w33_divs[1].get_text(strip=True)
                    if len(w33_divs) >= 3:
                        experience = w33_divs[2].get_text(strip=True)

                    # If w-33 divs not found, try other approaches
                    if not title:
                        # Try first child div or span for title
                        title_el = item.select_one('h3, h4, [class*="title"], strong, b')
                        if title_el:
                            title = title_el.get_text(strip=True)
                        else:
                            # Try first text content
                            children = item.find_all('div', recursive=False)
                            if children:
                                title = children[0].get_text(strip=True)

                    if not title:
                        continue

                    # Extract description from div.jobdetail
                    description = ''
                    detail_elem = item.select_one('div.jobdetail')
                    if detail_elem:
                        description = detail_elem.get_text(strip=True)
                    else:
                        detail_elem = item.select_one('[class*="jobdetail"], [class*="job-detail"], [class*="description"]')
                        if detail_elem:
                            description = detail_elem.get_text(strip=True)

                    # Extract any link for apply URL
                    href = ''
                    link_el = item.select_one('a[href]')
                    if link_el:
                        href = link_el.get('href', '')
                        if href and href.startswith('/'):
                            href = self.base_url + href

                    # Generate job ID
                    job_id = hashlib.md5((title + location).encode()).hexdigest()[:12]

                    external_id = self.generate_external_id(job_id, self.company_name)
                    if external_id in seen_ids:
                        continue

                    location_parts = self.parse_location(location)

                    job_data = {
                        'external_id': external_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': description,
                        'location': location,
                        'city': location_parts['city'],
                        'state': location_parts['state'],
                        'country': location_parts['country'],
                        'employment_type': '',
                        'department': '',
                        'apply_url': href if href else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    all_jobs.append(job_data)
                    seen_ids.add(external_id)
                    logger.info(f"Extracted: {title} | {location}")

                except Exception as e:
                    logger.error(f"Error parsing job item: {str(e)}")
                    continue

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs


if __name__ == "__main__":
    scraper = EaseMyTripScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['apply_url']}")

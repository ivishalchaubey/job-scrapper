import requests
from bs4 import BeautifulSoup
import hashlib
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('ferrero_scraper')


class FerreroScraper:
    def __init__(self):
        self.company_name = 'Ferrero'
        self.url = 'https://www.ferrerocareers.com/int/en/jobs'
        self.base_url = 'https://www.ferrerocareers.com'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'

    def _extract_job_id(self, job_url):
        """Extract job ID from a Ferrero career URL."""
        job_id = ''
        if '/job/' in job_url or '/jobs/' in job_url:
            parts = job_url.rstrip('/').split('/')
            for part in reversed(parts):
                if part.isdigit():
                    job_id = part
                    break
            if not job_id:
                # Try the last non-empty segment as a slug
                for part in reversed(parts):
                    if part and part != 'jobs' and part != 'job':
                        job_id = part
                        break
        if not job_id:
            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]
        return job_id

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Ferrero India jobs from the Drupal career site.

        The site at ferrerocareers.com uses a Drupal frontend. Job cards are
        structured as:
          div.views-row > article.node--type-job
            h3 > span.field--name-title  (job title)
            div.job-posting__data
              div.field--name-field-job-function  (department)
              div.field--name-field-id  (job ID)
            div.job-posting__summary
              div.location  (location)
              div.field--name-field-type-of-contract  (employment type)
            div.job-posting__link > a  (details link / job URL)

        Pagination uses page=0, page=1, etc.
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            seen_ids = set()

            for page in range(max_pages):
                params = {
                    'search_country': 'Ind',
                    'country[India]': 'India',
                    'page': page,
                }

                logger.info(f"Fetching page {page + 1} (page={page})")
                try:
                    response = self.session.get(self.url, params=params, timeout=30)
                    response.raise_for_status()
                except Exception as e:
                    logger.error(f"Failed to fetch page {page + 1}: {str(e)}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # Primary: Drupal views-row containers with article elements
                job_cards = soup.select('div.views-row')

                # Fallback: article elements with node--type-job class
                if not job_cards:
                    job_cards = soup.select('article.node--type-job')

                if not job_cards:
                    logger.info(f"No job cards found on page {page + 1}, stopping pagination")
                    break

                page_count = 0
                for card in job_cards:
                    try:
                        # Extract title from h3 > span.field--name-title
                        title_el = card.select_one('span.field--name-title')
                        if not title_el:
                            title_el = card.select_one('h3')
                        if not title_el:
                            continue

                        title = title_el.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue

                        # Extract job URL from the details link
                        detail_link = card.select_one('div.job-posting__link a')
                        if not detail_link:
                            detail_link = card.select_one('a[href*="/jobs/"]')
                        if not detail_link:
                            continue

                        href = detail_link.get('href', '')
                        if href and href.startswith('/'):
                            job_url = f"{self.base_url}{href}"
                        elif href and href.startswith('http'):
                            job_url = href
                        else:
                            continue

                        # Extract job ID from field--name-field-id or URL
                        job_id = ''
                        id_el = card.select_one('.field--name-field-id')
                        if id_el:
                            job_id = id_el.get_text(strip=True)
                        if not job_id:
                            job_id = self._extract_job_id(job_url)
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        # Location from div.location inside job-posting__summary
                        location = ''
                        loc_el = card.select_one('div.job-posting__summary div.location')
                        if not loc_el:
                            loc_el = card.select_one('div.location')
                        if loc_el:
                            location = loc_el.get_text(strip=True)

                        # Department from field--name-field-job-function
                        department = ''
                        dept_el = card.select_one('.field--name-field-job-function')
                        if dept_el:
                            department = dept_el.get_text(strip=True)

                        # Posted date
                        posted_date = ''
                        date_el = card.select_one('.job-date, .field--name-field-date, time')
                        if date_el:
                            posted_date = date_el.get_text(strip=True)
                            if not posted_date and date_el.get('datetime'):
                                posted_date = date_el.get('datetime', '')[:10]

                        # Employment type from field--name-field-type-of-contract
                        employment_type = ''
                        type_el = card.select_one('.field--name-field-type-of-contract')
                        if type_el:
                            employment_type = type_el.get_text(strip=True)

                        city, state, country = self.parse_location(location)

                        if location and 'india' not in location.lower():
                            location = f"{location}, India"
                        elif not location:
                            location = 'India'

                        # Remote type
                        remote_type = ''
                        if 'remote' in title.lower() or 'remote' in location.lower():
                            remote_type = 'Remote'
                        elif 'hybrid' in title.lower() or 'hybrid' in location.lower():
                            remote_type = 'Hybrid'

                        job = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city,
                            'state': state,
                            'country': 'India',
                            'employment_type': employment_type,
                            'department': department,
                            'apply_url': job_url,
                            'posted_date': posted_date,
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        }
                        jobs.append(job)
                        page_count += 1
                        logger.info(f"Extracted: {title} | {location} | {department}")
                    except Exception as e:
                        logger.warning(f"Error parsing job card: {str(e)}")
                        continue

                logger.info(f"Page {page + 1}: found {page_count} jobs (total: {len(jobs)})")

                if page_count == 0:
                    logger.info("No new jobs found on this page, stopping pagination")
                    break

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs


if __name__ == "__main__":
    scraper = FerreroScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

import requests
from bs4 import BeautifulSoup
import hashlib
from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('odoo_scraper')


class OdooScraper:
    def __init__(self):
        self.company_name = "Odoo"
        self.url = "https://www.odoo.com/jobs"
        self.base_url = 'https://www.odoo.com'
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Odoo jobs for India.

        Odoo's jobs page at odoo.com/jobs uses country_id parameter for filtering.
        IMPORTANT: country_id=101 is India (NOT 104, which is Iran).

        The HTML structure for each job card:
        - Container: div.card > a[href="/jobs/slug"]
        - Title: h3.text-900 inside div.x_wd_job_heading
        - Location: address.o_portal_address > span[itemprop="streetAddress"]
        - Department: span next to i.x_wd_icon_people
        - Open positions count: inside span.bg-200

        Pagination: /jobs/page/N?country_id=101
        """
        jobs = []
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            seen_ids = set()
            page = 0

            while page < max_pages:
                if page == 0:
                    fetch_url = f"{self.url}?country_id=101"
                else:
                    fetch_url = f"{self.url}/page/{page + 1}?country_id=101"

                logger.info(f"Fetching: {fetch_url}")
                try:
                    response = self.session.get(fetch_url, timeout=30)
                    response.raise_for_status()
                except Exception as e:
                    logger.warning(f"Failed to fetch {fetch_url}: {str(e)}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # Find job cards - each job is a div.card containing an anchor link
                job_cards = soup.select('div.card')
                if not job_cards:
                    # Try broader selectors
                    job_cards = soup.select('.oe_website_jobs .card, .o_jobs .card')

                # Filter to only cards with job links
                job_cards = [card for card in job_cards
                             if card.select_one('a[href*="/jobs/"]')]

                logger.info(f"Found {len(job_cards)} job card elements")

                if not job_cards:
                    # Check if page says "no open job opportunities"
                    page_text = soup.get_text()
                    if 'no open job' in page_text.lower():
                        logger.info("Page indicates no open positions")
                    break

                page_count = 0
                for card in job_cards:
                    try:
                        # Get the job link
                        link = card.select_one('a[href*="/jobs/"]')
                        if not link:
                            continue

                        href = link.get('href', '')
                        if not href or 'page' in href:
                            continue

                        if href.startswith('/'):
                            job_url = f"{self.base_url}{href}"
                        else:
                            job_url = href

                        # Extract job ID from URL slug (e.g., /jobs/business-support-analyst-1315)
                        slug = href.rstrip('/').split('/')[-1]
                        job_id = slug
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        # Title: h3 inside x_wd_job_heading
                        title = ''
                        title_el = card.select_one('div.x_wd_job_heading h3')
                        if not title_el:
                            title_el = card.select_one('h3.text-900')
                        if not title_el:
                            title_el = card.select_one('h3')
                        if title_el:
                            title = title_el.get_text(strip=True)

                        if not title or len(title) < 3:
                            continue

                        # Location: from address element with itemprop="streetAddress"
                        location = ''
                        addr_el = card.select_one('span[itemprop="streetAddress"]')
                        if addr_el:
                            location = addr_el.get_text(strip=True)
                        if not location:
                            addr_el = card.select_one('address.o_portal_address')
                            if addr_el:
                                location = addr_el.get_text(strip=True)

                        # Default location for Odoo India
                        if not location:
                            location = 'Gandhinagar, Gujarat, India'

                        # Department: text next to the people icon
                        department = ''
                        dept_container = card.select_one('i.x_wd_icon_people')
                        if dept_container and dept_container.parent:
                            # Get the span sibling text
                            dept_span = dept_container.find_next_sibling('span')
                            if dept_span:
                                department = dept_span.get_text(strip=True)
                            else:
                                # Try parent text minus icon
                                dept_text = dept_container.parent.get_text(strip=True)
                                if dept_text:
                                    department = dept_text

                        # Ensure India in location string
                        if 'india' not in location.lower():
                            location = f"{location}, India" if location else 'India'

                        city, state, country = self.parse_location(location)

                        job = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': '',
                            'location': location,
                            'city': city if city else 'Gandhinagar',
                            'state': state if state else 'Gujarat',
                            'country': 'India',
                            'employment_type': '',
                            'department': department,
                            'apply_url': job_url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }
                        jobs.append(job)
                        page_count += 1
                        logger.info(f"Extracted: {title} | {location} | {department}")
                    except Exception as e:
                        logger.warning(f"Error parsing job card: {str(e)}")
                        continue

                logger.info(f"Page {page + 1}: found {page_count} jobs (total: {len(jobs)})")

                # Check for next page link
                next_link = soup.select_one('a[href*="/jobs/page/"]')
                if not next_link:
                    logger.info("No next page link found")
                    break

                page += 1

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        return jobs


if __name__ == "__main__":
    scraper = OdooScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

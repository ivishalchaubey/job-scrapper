import requests
import hashlib
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('msctechnology_scraper')


class MSCTechnologyScraper:
    def __init__(self):
        self.company_name = "MSC Technology"
        self.url = "https://www.msc-technology.com/current-opening-india"
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
        """Scrape jobs from MSC Technology Drupal 10 site."""
        all_jobs = []
        seen_ids = set()

        try:
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Drupal 10 job articles
            job_articles = soup.select('article.node--type-jobs-in-india')

            if not job_articles:
                # Fallback: try broader selectors
                job_articles = soup.select('article[class*="node--type-job"]')

            if not job_articles:
                job_articles = soup.select('article.node')

            logger.info(f"Found {len(job_articles)} job articles on page")

            for article in job_articles:
                try:
                    # Extract title from div.field--name-title h2 a
                    # Note: the header h2.node__title > a is empty in Drupal 10 teaser view,
                    # the actual title text is inside div.field--name-title h2 a
                    title = ''
                    title_link = article.select_one('div.field--name-title h2 a')
                    if title_link:
                        title = title_link.get_text(strip=True)
                    else:
                        # Fallback: try any h2 a with text
                        for h2_a in article.select('h2 a'):
                            text = h2_a.get_text(strip=True)
                            if text:
                                title = text
                                title_link = h2_a
                                break
                        if not title:
                            title_el = article.select_one('div.field--name-title')
                            if title_el:
                                title = title_el.get_text(strip=True)

                    if not title:
                        continue

                    # Extract URL from the title link
                    href = ''
                    if title_link and title_link.get('href'):
                        href = title_link['href']
                        if href.startswith('/'):
                            href = 'https://www.msc-technology.com' + href

                    # Extract location from div.field--name-field-place .field__item
                    # Use .field__item to skip the label "Place"
                    location = ''
                    loc_item = article.select_one('div.field--name-field-place .field__item')
                    if loc_item:
                        location = loc_item.get_text(strip=True)
                    else:
                        loc_elem = article.select_one('div.field--name-field-place')
                        if loc_elem:
                            location = loc_elem.get_text(strip=True)

                    # Extract experience from div.field--name-field-experience .field__item
                    experience = ''
                    exp_item = article.select_one('div.field--name-field-experience .field__item')
                    if exp_item:
                        experience = exp_item.get_text(strip=True)
                    else:
                        exp_elem = article.select_one('div.field--name-field-experience')
                        if exp_elem:
                            experience = exp_elem.get_text(strip=True)

                    # Extract posted date from div.field--name-field-published-on1 time
                    posted_date = ''
                    date_elem = article.select_one('div.field--name-field-published-on1 time')
                    if date_elem:
                        posted_date = date_elem.get('datetime', '')
                        if posted_date:
                            posted_date = posted_date[:10]
                        else:
                            posted_date = date_elem.get_text(strip=True)

                    # Extract description from div.field--name-field-job-description
                    description = ''
                    desc_elem = article.select_one('div.field--name-field-job-description')
                    if desc_elem:
                        description = desc_elem.get_text(strip=True)

                    # Generate job ID from URL or title
                    if href:
                        job_id = hashlib.md5(href.encode()).hexdigest()[:12]
                    else:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    # Also try data-history-node-id or other Drupal attributes
                    node_id = article.get('data-history-node-id', '')
                    if node_id:
                        job_id = node_id

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
                        'posted_date': posted_date,
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
                    logger.error(f"Error parsing job article: {str(e)}")
                    continue

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs


if __name__ == "__main__":
    scraper = MSCTechnologyScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['apply_url']}")

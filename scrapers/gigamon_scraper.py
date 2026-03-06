import requests
import hashlib
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('gigamon_scraper')


class GigamonScraper:
    def __init__(self):
        self.company_name = 'Gigamon'
        self.url = 'https://jobs.jobvite.com/gigamon/search?intcid=careers-india'
        self.base_url = 'https://jobs.jobvite.com'
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
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 2:
            result['state'] = parts[1]
        if len(parts) >= 3:
            result['country'] = parts[2]
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        return result

    def _is_india_location(self, location_str):
        """Check if the location string indicates a job in India."""
        if not location_str:
            return False
        india_keywords = [
            'India', 'Bangalore', 'Bengaluru', 'Mumbai', 'Delhi',
            'Hyderabad', 'Chennai', 'Pune', 'Gurugram', 'Gurgaon',
            'Noida', 'Kolkata', 'Ahmedabad', 'Jaipur', 'Kochi',
            'Thiruvananthapuram', 'Chandigarh', 'Lucknow', 'Indore',
            'New Delhi', 'NCR', 'Coimbatore', 'Nagpur', 'Bhubaneswar',
        ]
        return any(kw.lower() in location_str.lower() for kw in india_keywords)

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Gigamon jobs from Jobvite platform (server-rendered HTML)."""
        all_jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name} from {self.url}")

            for page in range(1, max_pages + 1):
                page_url = self.url if page == 1 else f"{self.url}&p={page}"
                logger.info(f"Fetching page {page}: {page_url}")

                try:
                    response = self.session.get(page_url, timeout=30)
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request failed for page {page}: {str(e)}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # Jobvite renders job listings in a table or list structure
                # Look for job rows containing links to /gigamon/job/{id}
                job_rows = soup.select('table.jv-job-list tr.jv-job-list-name') or \
                           soup.select('tr.jv-job-list-name') or \
                           soup.select('li.jv-job-item')

                # If no structured elements found, try finding all job links
                if not job_rows:
                    job_links = soup.find_all('a', href=lambda h: h and '/gigamon/job/' in h)
                    if not job_links:
                        logger.info(f"No job listings found on page {page}, stopping pagination")
                        break

                    for link in job_links:
                        try:
                            title = link.get_text(strip=True)
                            if not title:
                                continue

                            href = link.get('href', '')
                            job_url = href if href.startswith('http') else f"{self.base_url}{href}"

                            # Extract job ID from the URL path
                            job_id = ''
                            if '/job/' in href:
                                path_parts = href.split('/job/')[-1].strip('/').split('/')
                                job_id = path_parts[0] if path_parts else ''
                            if not job_id:
                                job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                            # Try to find location in the parent or sibling elements
                            location = ''
                            parent_row = link.find_parent('tr') or link.find_parent('li') or link.find_parent('div')
                            if parent_row:
                                # Look for location column (typically second td or a span with location class)
                                location_el = parent_row.find('td', class_=lambda c: c and 'location' in c.lower()) or \
                                              parent_row.find('span', class_=lambda c: c and 'location' in c.lower())
                                if location_el:
                                    location = location_el.get_text(strip=True)
                                else:
                                    # Try all td elements - location is usually the second column
                                    tds = parent_row.find_all('td')
                                    if len(tds) >= 2:
                                        location = tds[1].get_text(strip=True)

                            # Find department if available
                            department = ''
                            if parent_row:
                                dept_el = parent_row.find('td', class_=lambda c: c and 'department' in c.lower()) or \
                                          parent_row.find('span', class_=lambda c: c and 'department' in c.lower())
                                if dept_el:
                                    department = dept_el.get_text(strip=True)
                                elif parent_row.find_all('td') and len(parent_row.find_all('td')) >= 3:
                                    department = parent_row.find_all('td')[2].get_text(strip=True)

                            # Filter for India jobs only
                            if not self._is_india_location(location):
                                continue

                            loc = self.parse_location(location)

                            job_data = {
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name,
                                'title': title,
                                'description': '',
                                'location': location,
                                'city': loc.get('city', ''),
                                'state': loc.get('state', ''),
                                'country': loc.get('country', 'India'),
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

                            all_jobs.append(job_data)
                            logger.info(f"Added job: {title} | {location}")

                        except Exception as e:
                            logger.error(f"Error processing job link: {str(e)}")
                            continue
                else:
                    # Process structured job rows
                    for row in job_rows:
                        try:
                            # Find the job title link
                            title_link = row.find('a', href=lambda h: h and '/gigamon/job/' in h) or \
                                         row.find('a')
                            if not title_link:
                                continue

                            title = title_link.get_text(strip=True)
                            if not title:
                                continue

                            href = title_link.get('href', '')
                            job_url = href if href.startswith('http') else f"{self.base_url}{href}"

                            job_id = ''
                            if '/job/' in href:
                                path_parts = href.split('/job/')[-1].strip('/').split('/')
                                job_id = path_parts[0] if path_parts else ''
                            if not job_id:
                                job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                            # Location from table cells or span elements
                            location = ''
                            tds = row.find_all('td')
                            if len(tds) >= 2:
                                location = tds[1].get_text(strip=True)
                            else:
                                loc_el = row.find(class_=lambda c: c and 'location' in str(c).lower())
                                if loc_el:
                                    location = loc_el.get_text(strip=True)

                            department = ''
                            if len(tds) >= 3:
                                department = tds[2].get_text(strip=True)

                            # Filter for India
                            if not self._is_india_location(location):
                                continue

                            loc = self.parse_location(location)

                            job_data = {
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name,
                                'title': title,
                                'description': '',
                                'location': location,
                                'city': loc.get('city', ''),
                                'state': loc.get('state', ''),
                                'country': loc.get('country', 'India'),
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

                            all_jobs.append(job_data)
                            logger.info(f"Added job: {title} | {location}")

                        except Exception as e:
                            logger.error(f"Error processing job row: {str(e)}")
                            continue

                # Check if there are more pages by looking for pagination links
                next_link = soup.find('a', class_='jv-page-next') or \
                            soup.find('a', text='Next') or \
                            soup.find('a', string='Next')
                if not next_link and page > 1:
                    logger.info("No next page link found, stopping pagination")
                    break

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Total India jobs found for {self.company_name}: {len(all_jobs)}")
        return all_jobs


if __name__ == "__main__":
    scraper = GigamonScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']} | {job['apply_url']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

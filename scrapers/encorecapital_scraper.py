import requests
import hashlib
import re
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('encorecapital_scraper')


class EncoreCapitalScraper:
    def __init__(self):
        self.company_name = 'Encore Capital Group'
        self.url = 'https://careers.encorecapital.com/en/search-jobs'
        self.base_url = 'https://careers.encorecapital.com'
        self.company_id = '29781'
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
        """Scrape Encore Capital Group jobs from TalentBrew / Radancy platform.

        Job links follow the pattern: /en/job/{city}/{title}/29781/{jobid}
        Pagination uses &p=N parameter.
        Filter for India jobs by checking location text.
        """
        all_jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name} from {self.url}")

            for page in range(1, max_pages + 1):
                if page == 1:
                    page_url = self.url
                else:
                    separator = '&' if '?' in self.url else '?'
                    page_url = f"{self.url}{separator}p={page}"

                logger.info(f"Fetching page {page}: {page_url}")

                try:
                    response = self.session.get(page_url, timeout=30)
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request failed for page {page}: {str(e)}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                page_jobs = self._extract_jobs_from_page(soup)

                if not page_jobs:
                    logger.info(f"No jobs found on page {page}, stopping pagination")
                    break

                all_jobs.extend(page_jobs)
                logger.info(f"Page {page}: found {len(page_jobs)} India jobs (total: {len(all_jobs)})")

                # Check for next page availability
                pagination = soup.find('div', class_='pagination-paging') or \
                             soup.find('div', class_='pagination') or \
                             soup.find('nav', attrs={'aria-label': 'pagination'})
                if pagination:
                    next_link = pagination.find('a', class_='next') or \
                                pagination.find('a', attrs={'aria-label': 'Next'}) or \
                                pagination.find('a', string=re.compile(r'next', re.I))
                    if not next_link:
                        logger.info("No next page link found in pagination")
                        break

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Total India jobs found for {self.company_name}: {len(all_jobs)}")
        return all_jobs

    def _extract_jobs_from_page(self, soup):
        """Extract job listings from a TalentBrew search results page."""
        jobs = []

        # TalentBrew typically uses a search-results-list section
        results_section = soup.find('section', id='search-results-list') or \
                          soup.find('section', class_='search-results') or \
                          soup.find('div', id='search-results-list')

        search_context = results_section if results_section else soup

        # TalentBrew job links follow pattern: /en/job/{city}/{title}/{companyId}/{jobid}
        job_link_pattern = re.compile(rf'/en/job/[^/]+/[^/]+/{self.company_id}/\d+')
        job_links = search_context.find_all('a', href=job_link_pattern)

        if not job_links:
            # Broader fallback: any link containing /job/ and the company ID
            job_links = search_context.find_all('a', href=lambda h: h and '/job/' in h and self.company_id in h)

        if not job_links:
            # Even broader fallback: look for structured list items
            list_items = search_context.select('li[data-job-id]') or \
                         search_context.select('ul.search-results-list li') or \
                         search_context.select('div.search-results li')
            for item in list_items:
                link = item.find('a', href=lambda h: h and '/job/' in h)
                if link and link not in job_links:
                    job_links.append(link)

        seen_urls = set()

        for link in job_links:
            try:
                href = link.get('href', '')
                if not href:
                    continue

                # Build full URL
                job_url = href if href.startswith('http') else f"{self.base_url}{href}"

                # Deduplicate
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                # Extract title from the h2 child element inside the link,
                # NOT from the full link text (which concatenates title + location).
                # Structure: <a><h2 class="section4__job-list-title">Title</h2>
                #            <span class="section4__job-list-location">Location</span></a>
                title_el = link.select_one('h2.section4__job-list-title, h2, h3')
                if title_el:
                    title = title_el.get_text(strip=True)
                else:
                    # Fallback: use link text but it may include location
                    title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                # Extract job ID from URL pattern /en/job/{city}/{title}/{companyId}/{jobId}
                job_id = ''
                match = re.search(rf'/{self.company_id}/(\d+)', href)
                if match:
                    job_id = match.group(1)
                if not job_id:
                    job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

                # Find the parent container for department/date extraction
                parent_li = link.find_parent('li') or link.find_parent('tr') or link.find_parent('div', class_=lambda c: c and 'job' in str(c).lower())

                # Extract location from child span inside the link first,
                # then fall back to sibling/parent elements
                location = ''
                loc_span = link.select_one('span.section4__job-list-location')
                if loc_span:
                    location = loc_span.get_text(strip=True)

                if not location and parent_li:
                    loc_el = parent_li.find('span', class_=lambda c: c and 'location' in str(c).lower()) or \
                             parent_li.find('div', class_=lambda c: c and 'location' in str(c).lower()) or \
                             parent_li.find(class_='job-location') or \
                             parent_li.find(class_='job-info')
                    if loc_el:
                        location = loc_el.get_text(strip=True)

                # If no structured location found, try extracting city from URL
                if not location:
                    url_parts = href.strip('/').split('/')
                    # Pattern: /en/job/{city}/{title}/{companyId}/{jobId}
                    job_idx = -1
                    for i, part in enumerate(url_parts):
                        if part == 'job':
                            job_idx = i
                            break
                    if job_idx >= 0 and len(url_parts) > job_idx + 1:
                        city_from_url = url_parts[job_idx + 1].replace('-', ' ').title()
                        location = city_from_url

                # Extract department if available
                department = ''
                if parent_li:
                    dept_el = parent_li.find('span', class_=lambda c: c and 'department' in str(c).lower()) or \
                              parent_li.find('div', class_=lambda c: c and 'department' in str(c).lower()) or \
                              parent_li.find(class_='job-department')
                    if dept_el:
                        department = dept_el.get_text(strip=True)

                # Extract posted date if available
                posted_date = ''
                if parent_li:
                    date_el = parent_li.find('span', class_=lambda c: c and 'date' in str(c).lower()) or \
                              parent_li.find(class_='job-date')
                    if date_el:
                        posted_date = date_el.get_text(strip=True)

                # Filter for India jobs
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
                    'posted_date': posted_date,
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }

                jobs.append(job_data)
                logger.info(f"Added job: {title} | {location}")

            except Exception as e:
                logger.error(f"Error processing job link: {str(e)}")
                continue

        return jobs


if __name__ == "__main__":
    scraper = EncoreCapitalScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']} | {job['apply_url']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

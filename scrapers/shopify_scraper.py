import requests
import hashlib
import re
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('shopify_scraper')


class ShopifyScraper:
    def __init__(self):
        self.company_name = 'Shopify'
        self.url = 'https://www.shopify.com/careers'
        self.base_url = 'https://www.shopify.com'
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
        """Scrape Shopify jobs from their custom React SSR careers page.

        Job titles are in <h4 class="font-bold text-xl grow"> elements.
        Job links follow <a href="/careers/{id}"> pattern.
        Filter for India by checking location text.
        """
        all_jobs = []

        try:
            logger.info(f"Starting scrape for {self.company_name} from {self.url}")

            try:
                response = self.session.get(self.url, timeout=30)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {str(e)}")
                return all_jobs

            soup = BeautifulSoup(response.text, 'html.parser')

            # Primary approach: find job title elements with the specific class
            job_title_elements = soup.find_all('h4', class_=lambda c: c and 'font-bold' in c and 'text-xl' in c and 'grow' in c)

            if job_title_elements:
                logger.info(f"Found {len(job_title_elements)} job title elements via h4.font-bold.text-xl.grow")
                for title_el in job_title_elements:
                    try:
                        title = title_el.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue

                        # Find the parent link element
                        parent_link = title_el.find_parent('a', href=lambda h: h and '/careers/' in h)
                        if not parent_link:
                            # Try to find a sibling or nearby link
                            parent_container = title_el.find_parent('div') or title_el.find_parent('li')
                            if parent_container:
                                parent_link = parent_container.find('a', href=lambda h: h and '/careers/' in h)

                        job_url = self.url
                        job_id = ''
                        if parent_link:
                            href = parent_link.get('href', '')
                            job_url = href if href.startswith('http') else f"{self.base_url}{href}"
                            # Extract ID from /careers/{id}
                            career_match = re.search(r'/careers/([^/?#]+)', href)
                            if career_match:
                                job_id = career_match.group(1)

                        if not job_id:
                            job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                        # Find location - look in parent container for location text
                        location = ''
                        parent_container = title_el.find_parent('div', class_=lambda c: c and 'flex' in str(c)) or \
                                           title_el.find_parent('li') or \
                                           title_el.find_parent('article')
                        if parent_container:
                            # Look for spans or divs that contain location info
                            loc_candidates = parent_container.find_all(['span', 'p', 'div'], string=re.compile(r'(India|Bangalore|Bengaluru|Mumbai|Delhi|Remote|Hybrid|On-site)', re.I))
                            if loc_candidates:
                                location = loc_candidates[0].get_text(strip=True)
                            else:
                                # Try all text content after the title
                                all_text = parent_container.get_text(separator='|', strip=True)
                                parts = all_text.split('|')
                                for part in parts:
                                    part = part.strip()
                                    if part != title and self._is_india_location(part):
                                        location = part
                                        break

                        # Determine remote type
                        remote_type = ''
                        if parent_container:
                            container_text = parent_container.get_text(strip=True).lower()
                            if 'remote' in container_text:
                                remote_type = 'Remote'
                            elif 'hybrid' in container_text:
                                remote_type = 'Hybrid'
                            elif 'on-site' in container_text or 'onsite' in container_text:
                                remote_type = 'On-site'

                        # Extract department if available
                        department = ''
                        if parent_container:
                            dept_el = parent_container.find(class_=lambda c: c and 'department' in str(c).lower()) or \
                                      parent_container.find(class_=lambda c: c and 'team' in str(c).lower())
                            if dept_el:
                                department = dept_el.get_text(strip=True)

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
                            'remote_type': remote_type,
                            'status': 'active'
                        }

                        all_jobs.append(job_data)
                        logger.info(f"Added job: {title} | {location}")

                    except Exception as e:
                        logger.error(f"Error processing job title element: {str(e)}")
                        continue
            else:
                # Fallback approach: find all career links
                logger.info("Primary selector not found, trying fallback approach with career links")
                career_links = soup.find_all('a', href=lambda h: h and re.match(r'/careers/[^/]+$', h))

                if not career_links:
                    career_links = soup.find_all('a', href=lambda h: h and '/careers/' in h and h != '/careers/')

                logger.info(f"Found {len(career_links)} career links")

                seen_urls = set()
                for link in career_links:
                    try:
                        href = link.get('href', '')
                        if not href or href == '/careers/' or href == '/careers':
                            continue

                        job_url = href if href.startswith('http') else f"{self.base_url}{href}"

                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        # Get title from the link or its children
                        title_el = link.find('h4') or link.find('h3') or link.find('h5')
                        title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue

                        # Extract job ID
                        career_match = re.search(r'/careers/([^/?#]+)', href)
                        job_id = career_match.group(1) if career_match else hashlib.md5(title.encode()).hexdigest()[:12]

                        # Extract location from the link content or parent
                        location = ''
                        link_text = link.get_text(separator='|', strip=True)
                        parts = link_text.split('|')
                        for part in parts:
                            part = part.strip()
                            if part != title and self._is_india_location(part):
                                location = part
                                break

                        if not location:
                            parent = link.find_parent('div') or link.find_parent('li')
                            if parent:
                                parent_text = parent.get_text(separator='|', strip=True)
                                for part in parent_text.split('|'):
                                    part = part.strip()
                                    if part != title and self._is_india_location(part):
                                        location = part
                                        break

                        # Remote type
                        remote_type = ''
                        full_text = (link_text + ' ' + (link.find_parent('div').get_text(strip=True) if link.find_parent('div') else '')).lower()
                        if 'remote' in full_text:
                            remote_type = 'Remote'
                        elif 'hybrid' in full_text:
                            remote_type = 'Hybrid'

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
                            'department': '',
                            'apply_url': job_url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': '',
                            'salary_range': '',
                            'remote_type': remote_type,
                            'status': 'active'
                        }

                        all_jobs.append(job_data)
                        logger.info(f"Added job: {title} | {location}")

                    except Exception as e:
                        logger.error(f"Error processing career link: {str(e)}")
                        continue

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Total India jobs found for {self.company_name}: {len(all_jobs)}")
        return all_jobs


if __name__ == "__main__":
    scraper = ShopifyScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']} | {job['apply_url']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

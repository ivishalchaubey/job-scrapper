import requests
import hashlib
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('bostonanalytics_scraper')


class BostonAnalyticsScraper:
    def __init__(self):
        self.company_name = 'Boston Analytics'
        self.url = 'https://bostonanalytics.com/careers.php'
        self.base_url = 'https://bostonanalytics.com'
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape Boston Analytics jobs from their static PHP careers page.

        Jobs are in Bootstrap accordion panels. Extract job titles from
        panel headings and descriptions from panel bodies.
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

            # Boston Analytics uses Bootstrap accordion panels for job listings
            # Try multiple selectors for accordion panels
            panels = soup.select('.panel') or \
                     soup.select('.accordion-item') or \
                     soup.select('.card')

            if not panels:
                # Fallback: try finding job headings directly
                headings = soup.find_all(['h3', 'h4', 'h5'], class_=lambda c: c and any(
                    kw in str(c).lower() for kw in ['panel', 'accordion', 'title', 'heading']
                ))
                if not headings:
                    # Try even broader: any heading inside a collapsible structure
                    headings = soup.select('.panel-heading') or \
                               soup.select('.accordion-header') or \
                               soup.select('.card-header')

                if headings:
                    for heading in headings:
                        try:
                            title = heading.get_text(strip=True)
                            if not title or len(title) < 3:
                                continue

                            job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                            # Try to find the associated panel body/description
                            description = ''
                            panel_body = heading.find_next_sibling(class_=lambda c: c and any(
                                kw in str(c).lower() for kw in ['panel-body', 'panel-collapse', 'collapse', 'card-body']
                            ))
                            if panel_body:
                                description = panel_body.get_text(separator=' ', strip=True)

                            # Extract location from description text
                            location = self._extract_location(description)
                            department = self._extract_department(description)

                            loc = self.parse_location(location)

                            apply_url = f"{self.base_url}/careers-apply.php"

                            job_data = {
                                'external_id': self.generate_external_id(job_id, self.company_name),
                                'company_name': self.company_name,
                                'title': title,
                                'description': description[:2000] if description else '',
                                'location': location if location else 'India',
                                'city': loc.get('city', ''),
                                'state': loc.get('state', ''),
                                'country': loc.get('country', 'India'),
                                'employment_type': self._extract_employment_type(description),
                                'department': department,
                                'apply_url': apply_url,
                                'posted_date': '',
                                'job_function': '',
                                'experience_level': self._extract_experience(description),
                                'salary_range': '',
                                'remote_type': '',
                                'status': 'active'
                            }

                            all_jobs.append(job_data)
                            logger.info(f"Added job: {title}")

                        except Exception as e:
                            logger.error(f"Error processing heading: {str(e)}")
                            continue
                else:
                    logger.warning("No accordion panels or headings found on page")
            else:
                # Process Bootstrap panels
                for panel in panels:
                    try:
                        # Extract title from panel heading
                        heading = panel.find(class_=lambda c: c and any(
                            kw in str(c).lower() for kw in ['panel-heading', 'panel-title', 'card-header', 'accordion-header']
                        ))
                        if not heading:
                            heading = panel.find(['h3', 'h4', 'h5', 'a'])
                        if not heading:
                            continue

                        title = heading.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue

                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                        # Extract description from panel body
                        description = ''
                        body = panel.find(class_=lambda c: c and any(
                            kw in str(c).lower() for kw in ['panel-body', 'panel-collapse', 'collapse', 'card-body', 'accordion-body']
                        ))
                        if body:
                            description = body.get_text(separator=' ', strip=True)

                        # Check for apply link within the panel
                        apply_link = panel.find('a', href=lambda h: h and 'apply' in h.lower())
                        if apply_link:
                            href = apply_link.get('href', '')
                            apply_url = href if href.startswith('http') else f"{self.base_url}/{href.lstrip('/')}"
                        else:
                            apply_url = f"{self.base_url}/careers-apply.php"

                        location = self._extract_location(description)
                        department = self._extract_department(description)

                        loc = self.parse_location(location)

                        job_data = {
                            'external_id': self.generate_external_id(job_id, self.company_name),
                            'company_name': self.company_name,
                            'title': title,
                            'description': description[:2000] if description else '',
                            'location': location if location else 'India',
                            'city': loc.get('city', ''),
                            'state': loc.get('state', ''),
                            'country': loc.get('country', 'India'),
                            'employment_type': self._extract_employment_type(description),
                            'department': department,
                            'apply_url': apply_url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': self._extract_experience(description),
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }

                        all_jobs.append(job_data)
                        logger.info(f"Added job: {title}")

                    except Exception as e:
                        logger.error(f"Error processing panel: {str(e)}")
                        continue

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        logger.info(f"Total jobs found for {self.company_name}: {len(all_jobs)}")
        return all_jobs

    def _extract_location(self, text):
        """Extract location from job description text."""
        if not text:
            return ''
        india_cities = [
            'Bangalore', 'Bengaluru', 'Mumbai', 'Delhi', 'New Delhi',
            'Hyderabad', 'Chennai', 'Pune', 'Gurugram', 'Gurgaon',
            'Noida', 'Kolkata', 'Ahmedabad', 'Jaipur', 'Kochi',
            'Coimbatore', 'Nagpur', 'Indore', 'Lucknow', 'Chandigarh',
            'Bhubaneswar', 'Thiruvananthapuram', 'NCR',
        ]
        text_lower = text.lower()
        found_cities = [city for city in india_cities if city.lower() in text_lower]
        if found_cities:
            return ', '.join(found_cities) + ', India'
        if 'india' in text_lower:
            return 'India'
        return ''

    def _extract_department(self, text):
        """Extract department from description text."""
        if not text:
            return ''
        text_lower = text.lower()
        departments = {
            'engineering': 'Engineering',
            'data science': 'Data Science',
            'analytics': 'Analytics',
            'marketing': 'Marketing',
            'sales': 'Sales',
            'human resources': 'Human Resources',
            'finance': 'Finance',
            'operations': 'Operations',
            'product': 'Product',
            'design': 'Design',
            'research': 'Research',
            'consulting': 'Consulting',
        }
        for keyword, dept_name in departments.items():
            if keyword in text_lower:
                return dept_name
        return ''

    def _extract_employment_type(self, text):
        """Extract employment type from description text."""
        if not text:
            return ''
        text_lower = text.lower()
        if 'full time' in text_lower or 'full-time' in text_lower or 'fulltime' in text_lower:
            return 'Full-time'
        if 'part time' in text_lower or 'part-time' in text_lower or 'parttime' in text_lower:
            return 'Part-time'
        if 'contract' in text_lower:
            return 'Contract'
        if 'intern' in text_lower or 'internship' in text_lower:
            return 'Internship'
        return ''

    def _extract_experience(self, text):
        """Extract experience level from description text."""
        if not text:
            return ''
        text_lower = text.lower()
        if 'senior' in text_lower or 'sr.' in text_lower or 'lead' in text_lower:
            return 'Senior'
        if 'junior' in text_lower or 'jr.' in text_lower:
            return 'Junior'
        if 'entry level' in text_lower or 'entry-level' in text_lower or 'fresher' in text_lower:
            return 'Entry Level'
        if 'manager' in text_lower or 'director' in text_lower:
            return 'Manager'
        if 'intern' in text_lower:
            return 'Intern'
        return ''


if __name__ == "__main__":
    scraper = BostonAnalyticsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']} | {job['apply_url']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

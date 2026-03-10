import requests
import hashlib
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('pncinfratech_scraper')


class PNCInfratechScraper:
    def __init__(self):
        self.company_name = "PNC Infratech"
        # Primary URL and alternates in case of DNS issues
        self.url = "https://www.pncinfratech.com/career.html"
        self.alt_urls = [
            'https://pncinfratech.com/career.html',
        ]
        self.base_url = 'https://www.pncinfratech.com'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

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
            if parts[1] in ['IN', 'IND', 'India']:
                result['country'] = 'India'
            else:
                result['state'] = parts[1]
        return result

    def _fetch_page(self):
        """Try primary and alternate URLs with retry logic for DNS issues."""
        urls_to_try = [self.url] + self.alt_urls

        for url in urls_to_try:
            for attempt in range(2):
                try:
                    logger.info(f"Trying URL: {url} (attempt {attempt + 1})")
                    response = requests.get(
                        url, headers=self.headers, timeout=30, allow_redirects=True
                    )
                    response.raise_for_status()
                    logger.info(f"Successfully fetched from: {response.url}")
                    return response
                except requests.exceptions.ConnectionError as e:
                    logger.warning(f"Connection error for {url} (attempt {attempt + 1}): {str(e)}")
                    if attempt == 0:
                        import time
                        time.sleep(2)  # Brief pause before retry
                    continue
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Request failed for {url}: {str(e)}")
                    break  # Don't retry non-connection errors

        return None

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        try:
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            response = self._fetch_page()
            if not response:
                logger.error(f"Failed to fetch career page from all URLs")
                return all_jobs

            soup = BeautifulSoup(response.text, 'html.parser')

            # Strategy 1: Find the innermost table with job data
            # The PNC Infratech page uses deeply nested tables (IndiaMART-style).
            # We need to find the innermost table whose header row has columns like
            # "SN.", "NAME OF THE POST", "ELIGIBILITY CRITERIA", "VACANCY CODE".
            # We sort tables by nesting depth (deepest first) to avoid outer wrappers.
            tables = soup.find_all('table')
            seen_ids = set()

            # Sort tables: prefer those with more data rows and fewer nested tables
            def table_score(t):
                direct_rows = t.find_all('tr', recursive=False)
                if not direct_rows:
                    direct_rows = t.find_all('tr')
                nested_tables = t.find_all('table')
                # Prefer tables with many rows, no nested tables, and a job-like header
                return len(direct_rows) - len(nested_tables) * 10

            tables_sorted = sorted(tables, key=table_score, reverse=True)

            for table in tables_sorted:
                rows = table.find_all('tr', recursive=False)
                if not rows:
                    rows = table.find_all('tr')
                if len(rows) < 2:
                    continue

                # Detect header row
                header_row = rows[0]
                header_cells = header_row.find_all(['th', 'td'], recursive=False)
                if not header_cells:
                    header_cells = header_row.find_all(['th', 'td'])
                headers_text = [th.get_text(strip=True).lower() for th in header_cells]

                # Check if this looks like a job listing table
                job_keywords = ['position', 'title', 'designation', 'vacancy', 'post',
                               'qualification', 'experience', 'code', 'name']
                is_job_table = any(any(kw in h for kw in job_keywords) for h in headers_text)

                if not is_job_table and len(headers_text) > 0:
                    continue

                logger.info(f"Found job table with {len(rows) - 1} data rows. Headers: {headers_text}")

                # Map column indices
                col_map = {}
                for i, h in enumerate(headers_text):
                    if any(kw in h for kw in ['position', 'title', 'designation', 'post', 'name']):
                        col_map['title'] = i
                    elif any(kw in h for kw in ['code', 'vacancy code', 'ref', 'id']):
                        col_map['code'] = i
                    elif any(kw in h for kw in ['qualification', 'education']):
                        col_map['qualification'] = i
                    elif any(kw in h for kw in ['experience', 'exp']):
                        col_map['experience'] = i
                    elif any(kw in h for kw in ['location', 'place', 'city']):
                        col_map['location'] = i
                    elif any(kw in h for kw in ['department', 'dept']):
                        col_map['department'] = i

                # If no title column found, use first column
                if 'title' not in col_map:
                    col_map['title'] = 0

                # Process data rows
                for row in rows[1:]:
                    try:
                        cells = row.find_all(['td', 'th'])
                        if not cells:
                            continue

                        # Extract title
                        title_idx = col_map.get('title', 0)
                        if title_idx >= len(cells):
                            continue
                        title = cells[title_idx].get_text(strip=True)
                        if not title or len(title) < 2:
                            continue

                        # Extract vacancy code
                        vacancy_code = ''
                        code_idx = col_map.get('code')
                        if code_idx is not None and code_idx < len(cells):
                            vacancy_code = cells[code_idx].get_text(strip=True)

                        # Extract qualification
                        qualification = ''
                        qual_idx = col_map.get('qualification')
                        if qual_idx is not None and qual_idx < len(cells):
                            qualification = cells[qual_idx].get_text(strip=True)

                        # Extract experience
                        experience = ''
                        exp_idx = col_map.get('experience')
                        if exp_idx is not None and exp_idx < len(cells):
                            experience = cells[exp_idx].get_text(strip=True)

                        # Extract location
                        location = ''
                        loc_idx = col_map.get('location')
                        if loc_idx is not None and loc_idx < len(cells):
                            location = cells[loc_idx].get_text(strip=True)

                        # Extract department
                        department = ''
                        dept_idx = col_map.get('department')
                        if dept_idx is not None and dept_idx < len(cells):
                            department = cells[dept_idx].get_text(strip=True)

                        # Build description from available fields
                        desc_parts = []
                        if vacancy_code:
                            desc_parts.append(f"Vacancy Code: {vacancy_code}")
                        if qualification:
                            desc_parts.append(f"Qualification: {qualification}")
                        if experience:
                            desc_parts.append(f"Experience: {experience}")
                        description = '\n'.join(desc_parts)

                        # Check for link in the row
                        job_url = self.url
                        link = row.find('a', href=True)
                        if link:
                            href = link.get('href', '')
                            if href and not href.startswith('#') and not href.startswith('javascript:'):
                                if href.startswith('http'):
                                    job_url = href
                                elif href.startswith('/'):
                                    job_url = self.base_url + href
                                else:
                                    job_url = self.base_url + '/' + href

                        # Generate job ID from vacancy code or title
                        job_id_str = vacancy_code if vacancy_code else title
                        job_id = hashlib.md5(job_id_str.encode()).hexdigest()[:12]
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
                            'department': department,
                            'apply_url': job_url,
                            'posted_date': '',
                            'job_function': '',
                            'experience_level': experience,
                            'salary_range': '',
                            'remote_type': '',
                            'status': 'active'
                        }

                        all_jobs.append(job_data)
                        seen_ids.add(external_id)
                        logger.info(f"Extracted: {title} | {location} | {experience}")

                    except Exception as e:
                        logger.error(f"Error parsing table row: {str(e)}")
                        continue

                if all_jobs:
                    break  # Stop after first matching table

            # Strategy 2: If no table found, try list/card structures
            if not all_jobs:
                logger.info("No job table found, trying alternative structures")
                all_jobs = self._extract_from_lists(soup, seen_ids)

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _extract_from_lists(self, soup, seen_ids):
        """Fallback: extract from list/card structures."""
        jobs = []

        # Try divs and list items
        selectors = [
            'div.career-item', 'div.job-card', 'div.vacancy',
            'li.career-item', 'div.opening', 'div.position'
        ]

        for selector in selectors:
            elements = soup.select(selector)
            if not elements:
                continue

            for elem in elements:
                try:
                    title_elem = elem.select_one('h2, h3, h4, h5, strong, a')
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue

                    job_url = self.url
                    link = elem.find('a', href=True)
                    if link:
                        href = link.get('href', '')
                        if href and not href.startswith('#'):
                            job_url = href if href.startswith('http') else self.base_url + href

                    job_id = hashlib.md5(title.encode()).hexdigest()[:12]
                    external_id = self.generate_external_id(job_id, self.company_name)

                    if external_id in seen_ids:
                        continue

                    job_data = {
                        'external_id': external_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': '',
                        'department': '',
                        'apply_url': job_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    jobs.append(job_data)
                    seen_ids.add(external_id)
                    logger.info(f"Extracted (list): {title}")

                except Exception as e:
                    logger.error(f"Error parsing list element: {str(e)}")
                    continue

            if jobs:
                break

        return jobs


if __name__ == "__main__":
    scraper = PNCInfratechScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['experience_level']}")

import requests
import hashlib
import re
import json

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('ramcosystems_scraper')


class RamcoSystemsScraper:
    def __init__(self):
        self.company_name = 'Ramco Systems'
        self.url = 'https://www.ramco.com/careers/jobs-by-locations'
        self.base_url = 'https://www.ramco.com'
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        try:
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            try:
                response = requests.get(self.url, headers=self.headers, timeout=30)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {str(e)}")
                return all_jobs

            html = response.text
            logger.info(f"Fetched page ({len(html)} bytes)")

            # Strategy 1: Extract jobData JavaScript variable
            # The Ramco careers page embeds job data as a JS array:
            #   const jobData = [ { "page_path": "...", "job_title": `...`, ... }, ... ]
            # Note: uses `const` (not `var`) and backtick template literals (not quotes)
            # for some values. We need to handle both.

            # Match both var and const declarations.
            # Use a non-greedy match up to the closing bracket `]`
            # (the first `]` that isn't inside an object or nested array).
            job_data_match = re.search(
                r'(?:var|let|const)\s+jobData\s*=\s*\[(.*?)\]',
                html, re.DOTALL
            )

            if job_data_match:
                logger.info("Found jobData JavaScript variable")
                raw_array_content = job_data_match.group(1)
                all_jobs = self._parse_js_job_array(raw_array_content)

            if not all_jobs:
                logger.warning("jobData extraction failed or empty, trying alternative patterns")

                # Strategy 2: Try other JS variable names with const/let/var
                alt_patterns = [
                    r'(?:var|let|const)\s+jobs\s*=\s*\[(.*?)\]',
                    r'(?:var|let|const)\s+jobList\s*=\s*\[(.*?)\]',
                    r'(?:var|let|const)\s+openings\s*=\s*\[(.*?)\]',
                    r'(?:var|let|const)\s+positions\s*=\s*\[(.*?)\]',
                    r'jobData\s*:\s*\[(.*?)\]',
                    r'"jobs"\s*:\s*\[(.*?)\]',
                ]

                for pattern in alt_patterns:
                    match = re.search(pattern, html, re.DOTALL)
                    if match:
                        logger.info(f"Found match with pattern: {pattern}")
                        jobs = self._parse_js_job_array(match.group(1))
                        if jobs:
                            all_jobs = jobs
                            break

                # Strategy 3: Fall back to HTML parsing if JS extraction failed
                if not all_jobs:
                    logger.info("JS extraction failed, trying HTML parsing")
                    all_jobs = self._parse_html_fallback(html)

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _parse_js_job_array(self, raw_array_content):
        """Parse job objects from a JavaScript array body that may use backtick literals.

        The Ramco page uses a mix of double-quoted strings and backtick template
        literals for values:
            { "page_path" : "some-slug", "job_title" : `Some Title`, ... }

        We convert backtick-delimited values to double-quoted strings so the
        result is valid JSON, then parse each object.
        """
        jobs = []

        # Replace backtick-delimited values with double-quoted values
        # Match: `...` (backtick strings, possibly multiline)
        def backtick_to_quote(m):
            content = m.group(1)
            # Escape double quotes inside the content
            content = content.replace('\\', '\\\\').replace('"', '\\"')
            # Collapse newlines to spaces
            content = content.replace('\n', ' ').replace('\r', '')
            return f'"{content}"'

        cleaned = re.sub(r'`((?:[^`])*)`', backtick_to_quote, raw_array_content)

        # Strip trailing whitespace and commas from array content
        cleaned = cleaned.rstrip()
        cleaned = re.sub(r',\s*$', '', cleaned)
        # Remove trailing commas before closing brackets/braces
        cleaned = re.sub(r',\s*\]', ']', cleaned)
        cleaned = re.sub(r',\s*\}', '}', cleaned)

        # Wrap in array brackets for JSON parsing
        json_str = f'[{cleaned}]'

        try:
            job_list = json.loads(json_str)
            logger.info(f"Parsed {len(job_list)} jobs from JS array")

            for item in job_list:
                try:
                    job = self._parse_job_item(item)
                    if job:
                        jobs.append(job)
                        logger.info(f"Extracted: {job['title']} | {job['location']}")
                except Exception as e:
                    logger.error(f"Error parsing job item: {str(e)}")
                    continue

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed after backtick cleanup: {str(e)}")
            # Fallback: extract individual objects with regex
            jobs = self._parse_with_regex(raw_array_content)

        return jobs

    def _parse_job_item(self, item):
        """Parse a single job item from the jobData array.

        Actual field names from the Ramco page:
            page_path, job_title, job_code, job_level, location,
            location_coordinates, job_status, experience, qualification,
            roles_responsibilities, sbu
        We also handle generic key names for robustness.
        """
        # Handle different possible key names
        title = (
            item.get('job_title', '') or
            item.get('title', '') or
            item.get('Title', '') or
            item.get('jobTitle', '') or
            item.get('position', '') or
            item.get('Position', '') or
            ''
        ).strip()

        if not title:
            return None

        # Skip inactive jobs
        job_status = item.get('job_status', '').strip()
        if job_status and job_status.lower() not in ['active', '']:
            return None

        # Job code/ID
        job_code = (
            item.get('job_code', '') or
            item.get('code', '') or
            item.get('Code', '') or
            item.get('jobCode', '') or
            item.get('id', '') or
            item.get('Id', '') or
            ''
        )
        job_code = str(job_code).strip()

        # Page path (used to build the detail URL)
        page_path = item.get('page_path', '').strip()

        # Location
        location = (
            item.get('location', '') or
            item.get('Location', '') or
            item.get('city', '') or
            item.get('City', '') or
            ''
        ).strip()

        # Experience
        experience = (
            item.get('experience', '') or
            item.get('Experience', '') or
            item.get('exp', '') or
            ''
        ).strip()

        # Qualifications
        qualifications = (
            item.get('qualification', '') or
            item.get('qualifications', '') or
            item.get('Qualifications', '') or
            item.get('education', '') or
            ''
        ).strip()

        # Department / SBU (Strategic Business Unit)
        department = (
            item.get('sbu', '') or
            item.get('department', '') or
            item.get('Department', '') or
            item.get('team', '') or
            ''
        ).strip()

        # Job level
        job_level = item.get('job_level', '').strip()

        # Description - build from available fields
        description_parts = []

        # roles_responsibilities may contain HTML
        roles = item.get('roles_responsibilities', '').strip()
        if roles:
            # Strip HTML tags for plain text description
            from bs4 import BeautifulSoup as BS
            roles_text = BS(roles, 'html.parser').get_text(separator=' ', strip=True)
            if roles_text:
                description_parts.append(roles_text)

        desc = (
            item.get('description', '') or
            item.get('Description', '') or
            ''
        ).strip()
        if desc:
            description_parts.insert(0, desc)

        if qualifications:
            description_parts.append(f"Qualification: {qualifications}")
        if experience:
            description_parts.append(f"Experience: {experience}")
        if job_level:
            description_parts.append(f"Level: {job_level}")

        description = '\n'.join(description_parts)[:2000]

        # URL - build from page_path if available
        if page_path:
            apply_url = f"{self.base_url}/careers/jobs-by-locations/{page_path}"
        else:
            apply_url = (
                item.get('url', '') or
                item.get('applyUrl', '') or
                item.get('link', '') or
                self.url
            ).strip()
            if apply_url and not apply_url.startswith('http'):
                apply_url = f"{self.base_url}{apply_url}" if apply_url.startswith('/') else self.url

        # Generate external ID
        job_id_str = job_code if job_code else title
        job_id = hashlib.md5(job_id_str.encode()).hexdigest()[:12] if not job_code else job_code
        external_id = self.generate_external_id(job_id, self.company_name)

        location_parts = self.parse_location(location)

        return {
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
            'apply_url': apply_url,
            'posted_date': '',
            'job_function': '',
            'experience_level': experience,
            'salary_range': '',
            'remote_type': '',
            'status': 'active'
        }

    def _parse_with_regex(self, raw_json):
        """Parse individual job objects from JS when JSON parsing fails."""
        jobs = []
        # Find individual objects in the array
        obj_pattern = re.compile(r'\{[^{}]+\}', re.DOTALL)
        matches = obj_pattern.findall(raw_json)

        for match in matches:
            try:
                # Try to parse individual object
                cleaned = re.sub(r',\s*\}', '}', match)
                cleaned = re.sub(r"'", '"', cleaned)
                item = json.loads(cleaned)
                job = self._parse_job_item(item)
                if job:
                    jobs.append(job)
            except (json.JSONDecodeError, Exception):
                continue

        return jobs

    def _parse_html_fallback(self, html):
        """Fallback: parse job data from HTML elements."""
        from bs4 import BeautifulSoup

        jobs = []
        soup = BeautifulSoup(html, 'html.parser')
        seen_ids = set()

        # Look for job listing elements
        selectors = [
            'div.job-item', 'div.career-item', 'div.opening',
            'tr', 'li.job', 'div.vacancy', 'div.position',
            'div.accordion-item', 'div.panel'
        ]

        for selector in selectors:
            elements = soup.select(selector)
            if selector == 'tr':
                elements = [e for e in elements if e.find('td')]
            if not elements:
                continue

            for elem in elements:
                try:
                    title_elem = elem.select_one('h2, h3, h4, h5, strong, a, td:first-child')
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    if not title or len(title) < 3 or len(title) > 200:
                        continue

                    job_id = hashlib.md5(title.encode()).hexdigest()[:12]
                    external_id = self.generate_external_id(job_id, self.company_name)

                    if external_id in seen_ids:
                        continue

                    job_url = self.url
                    link = elem.find('a', href=True)
                    if link:
                        href = link.get('href', '')
                        if href and not href.startswith('#'):
                            job_url = href if href.startswith('http') else f"https://www.ramco.com{href}"

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
                    logger.info(f"Extracted (HTML): {title}")
                except Exception as e:
                    logger.error(f"Error in HTML fallback: {str(e)}")
                    continue

            if jobs:
                break

        return jobs


if __name__ == "__main__":
    scraper = RamcoSystemsScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['experience_level']}")

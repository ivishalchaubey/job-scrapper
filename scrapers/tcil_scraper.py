import requests
import hashlib
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('tcil_scraper')


class TCILScraper:
    def __init__(self):
        self.company_name = 'Transport Corporation of India'
        self.url = 'https://tcil.com/careers/'
        self.api_url = 'https://tcil.com/wp-admin/admin-ajax.php'
        self.direct_api_url = 'https://tlog.grouptci.in/WebServices/uat_service/common.svc/CurrentOpening'
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
        """Scrape Transport Corporation of India jobs.

        Primary method: POST to WordPress AJAX endpoint with action=fetch_jobs
        Response format: {"success": true, "data": {"CurrentOpeningList": [...]}}

        Fallback: Parse the HTML careers page directly.
        Each job has: jdetail class, jtitle, jdesc, jmeta with location/department/job_id
        """
        all_jobs = []

        # Try the AJAX API first
        try:
            logger.info(f"Attempting AJAX API scrape for {self.company_name}")
            api_jobs = self._scrape_via_ajax()
            if api_jobs:
                logger.info(f"AJAX API returned {len(api_jobs)} jobs")
                return api_jobs
            else:
                logger.warning("AJAX API returned 0 jobs, falling back to HTML parsing")
        except Exception as e:
            logger.warning(f"AJAX API failed: {str(e)}, falling back to HTML parsing")

        # Fallback: parse the HTML page
        try:
            logger.info(f"Falling back to HTML parsing for {self.company_name}")
            html_jobs = self._scrape_via_html()
            all_jobs.extend(html_jobs)
        except Exception as e:
            logger.error(f"HTML parsing also failed: {str(e)}")

        logger.info(f"Total jobs found for {self.company_name}: {len(all_jobs)}")
        return all_jobs

    def _scrape_via_ajax(self):
        """Scrape jobs via WordPress AJAX endpoint and direct API fallback.

        The WordPress AJAX endpoint proxies to a .NET/Oracle backend at
        tlog.grouptci.in. Both return JSON with the structure:
          {CurrentOpeningList: [...], objAppResultStatus: {STATUS: "SUCCESS"|"ERROR"}}

        The AJAX wrapper adds a {success: true, data: {...}} envelope.
        Each job entry uses uppercase keys: JOB_ID, POST_NAME, LOCATION,
        DEPARTMENT, ESSENTIAL_FUNCTION, EXPERIENCE_REQUIRED.
        """
        jobs = []

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://tcil.com',
            'Referer': 'https://tcil.com/careers/',
        }

        data = {
            'action': 'fetch_jobs'
        }

        job_list = []

        # Try the WordPress AJAX endpoint first
        try:
            response = self.session.post(self.api_url, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

            # The AJAX endpoint wraps the response: {success: true, data: {CurrentOpeningList: [...]}}
            success = result.get('success', False)
            if success:
                response_data = result.get('data', {})
                status_obj = response_data.get('objAppResultStatus', {})
                api_status = status_obj.get('STATUS', '')
                if api_status == 'ERROR':
                    error_msg = status_obj.get('MESSAGE', 'Unknown error')
                    logger.warning(f"AJAX API returned STATUS=ERROR: {error_msg}")
                else:
                    job_list = response_data.get('CurrentOpeningList', [])
            else:
                logger.warning("AJAX API returned success=false")
        except Exception as e:
            logger.warning(f"AJAX endpoint failed: {str(e)}")

        # If AJAX returned no jobs, try the direct .NET API
        if not job_list:
            try:
                logger.info("Trying direct API at tlog.grouptci.in")
                direct_headers = {
                    'User-Agent': headers['User-Agent'],
                    'Accept': 'application/json',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Origin': 'https://tcil.com',
                    'Referer': 'https://tcil.com/careers/',
                }
                response = self.session.post(self.direct_api_url, data={}, headers=direct_headers, timeout=30)
                response.raise_for_status()
                result = response.json()

                status_obj = result.get('objAppResultStatus', {})
                api_status = status_obj.get('STATUS', '')
                if api_status == 'ERROR':
                    error_msg = status_obj.get('MESSAGE', 'Unknown error')
                    logger.warning(f"Direct API returned STATUS=ERROR: {error_msg}")
                    raise ValueError(f"Direct API error: {error_msg}")
                else:
                    job_list = result.get('CurrentOpeningList', [])
            except Exception as e:
                logger.warning(f"Direct API also failed: {str(e)}")
                raise

        if not job_list:
            logger.info("No jobs in CurrentOpeningList from any API source")
            return jobs

        logger.info(f"API returned {len(job_list)} job entries")

        for job_entry in job_list:
            try:
                # The API returns uppercase keys: POST_NAME, JOB_ID, LOCATION,
                # DEPARTMENT, ESSENTIAL_FUNCTION, EXPERIENCE_REQUIRED
                # Also try lowercase variants for robustness.
                title = job_entry.get('POST_NAME', '') or \
                        job_entry.get('post_name', '') or \
                        job_entry.get('title', '') or \
                        job_entry.get('job_title', '') or ''
                if not title:
                    continue

                # Extract job ID
                job_id = str(
                    job_entry.get('JOB_ID', '') or
                    job_entry.get('job_id', '') or
                    job_entry.get('id', '') or
                    job_entry.get('ID', '') or
                    ''
                )
                if not job_id:
                    job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                # Description
                description = job_entry.get('ESSENTIAL_FUNCTION', '') or \
                              job_entry.get('essential_function', '') or \
                              job_entry.get('description', '') or \
                              job_entry.get('content', '') or ''
                if description:
                    # Strip HTML tags if present
                    if '<' in description and '>' in description:
                        desc_soup = BeautifulSoup(description, 'html.parser')
                        description = desc_soup.get_text(separator=' ', strip=True)
                    description = description[:2000]

                # Location
                location = job_entry.get('LOCATION', '') or \
                           job_entry.get('location', '') or \
                           job_entry.get('job_location', '') or ''
                if isinstance(location, list):
                    location = ', '.join(str(loc) for loc in location)
                elif isinstance(location, dict):
                    location = location.get('name', '') or location.get('city', '') or ''

                # Department
                department = job_entry.get('DEPARTMENT', '') or \
                             job_entry.get('department', '') or \
                             job_entry.get('job_department', '') or ''

                # Employment type
                employment_type = job_entry.get('employment_type', '') or \
                                  job_entry.get('job_type', '') or \
                                  job_entry.get('type', '') or ''

                # Apply URL - the site uses https://tcil.com/work-with-us?jid=<JOB_ID>
                apply_url = f"https://tcil.com/work-with-us?jid={job_id}" if job_id else self.url

                # Posted date
                posted_date = job_entry.get('posted_date', '') or \
                              job_entry.get('date', '') or \
                              job_entry.get('post_date', '') or \
                              job_entry.get('created_at', '') or ''
                if posted_date and len(posted_date) > 10:
                    posted_date = posted_date[:10]

                # Experience level
                experience_level = job_entry.get('EXPERIENCE_REQUIRED', '') or \
                                   job_entry.get('experience_required', '') or \
                                   job_entry.get('experience', '') or ''
                # Clean up " Years" suffix from experience
                if experience_level and experience_level.lower().endswith(' years'):
                    experience_level = experience_level[:-6].strip()
                elif experience_level and experience_level.lower().endswith('years'):
                    experience_level = experience_level[:-5].strip()

                if not location:
                    location = 'India'

                loc = self.parse_location(location)

                job_data = {
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': description,
                    'location': location,
                    'city': loc.get('city', ''),
                    'state': loc.get('state', ''),
                    'country': loc.get('country', 'India'),
                    'employment_type': employment_type,
                    'department': department,
                    'apply_url': apply_url,
                    'posted_date': posted_date,
                    'job_function': '',
                    'experience_level': experience_level,
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                }

                jobs.append(job_data)
                logger.info(f"Added job (AJAX): {title} | {location}")

            except Exception as e:
                logger.error(f"Error processing AJAX job entry: {str(e)}")
                continue

        return jobs

    def _scrape_via_html(self):
        """Fallback: scrape jobs by parsing the HTML careers page."""
        jobs = []

        try:
            response = self.session.get(self.url, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"HTML page request failed: {str(e)}")
            return jobs

        soup = BeautifulSoup(response.text, 'html.parser')

        # Each job has: jdetail class, jtitle, jdesc, jmeta
        job_details = soup.find_all(class_='jdetail') or \
                      soup.find_all(class_='job-detail') or \
                      soup.find_all(class_='job-listing') or \
                      soup.find_all(class_='career-item')

        if job_details:
            logger.info(f"Found {len(job_details)} job detail elements in HTML")
            for detail in job_details:
                try:
                    # Extract title from jtitle class
                    title_el = detail.find(class_='jtitle') or \
                               detail.find(class_='job-title') or \
                               detail.find(['h3', 'h4', 'h5'])
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue

                    # Extract description from jdesc class
                    desc_el = detail.find(class_='jdesc') or \
                              detail.find(class_='job-desc') or \
                              detail.find(class_='job-description')
                    description = desc_el.get_text(separator=' ', strip=True)[:2000] if desc_el else ''

                    # Extract metadata from jmeta class
                    meta_el = detail.find(class_='jmeta') or \
                              detail.find(class_='job-meta') or \
                              detail.find(class_='job-info')

                    location = ''
                    department = ''
                    job_id = ''

                    if meta_el:
                        meta_text = meta_el.get_text(separator='|', strip=True)
                        meta_items = meta_el.find_all(['span', 'li', 'div', 'p'])

                        for item in meta_items:
                            item_text = item.get_text(strip=True)
                            item_class = ' '.join(item.get('class', []))

                            if 'location' in item_class.lower() or 'loc' in item_class.lower():
                                location = item_text
                            elif 'department' in item_class.lower() or 'dept' in item_class.lower():
                                department = item_text
                            elif 'job-id' in item_class.lower() or 'jobid' in item_class.lower() or 'id' in item_class.lower():
                                job_id = item_text

                        # If no structured items found, try to parse from text
                        if not location and meta_text:
                            parts = meta_text.split('|')
                            for part in parts:
                                part = part.strip()
                                if any(city.lower() in part.lower() for city in [
                                    'Mumbai', 'Delhi', 'Bangalore', 'Bengaluru', 'Chennai',
                                    'Hyderabad', 'Pune', 'Kolkata', 'Gurugram', 'Gurgaon',
                                    'Noida', 'India', 'Ahmedabad', 'Jaipur', 'Lucknow',
                                ]):
                                    location = part
                                    break

                    if not job_id:
                        # Try data attributes
                        job_id = detail.get('data-job-id', '') or \
                                 detail.get('data-id', '') or \
                                 detail.get('id', '')
                    if not job_id:
                        job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    # Find apply link
                    apply_link = detail.find('a', href=lambda h: h and 'apply' in h.lower()) or \
                                 detail.find('a', class_=lambda c: c and 'apply' in str(c).lower()) or \
                                 detail.find('a', string=lambda s: s and 'apply' in s.lower() if s else False)
                    if apply_link:
                        href = apply_link.get('href', '')
                        apply_url = href if href.startswith('http') else f"https://tcil.com{href}"
                    else:
                        apply_url = self.url

                    if not location:
                        location = 'India'

                    loc = self.parse_location(location)

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': description,
                        'location': location,
                        'city': loc.get('city', ''),
                        'state': loc.get('state', ''),
                        'country': loc.get('country', 'India'),
                        'employment_type': '',
                        'department': department,
                        'apply_url': apply_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    jobs.append(job_data)
                    logger.info(f"Added job (HTML): {title} | {location}")

                except Exception as e:
                    logger.error(f"Error processing HTML job detail: {str(e)}")
                    continue
        else:
            # Broader fallback: look for the job-opening container that holds
            # dynamically-loaded job data. On the TCIL site, job listings are
            # loaded via AJAX into div.job-opening > div#data-container.
            # Since the data is loaded dynamically, static HTML parsing won't
            # find actual job listings here. We should NOT scrape promotional
            # headings like "Learning opportunities", "Global exposure" etc.
            # that appear in Elementor widget sections.
            logger.info("No jdetail elements found, and dynamic job data is not available in static HTML")
            logger.info("The TCIL careers page loads job data via AJAX into #data-container; "
                        "static HTML parsing cannot extract job listings.")

        return jobs


if __name__ == "__main__":
    scraper = TCILScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for i, job in enumerate(jobs[:10], 1):
        print(f"{i}. {job['title']} | {job['location']} | {job['apply_url']}")
    if len(jobs) > 10:
        print(f"... and {len(jobs) - 10} more")

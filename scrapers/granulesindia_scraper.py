import requests
import hashlib
import re
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('granulesindia_scraper')


class GranulesScraper:
    def __init__(self):
        self.company_name = 'Granules India'
        self.url = 'https://granulesindia.com/careers/current-openings/'
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

            soup = BeautifulSoup(response.text, 'html.parser')

            # The Granules India careers page uses SiteOrigin Panels with
            # div.apply_box containers for each job listing. Each contains:
            #   - h3: role title (e.g. "Analyst")
            #   - div.one_ap with h4: specialization (e.g. "Regulatory affairs")
            #   - p: location and experience text
            #   - a: "Read More" link to job description
            #
            # IMPORTANT: The page also has 70+ product specification tables
            # with 568 <tr> rows -- those are NOT job listings.

            seen_titles = set()
            apply_boxes = soup.select('div.apply_box')

            if apply_boxes:
                logger.info(f"Found {len(apply_boxes)} job listing boxes (div.apply_box)")

                for idx, box in enumerate(apply_boxes, 1):
                    try:
                        job_data = self._extract_job_from_apply_box(box, idx)
                        if job_data:
                            # Deduplicate: the page renders job boxes twice
                            # (once for desktop, once for mobile)
                            dedup_key = f"{job_data['title']}|{job_data['apply_url']}"
                            if dedup_key not in seen_titles:
                                seen_titles.add(dedup_key)
                                all_jobs.append(job_data)
                                logger.info(f"Extracted: {job_data['title']} | {job_data['location']}")
                            else:
                                logger.debug(f"Skipping duplicate: {job_data['title']}")
                    except Exception as e:
                        logger.error(f"Error parsing apply_box {idx}: {str(e)}")
                        continue
            else:
                # Fallback: look for div.one_ap elements directly
                logger.info("No div.apply_box found, trying div.one_ap")
                one_ap_divs = soup.select('div.one_ap')
                if one_ap_divs:
                    for idx, ap_div in enumerate(one_ap_divs, 1):
                        try:
                            job_data = self._extract_job_from_one_ap(ap_div, idx)
                            if job_data:
                                dedup_key = f"{job_data['title']}|{job_data['apply_url']}"
                                if dedup_key not in seen_titles:
                                    seen_titles.add(dedup_key)
                                    all_jobs.append(job_data)
                        except Exception as e:
                            logger.error(f"Error parsing one_ap {idx}: {str(e)}")
                            continue

            if not all_jobs:
                logger.info("No structured job elements found, trying heading-based extraction")
                all_jobs = self._extract_from_headings(soup)

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _extract_job_from_apply_box(self, box, idx):
        """Extract job data from a div.apply_box container.

        Structure:
            <div class="apply_box ...">
                <h3>Analyst</h3>
                <div class="one_ap">
                    <h4>Regulatory affairs</h4>
                    <p>Location - Hyderabad, India  Experience - 3+ Year</p>
                    <a href="...">Read More</a>
                </div>
            </div>
        """
        h3 = box.find('h3')
        h4 = box.find('h4')
        one_ap = box.select_one('div.one_ap')

        # Build the job title from h3 + h4
        role = h3.get_text(strip=True) if h3 else ''
        specialization = h4.get_text(strip=True) if h4 else ''

        if specialization and role:
            title = f"{role} - {specialization}"
        elif role:
            title = role
        elif specialization:
            title = specialization
        else:
            return None

        if not title or len(title) < 3:
            return None

        # Extract location and experience from paragraph text
        location = ''
        experience = ''
        search_elem = one_ap if one_ap else box
        for p in search_elem.find_all('p'):
            text = p.get_text(strip=True)
            # Parse "Location - Hyderabad, India  Experience - 3+ Year"
            loc_match = re.search(r'Location\s*[-:]\s*(.+?)(?:Experience|$)', text, re.IGNORECASE)
            if loc_match:
                location = loc_match.group(1).strip().rstrip(',').strip()
            exp_match = re.search(r'Experience\s*[-:]\s*(.+)', text, re.IGNORECASE)
            if exp_match:
                experience = exp_match.group(1).strip()

        # Extract the "Read More" link
        job_url = self.url
        link = search_elem.find('a', href=True)
        if link:
            href = link.get('href', '')
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                job_url = href if href.startswith('http') else f"https://granulesindia.com{href}"

        # Generate unique ID
        job_id_str = f"{title}_{job_url}"
        job_id = hashlib.md5(job_id_str.encode()).hexdigest()[:12]
        external_id = self.generate_external_id(job_id, self.company_name)

        location_parts = self.parse_location(location)

        return {
            'external_id': external_id,
            'company_name': self.company_name,
            'title': title,
            'description': f"Experience: {experience}" if experience else '',
            'location': location,
            'city': location_parts['city'],
            'state': location_parts['state'],
            'country': location_parts['country'],
            'employment_type': '',
            'department': '',
            'apply_url': job_url,
            'posted_date': '',
            'job_function': '',
            'experience_level': experience,
            'salary_range': '',
            'remote_type': '',
            'status': 'active'
        }

    def _extract_job_from_one_ap(self, ap_div, idx):
        """Extract job data from a standalone div.one_ap element."""
        h4 = ap_div.find('h4')
        title = h4.get_text(strip=True) if h4 else ''

        # Check parent for h3
        parent = ap_div.parent
        if parent:
            h3 = parent.find('h3')
            if h3:
                role = h3.get_text(strip=True)
                if role and title:
                    title = f"{role} - {title}"
                elif role:
                    title = role

        if not title or len(title) < 3:
            return None

        location = ''
        experience = ''
        for p in ap_div.find_all('p'):
            text = p.get_text(strip=True)
            loc_match = re.search(r'Location\s*[-:]\s*(.+?)(?:Experience|$)', text, re.IGNORECASE)
            if loc_match:
                location = loc_match.group(1).strip().rstrip(',').strip()
            exp_match = re.search(r'Experience\s*[-:]\s*(.+)', text, re.IGNORECASE)
            if exp_match:
                experience = exp_match.group(1).strip()

        job_url = self.url
        link = ap_div.find('a', href=True)
        if link:
            href = link.get('href', '')
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                job_url = href if href.startswith('http') else f"https://granulesindia.com{href}"

        job_id_str = f"{title}_{job_url}"
        job_id = hashlib.md5(job_id_str.encode()).hexdigest()[:12]
        external_id = self.generate_external_id(job_id, self.company_name)

        location_parts = self.parse_location(location)

        return {
            'external_id': external_id,
            'company_name': self.company_name,
            'title': title,
            'description': f"Experience: {experience}" if experience else '',
            'location': location,
            'city': location_parts['city'],
            'state': location_parts['state'],
            'country': location_parts['country'],
            'employment_type': '',
            'department': '',
            'apply_url': job_url,
            'posted_date': '',
            'job_function': '',
            'experience_level': experience,
            'salary_range': '',
            'remote_type': '',
            'status': 'active'
        }

    def _extract_from_headings(self, soup):
        """Fallback extraction using heading tags that look like job titles."""
        jobs = []
        seen_titles = set()

        # Look for headings within the main content area, excluding product popups
        main_content = soup.select_one('main, article, .content, .entry-content, #content') or soup

        # Only look at h3/h4 inside apply_box or panel-widget-style containers
        # Exclude product popups (class p_popup) and footer
        headings = main_content.select('h3, h4')

        for heading in headings:
            title = heading.get_text(strip=True)
            if not title or len(title) < 5 or len(title) > 200:
                continue

            # Skip product names (inside p_popup divs) and navigation headings
            parent_classes = []
            p = heading.parent
            while p and p.name != 'body':
                parent_classes.extend(p.get('class', []))
                p = p.parent

            parent_cls_str = ' '.join(parent_classes)
            # Skip product popup sections, footer, and navigation
            if any(kw in parent_cls_str for kw in ['p_popup', 'footer', 'modal', 'mega-menu']):
                continue

            # Skip generic navigation/section headings
            skip_words = ['menu', 'navigation', 'footer', 'header', 'sidebar', 'widget',
                          'comment', 'search', 'archive', 'category', 'tag', 'current openings',
                          'career', 'about', 'contact', 'company', 'investors', 'business',
                          'connect', 'bonthapally', 'jeedimetla', 'paravada', 'chantilly',
                          'gagillapur']
            if any(word in title.lower() for word in skip_words):
                continue

            if title in seen_titles:
                continue
            seen_titles.add(title)

            link = heading.find('a')
            job_url = self.url
            if link and link.get('href'):
                href = link.get('href', '')
                if href and not href.startswith('#') and not href.startswith('javascript:'):
                    job_url = href if href.startswith('http') else f"https://granulesindia.com{href}"

            description = ''
            next_elem = heading.find_next_sibling()
            if next_elem and next_elem.name in ['p', 'div', 'ul']:
                description = next_elem.get_text(strip=True)[:2000]

            job_id = hashlib.md5(title.encode()).hexdigest()[:12]
            external_id = self.generate_external_id(job_id, self.company_name)

            job_data = {
                'external_id': external_id,
                'company_name': self.company_name,
                'title': title,
                'description': description,
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

        return jobs


if __name__ == "__main__":
    scraper = GranulesScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['apply_url']}")

import requests
import hashlib
import re
from bs4 import BeautifulSoup

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('jkbank_scraper')


class JKBankScraper:
    def __init__(self):
        self.company_name = 'Jammu and Kashmir Bank'
        # The bank migrated to jkb.bank.in; old domains redirect here
        self.url = 'https://jkb.bank.in/career'
        self.alt_urls = [
            'https://www.jkbank.com/career',
        ]
        self.base_url = 'https://jkb.bank.in'
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
        """Try multiple URLs to fetch the careers page."""
        urls_to_try = [self.url] + self.alt_urls

        for url in urls_to_try:
            try:
                logger.info(f"Trying URL: {url}")
                response = requests.get(url, headers=self.headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
                logger.info(f"Successfully fetched from: {response.url}")
                return response
            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to fetch {url}: {str(e)}")
                continue

        return None

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []

        try:
            logger.info(f"Starting {self.company_name} scraping")

            response = self._fetch_page()
            if not response:
                logger.error("Failed to fetch career page from all URLs")
                return all_jobs

            soup = BeautifulSoup(response.text, 'html.parser')
            final_url = response.url.rstrip('/')
            # Determine base URL from the final redirected URL
            base_url = re.match(r'(https?://[^/]+)', final_url)
            base_url = base_url.group(1) if base_url else self.base_url

            # The JK Bank careers page at jkb.bank.in/career uses a Drupal-based
            # structure with:
            #   div.career-page > div.job-listings > div.job-card elements
            #
            # Each div.job-card contains:
            #   - h3: job title / notification title
            #   - div.job-details:
            #       - span.location: category (e.g., "General", "CFO")
            #       - span.posted: posting date (e.g., "Posted 1 day ago")
            #   - a.apply-btn: link to PDF notification or online application

            job_cards = soup.select('div.job-card')

            if job_cards:
                logger.info(f"Found {len(job_cards)} job cards (div.job-card)")
                seen_ids = set()

                for idx, card in enumerate(job_cards, 1):
                    try:
                        job_data = self._extract_job_from_card(card, base_url)
                        if job_data and job_data['external_id'] not in seen_ids:
                            all_jobs.append(job_data)
                            seen_ids.add(job_data['external_id'])
                            logger.info(f"Extracted: {job_data['title'][:80]}")
                    except Exception as e:
                        logger.error(f"Error parsing job card {idx}: {str(e)}")
                        continue
            else:
                # Fallback: look for links that look like job postings
                logger.info("No div.job-card elements found, trying link-based extraction")
                all_jobs = self._extract_from_links(soup, base_url)

            # Check for pagination (the page may have multiple pages)
            # JK Bank uses Drupal views pager
            if len(all_jobs) > 0:
                page = 1
                while page < max_pages:
                    pager_next = soup.select_one('li.pager__item--next a, a.page-link[rel="next"]')
                    if not pager_next:
                        break
                    next_href = pager_next.get('href', '')
                    if not next_href:
                        break
                    next_url = next_href if next_href.startswith('http') else base_url + next_href
                    logger.info(f"Fetching page {page + 1}: {next_url}")
                    try:
                        resp = requests.get(next_url, headers=self.headers, timeout=30, allow_redirects=True)
                        resp.raise_for_status()
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        next_cards = soup.select('div.job-card')
                        if not next_cards:
                            break
                        added = 0
                        seen_ids = {j['external_id'] for j in all_jobs}
                        for card in next_cards:
                            jd = self._extract_job_from_card(card, base_url)
                            if jd and jd['external_id'] not in seen_ids:
                                all_jobs.append(jd)
                                seen_ids.add(jd['external_id'])
                                added += 1
                        logger.info(f"Page {page + 1}: added {added} jobs")
                        if added == 0:
                            break
                        page += 1
                    except Exception as e:
                        logger.warning(f"Failed to fetch page {page + 1}: {str(e)}")
                        break

            logger.info(f"Successfully scraped {len(all_jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        return all_jobs

    def _extract_job_from_card(self, card, base_url):
        """Extract job data from a div.job-card element.

        Structure:
            <div class="job-card">
                <div class="highlight"></div>
                <h3>Job title / notification text</h3>
                <div class="job-details">
                    <span class="location">General</span>
                    <span class="posted"><i class="fas fa-clock"></i> Posted 1 day ago</span>
                </div>
                <a class="apply-btn" href="..." target="_blank">Apply Online / Know More</a>
            </div>
        """
        # Extract title from h3
        h3 = card.find('h3')
        if not h3:
            return None
        title = h3.get_text(strip=True)
        if not title or len(title) < 5:
            return None

        # Extract category from span.location
        category = ''
        location_span = card.select_one('div.job-details span.location')
        if location_span:
            category = location_span.get_text(strip=True)

        # Extract posted date from span.posted
        posted_date = ''
        posted_span = card.select_one('div.job-details span.posted')
        if posted_span:
            posted_date = posted_span.get_text(strip=True)
            # Clean up: remove icon text
            posted_date = re.sub(r'^\s*', '', posted_date).strip()

        # Extract link
        job_url = self.url
        link_text = ''
        apply_link = card.select_one('a.apply-btn') or card.find('a', href=True)
        if apply_link:
            href = apply_link.get('href', '')
            link_text = apply_link.get_text(strip=True)
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                if href.startswith('http'):
                    job_url = href
                elif href.startswith('/'):
                    job_url = base_url + href
                else:
                    job_url = base_url + '/' + href

        # Build description
        desc_parts = []
        if category:
            desc_parts.append(f"Category: {category}")
        if posted_date:
            desc_parts.append(posted_date)
        if link_text:
            desc_parts.append(f"Action: {link_text}")
        description = ' | '.join(desc_parts)

        # Generate job ID from title + URL to ensure uniqueness
        job_id_str = f"{title}_{job_url}"
        job_id = hashlib.md5(job_id_str.encode()).hexdigest()[:12]
        external_id = self.generate_external_id(job_id, self.company_name)

        return {
            'external_id': external_id,
            'company_name': self.company_name,
            'title': title,
            'description': description,
            'location': 'Jammu and Kashmir',
            'city': 'Srinagar',
            'state': 'Jammu and Kashmir',
            'country': 'India',
            'employment_type': '',
            'department': category,
            'apply_url': job_url,
            'posted_date': posted_date,
            'job_function': '',
            'experience_level': '',
            'salary_range': '',
            'remote_type': '',
            'status': 'active'
        }

    def _extract_from_links(self, soup, base_url):
        """Fallback: extract jobs from links that look like job postings."""
        jobs = []
        seen_titles = set()

        all_links = soup.find_all('a', href=True)

        for link in all_links:
            href = link.get('href', '')
            title = link.get_text(strip=True)

            if not title or len(title) < 5 or len(title) > 300:
                continue

            href_lower = href.lower()
            title_lower = title.lower()
            job_keywords = ['recruitment', 'vacancy', 'opening', 'position', 'job',
                           'notification', 'appointment', 'engagement', 'advertisement',
                           'officer', 'consultant', 'auditor', 'apprentice',
                           'chartered', 'associate']

            is_job = any(kw in href_lower or kw in title_lower for kw in job_keywords)
            if not is_job:
                continue

            skip_words = ['menu', 'login', 'register', 'home', 'about', 'contact',
                          'privacy', 'terms', 'faq', 'help', 'footer']
            if any(word in title_lower for word in skip_words):
                continue

            if title in seen_titles:
                continue
            seen_titles.add(title)

            if href.startswith('http'):
                job_url = href
            elif href.startswith('/'):
                job_url = base_url + href
            else:
                job_url = base_url + '/' + href

            job_id = hashlib.md5(title.encode()).hexdigest()[:12]
            external_id = self.generate_external_id(job_id, self.company_name)

            job_data = {
                'external_id': external_id,
                'company_name': self.company_name,
                'title': title,
                'description': '',
                'location': 'Jammu and Kashmir',
                'city': 'Srinagar',
                'state': 'Jammu and Kashmir',
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
            logger.info(f"Extracted (link): {title[:80]}")

        return jobs


if __name__ == "__main__":
    scraper = JKBankScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title'][:80]} | {job['location']} | {job['apply_url'][:80]}")

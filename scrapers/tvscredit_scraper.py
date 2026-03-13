from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('tvscredit_scraper')

class TVSCreditScraper:
    def __init__(self):
        self.company_name = "TVS Credit"
        self.url = "https://tvscredit.talentrecruit.com/career-page"
        self.alt_url = 'https://www.tvscredit.com/careers/current-openings/'
        self.base_url = 'https://tvscredit.talentrecruit.com'
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) >= 1 else ''
        state = parts[1] if len(parts) >= 2 else ''
        return city, state, 'India'

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from TVS Credit — try TalentRecruit first, fallback to main website"""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Strategy 1: TalentRecruit career page
            jobs = self._scrape_talentrecruit(driver, max_pages)

            if jobs:
                logger.info(f"TalentRecruit scraping found {len(jobs)} jobs")
            else:
                # Strategy 2: Fallback to main website careers page
                logger.info("TalentRecruit returned no jobs (may be blocked), trying main website")
                jobs = self._scrape_main_website(driver)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _scrape_talentrecruit(self, driver, max_pages=1):
        """Scrape from TalentRecruit career page SPA"""
        jobs = []

        try:
            logger.info(f"Navigating to TalentRecruit: {self.url}")
            driver.get(self.url)

            # TalentRecruit SPA needs time to render; they also block bots
            time.sleep(15)

            # Check if we got blocked (403 or access denied)
            page_source = driver.page_source.lower()
            if '403' in page_source or 'access denied' in page_source or 'forbidden' in page_source:
                logger.warning("TalentRecruit returned 403/access denied, will try fallback")
                return jobs

            # Scroll to trigger lazy loading
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            for page in range(max_pages):
                page_jobs = self._extract_talentrecruit_jobs(driver)

                if not page_jobs:
                    if page == 0:
                        logger.warning("No jobs found on TalentRecruit page")
                    break

                jobs.extend(page_jobs)
                logger.info(f"Page {page + 1}: found {len(page_jobs)} jobs (total: {len(jobs)})")

                if not self._go_to_next_page(driver):
                    break
                time.sleep(5)

        except Exception as e:
            logger.error(f"TalentRecruit scraping error: {str(e)}")

        return jobs

    def _extract_talentrecruit_jobs(self, driver):
        """Extract job listings from TalentRecruit DOM"""
        jobs = []

        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // TalentRecruit specific selectors
                // Strategy 1: TalentRecruit job card/listing elements
                var cards = document.querySelectorAll('.job-card, .job-listing, .job-item, [class*="job-card"], [class*="jobCard"], [class*="job-listing"], [class*="jobListing"], [class*="career-card"]');
                if (cards.length === 0) {
                    cards = document.querySelectorAll('[class*="job"], [class*="opening"], [class*="position"], [class*="vacancy"], [class*="listing"]');
                }

                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = card.innerText.trim();
                    if (text.length < 5 || text.length > 2000) continue;

                    var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="name"], [class*="designation"], strong, a');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title) title = text.split('\\n')[0].trim();
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (title.match(/^(Home|About|Contact|Login|Sign|Menu|Close|Apply|Submit|TVS Credit)/i)) continue;

                    var locEl = card.querySelector('[class*="location"], [class*="city"], [class*="place"], [class*="loc"]');
                    var location = locEl ? locEl.innerText.trim() : '';
                    if (!location) {
                        var lines = text.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            var line = lines[j].trim();
                            if (line.match(/Chennai|Mumbai|Delhi|Bangalore|Bengaluru|Hyderabad|Pune|Kolkata|Gurgaon|Gurugram|Pan India|Multiple/i)) {
                                location = line;
                                break;
                            }
                        }
                    }

                    var deptEl = card.querySelector('[class*="department"], [class*="dept"], [class*="team"], [class*="category"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';

                    var linkEl = card.querySelector('a[href]');
                    var url = linkEl ? linkEl.href : '';

                    if (!seen[title + location]) {
                        seen[title + location] = true;
                        results.push({title: title, location: location, department: department, url: url});
                    }
                }

                // Strategy 2: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var cells = rows[i].querySelectorAll('td');
                        if (cells.length < 1) continue;
                        var title = cells[0].innerText.trim();
                        if (!title || title.length < 3) continue;
                        var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                        var department = cells.length > 2 ? cells[2].innerText.trim() : '';
                        var link = rows[i].querySelector('a[href]');
                        var url = link ? link.href : '';

                        if (!seen[title + location]) {
                            seen[title + location] = true;
                            results.push({title: title, location: location, department: department, url: url});
                        }
                    }
                }

                // Strategy 3: Accordion/expandable panels
                if (results.length === 0) {
                    var panels = document.querySelectorAll('[class*="accordion"], [class*="panel"], [class*="collapse"], [class*="expand"]');
                    for (var i = 0; i < panels.length; i++) {
                        var titleEl = panels[i].querySelector('h2, h3, h4, h5, button, a, [class*="title"], [class*="header"]');
                        if (!titleEl) continue;
                        var title = titleEl.innerText.trim();
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (seen[title]) continue;
                        seen[title] = true;
                        results.push({title: title, location: '', department: '', url: ''});
                    }
                }

                // Strategy 4: Link-based extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href || '';
                        if (text.length > 3 && text.length < 200 && !seen[text]) {
                            if (href.includes('job') || href.includes('career') || href.includes('opening') || href.includes('position') || href.includes('apply') || href.includes('detail')) {
                                if (!href.includes('login') && !href.includes('javascript:') && !href.includes('#') && text !== 'Apply' && text !== 'Apply Now') {
                                    seen[text] = true;
                                    results.push({title: text, location: '', department: '', url: href});
                                }
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"TalentRecruit extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    url = job_data.get('url', '')

                    if not title or len(title) < 3:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    job_id = hashlib.md5(f"{title}_{location}_{idx}".encode()).hexdigest()[:12]
                    if url:
                        job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })

        except Exception as e:
            logger.error(f"TalentRecruit extraction error: {str(e)}")

        return jobs

    def _scrape_main_website(self, driver):
        """Fallback: Scrape from TVS Credit main website careers page"""
        jobs = []

        try:
            logger.info(f"Navigating to main website: {self.alt_url}")
            driver.get(self.alt_url)
            time.sleep(12)

            # Scroll to load content
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)

            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Job listing elements on main website
                var cards = document.querySelectorAll('[class*="job"], [class*="career"], [class*="opening"], [class*="position"], [class*="vacancy"], [class*="listing"], [class*="opportunity"]');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = card.innerText.trim();
                    if (text.length < 10 || text.length > 2000) continue;

                    var titleEl = card.querySelector('h2, h3, h4, h5, [class*="title"], [class*="name"], strong, a');
                    var title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                    if (!title) title = text.split('\\n')[0].trim();
                    if (!title || title.length < 3 || title.length > 200) continue;
                    if (title.match(/^(Home|About|Contact|Login|Sign|Menu|Close|TVS Credit|Current)/i)) continue;

                    var locEl = card.querySelector('[class*="location"], [class*="city"]');
                    var location = locEl ? locEl.innerText.trim() : '';

                    var deptEl = card.querySelector('[class*="department"], [class*="dept"], [class*="team"]');
                    var department = deptEl ? deptEl.innerText.trim() : '';

                    var linkEl = card.querySelector('a[href]');
                    var url = linkEl ? linkEl.href : '';

                    if (!seen[title + location]) {
                        seen[title + location] = true;
                        results.push({title: title, location: location, department: department, url: url});
                    }
                }

                // Strategy 2: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr');
                    for (var i = 0; i < rows.length; i++) {
                        var cells = rows[i].querySelectorAll('td');
                        if (cells.length < 1) continue;
                        var title = cells[0].innerText.trim();
                        if (!title || title.length < 3) continue;
                        var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                        var link = rows[i].querySelector('a[href]');
                        var url = link ? link.href : '';

                        if (!seen[title]) {
                            seen[title] = true;
                            results.push({title: title, location: location, department: '', url: url});
                        }
                    }
                }

                // Strategy 3: Accordion sections (common in WordPress career pages)
                if (results.length === 0) {
                    var accordions = document.querySelectorAll('[class*="accordion"], [class*="toggle"], [class*="collapse"], [class*="faq"], details');
                    for (var i = 0; i < accordions.length; i++) {
                        var titleEl = accordions[i].querySelector('h2, h3, h4, h5, summary, button, [class*="title"], [class*="header"]');
                        if (!titleEl) continue;
                        var title = titleEl.innerText.trim();
                        if (!title || title.length < 3 || title.length > 200) continue;
                        if (title.match(/^(Home|About|Contact|Login|FAQ)/i)) continue;
                        if (seen[title]) continue;
                        seen[title] = true;

                        var body = accordions[i].querySelector('[class*="body"], [class*="content"], [class*="panel"]');
                        var bodyText = body ? body.innerText.trim() : '';
                        var location = '';
                        if (bodyText.match(/Chennai|Mumbai|Delhi|Bangalore|Bengaluru|Hyderabad|Pune/i)) {
                            var m = bodyText.match(/(Chennai|Mumbai|Delhi|Bangalore|Bengaluru|Hyderabad|Pune|Kolkata|Gurgaon|Gurugram)/i);
                            if (m) location = m[1];
                        }
                        results.push({title: title, location: location, department: '', url: ''});
                    }
                }

                // Strategy 4: Link-based extraction
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href]');
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        var href = links[i].href || '';
                        if (text.length > 5 && text.length < 200 && !seen[text]) {
                            if (href.includes('career') || href.includes('job') || href.includes('opening') || href.includes('position') || href.includes('apply')) {
                                if (!href.includes('login') && !href.includes('javascript:') && !href.includes('#')) {
                                    seen[text] = true;
                                    results.push({title: text, location: '', department: '', url: href});
                                }
                            }
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Main website extraction found {len(js_jobs)} jobs")
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    location = job_data.get('location', '')
                    department = job_data.get('department', '')
                    url = job_data.get('url', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5(f"{title}_{location}_{idx}".encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': department,
                        'apply_url': url if url else self.alt_url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found on main website either")
                try:
                    body_text = driver.execute_script('return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Main page body preview: {body_text}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Main website scraping error: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        """Try to navigate to the next page"""
        try:
            result = driver.execute_script("""
                var selectors = [
                    '.pagination .next a', '.pagination li.next a',
                    'a[aria-label="Next"]', 'button[aria-label="Next"]',
                    'a.next-page', 'a[rel="next"]',
                    '[class*="pagination"] [class*="next"]',
                    'button[class*="next"]', 'a[class*="next"]',
                    'button[class*="load-more"]', 'a[class*="load-more"]',
                ];

                for (var i = 0; i < selectors.length; i++) {
                    var btn = document.querySelector(selectors[i]);
                    if (btn && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                }

                // Try text-based buttons
                var xpath = '//a[contains(text(), "Next")] | //button[contains(text(), "Next")] | //button[contains(text(), "Load More")] | //button[contains(text(), "Show More")]';
                var result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                if (result.singleNodeValue && result.singleNodeValue.offsetParent !== null) {
                    result.singleNodeValue.click();
                    return true;
                }

                return false;
            """)
            if result:
                logger.info("Navigated to next page")
            return result
        except Exception:
            return False

if __name__ == '__main__':
    scraper = TVSCreditScraper()
    results = scraper.scrape()
    print(f"\nTotal jobs found: {len(results)}")
    for job in results[:10]:
        print(f"  - {job['title']} | {job['location']} | {job['department']} | {job['apply_url']}")

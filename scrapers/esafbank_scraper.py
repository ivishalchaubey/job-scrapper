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

logger = setup_logger('esafbank_scraper')

class ESAFBankScraper:
    def __init__(self):
        self.company_name = "ESAF Small Finance Bank"
        self.url = "https://esafcareers.zappyhire.com/#/"
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_location(self, location_str):
        if not location_str:
            return '', '', 'India'
        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''
        return city, state, 'India'

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from ESAF Bank Zappyhire careers page (extremely JS-heavy SPA)."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)

            # Zappyhire is extremely JS-heavy — zero content in initial HTML
            logger.info("Waiting 15s for Zappyhire JS-heavy SPA to fully render...")
            time.sleep(15)

            # Scroll to trigger lazy-loaded content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try to click Load More / Show More buttons
            for _ in range(max_pages):
                try:
                    load_more = driver.find_elements(By.XPATH,
                        '//button[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View More") or contains(text(),"See More")]'
                        ' | //a[contains(text(),"Load More") or contains(text(),"Show More") or contains(text(),"View More") or contains(text(),"See More")]'
                        ' | //div[contains(text(),"Load More") or contains(text(),"Show More")]')
                    if load_more:
                        driver.execute_script("arguments[0].click();", load_more[0])
                        logger.info("Clicked 'Load More' button")
                        time.sleep(3)
                    else:
                        break
                except Exception:
                    break

            # Extract jobs from the rendered DOM
            jobs = self._extract_jobs_js(driver)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs_js(self, driver):
        """Extract jobs from Zappyhire page using JavaScript."""
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Strategy 1: Job card elements (Zappyhire-specific)
                var selectors = [
                    '.job-card', '.position', '.opening',
                    '[class*="job-card"]', '[class*="jobCard"]', '[class*="job_card"]',
                    '[class*="position-card"]', '[class*="opening-card"]',
                    '[class*="job-item"]', '[class*="jobItem"]',
                    '[class*="vacancy"]', '[class*="career-item"]',
                    'div[class*="listing"]', 'div[class*="job-list"] > div',
                    'div[class*="job-list"] > li', 'ul[class*="job"] > li'
                ];

                for (var s = 0; s < selectors.length; s++) {
                    var cards = document.querySelectorAll(selectors[s]);
                    if (cards.length > 0) {
                        for (var i = 0; i < cards.length; i++) {
                            var card = cards[i];
                            var title = '';
                            var href = '';
                            var location = '';
                            var department = '';

                            // Get title from heading or link
                            var heading = card.querySelector('h1, h2, h3, h4, h5, a');
                            if (heading) {
                                title = heading.innerText.trim().split('\\n')[0].trim();
                                if (heading.tagName === 'A') href = heading.href;
                            }
                            if (!title) {
                                var firstLink = card.querySelector('a');
                                if (firstLink) {
                                    title = firstLink.innerText.trim().split('\\n')[0].trim();
                                    href = firstLink.href;
                                }
                            }
                            if (!href) {
                                var aTag = card.querySelector('a[href]');
                                if (aTag) href = aTag.href;
                            }

                            // Get location
                            var locEl = card.querySelector('[class*="location"], [class*="Location"], [class*="place"], [class*="city"]');
                            if (locEl) location = locEl.innerText.trim();

                            // Get department
                            var deptEl = card.querySelector('[class*="department"], [class*="Department"], [class*="category"], [class*="team"]');
                            if (deptEl) department = deptEl.innerText.trim();

                            if (title && title.length > 2 && title.length < 300 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({title: title, href: href, location: location, department: department});
                            }
                        }
                        if (results.length > 0) break;
                    }
                }

                // Strategy 2: Links with job-related hrefs
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="job"], a[href*="position"], a[href*="opening"], a[href*="career"]');
                    for (var i = 0; i < links.length; i++) {
                        var link = links[i];
                        var text = link.innerText.trim().split('\\n')[0].trim();
                        var lhref = link.href;
                        if (text.length > 3 && text.length < 200 && !seen[text + lhref]) {
                            seen[text + lhref] = true;
                            var parent = link.closest('div, li, tr, section');
                            var loc = '';
                            var dept = '';
                            if (parent) {
                                var locEl = parent.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl && locEl !== link) loc = locEl.innerText.trim();
                                var deptEl = parent.querySelector('[class*="department"], [class*="Department"]');
                                if (deptEl && deptEl !== link) dept = deptEl.innerText.trim();
                            }
                            results.push({title: text, href: lhref, location: loc, department: dept});
                        }
                    }
                }

                // Strategy 3: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tbody tr, table tr, div[role="row"]');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        var cells = row.querySelectorAll('td, div[role="cell"]');
                        if (cells.length >= 1) {
                            var titleCell = cells[0];
                            var link = titleCell.querySelector('a');
                            var title = titleCell.innerText.trim().split('\\n')[0].trim();
                            var href = link ? link.href : '';
                            var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                            var dept = cells.length > 2 ? cells[2].innerText.trim() : '';
                            if (title.length > 3 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({title: title, href: href, location: location, department: dept});
                            }
                        }
                    }
                }

                // Strategy 4: Body text parsing fallback — find any structured text blocks
                if (results.length === 0) {
                    var allDivs = document.querySelectorAll('div, li, article, section');
                    for (var i = 0; i < allDivs.length; i++) {
                        var el = allDivs[i];
                        if (el.children.length > 5) continue;  // Skip containers
                        var text = el.innerText.trim();
                        if (text.length < 5 || text.length > 500) continue;

                        var link = el.querySelector('a[href]');
                        var lines = text.split('\\n').filter(function(l) { return l.trim().length > 0; });
                        if (lines.length < 1) continue;

                        var title = lines[0].trim();
                        var href = link ? link.href : '';
                        if (title.length > 3 && title.length < 200 && !seen[title]) {
                            // Check if it looks like a job title (not navigation, etc.)
                            var lowerTitle = title.toLowerCase();
                            if (lowerTitle.includes('apply') || lowerTitle.includes('search') ||
                                lowerTitle.includes('filter') || lowerTitle.includes('menu') ||
                                lowerTitle.includes('home') || lowerTitle.includes('about') ||
                                lowerTitle.includes('contact') || lowerTitle.includes('login') ||
                                lowerTitle.includes('sign')) continue;

                            seen[title] = true;
                            var loc = '';
                            for (var li = 1; li < lines.length; li++) {
                                var line = lines[li].trim();
                                if (line.match(/India|Kerala|Tamil Nadu|Karnataka|Mumbai|Bangalore|Chennai|Hyderabad|Delhi|Pune|Kochi|Thrissur|Trivandrum|Calicut|Kozhikode/i)) {
                                    loc = line;
                                    break;
                                }
                            }
                            results.push({title: title, href: href, location: loc, department: ''});
                        }
                    }
                }

                return results;
            """)

            if job_data:
                logger.info(f"JS extraction found {len(job_data)} jobs")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '')
                    href = jd.get('href', '')
                    location = jd.get('location', '')
                    department = jd.get('department', '')

                    if not title or len(title) < 3:
                        continue

                    job_id = hashlib.md5((href or f"{title}_{idx}").encode()).hexdigest()[:12]
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
                        'apply_url': href if href else self.url,
                        'posted_date': '',
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found on Zappyhire page")

        except Exception as e:
            logger.error(f"JS extraction failed: {e}")

        return jobs

if __name__ == "__main__":
    scraper = ESAFBankScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

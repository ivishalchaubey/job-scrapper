from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
from datetime import datetime
from pathlib import Path

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('marutisuzuki_scraper')

# The old URL /corporate/career/current-openings returns 404 (page was removed).
# Maruti Suzuki now uses /corporate/careers as the main careers page, with
# sub-pages for workmen hiring and external links to Param AI for professional roles.
CAREERS_URL = 'https://www.marutisuzuki.com/corporate/careers'
WORKMEN_HIRING_URL = 'https://www.marutisuzuki.com/corporate/careers/join-us/workmen-hiring'
PARAM_AI_URL = 'https://maruti.app.param.ai/jobs/'

class MarutiSuzukiScraper:
    def __init__(self):
        self.company_name = "Maruti Suzuki"
        self.url = CAREERS_URL
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from all Maruti Suzuki career sources."""
        all_jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # 1. Scrape the workmen-hiring page (Apprentice + Flexi Workmen positions)
            workmen_jobs = self._scrape_workmen_hiring(driver)
            all_jobs.extend(workmen_jobs)
            logger.info(f"Workmen hiring page: {len(workmen_jobs)} jobs")

            # 2. Scrape the main careers page overlay cards
            #    (Freshers, Engineering Hiring, Experienced Professionals)
            careers_jobs = self._scrape_careers_page(driver)
            all_jobs.extend(careers_jobs)
            logger.info(f"Main careers page: {len(careers_jobs)} jobs")

            # 3. Try Param AI for any active professional job openings
            param_jobs = self._scrape_param_ai(driver)
            all_jobs.extend(param_jobs)
            logger.info(f"Param AI: {len(param_jobs)} jobs")

            # Deduplicate by external_id
            seen = set()
            unique_jobs = []
            for job in all_jobs:
                if job['external_id'] not in seen:
                    seen.add(job['external_id'])
                    unique_jobs.append(job)
            all_jobs = unique_jobs

            logger.info(f"Successfully scraped {len(all_jobs)} total unique jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return all_jobs

    # ------------------------------------------------------------------
    # Workmen Hiring (ITI) page
    # ------------------------------------------------------------------
    def _scrape_workmen_hiring(self, driver):
        """Scrape ITI Apprentice and Flexi Workmen positions."""
        jobs = []
        try:
            logger.info(f"Navigating to workmen hiring: {WORKMEN_HIRING_URL}")
            driver.get(WORKMEN_HIRING_URL)
            time.sleep(10)

            # The page has two tabs: Apprentice (#home) and Flexi Workmen (#menu1).
            # Each tab has Overview, Selection Process, Eligibility panels.
            positions = driver.execute_script("""
                var positions = [];

                // Helper: extract key-value pairs from overview text
                function extractDetails(el) {
                    var text = el ? el.innerText.trim() : '';
                    var details = {};
                    var lines = text.split('\\n').map(function(l) { return l.trim(); }).filter(Boolean);
                    var keys = ['Location', 'Duration', 'Stipend', 'Salary', 'Other Benefits'];
                    for (var i = 0; i < lines.length; i++) {
                        for (var k = 0; k < keys.length; k++) {
                            if (lines[i].toLowerCase().startsWith(keys[k].toLowerCase())) {
                                // Value is on the next non-empty line
                                for (var j = i+1; j < lines.length; j++) {
                                    var val = lines[j].replace(/^["']|["']$/g, '').trim();
                                    if (val && val.toLowerCase() !== lines[i].toLowerCase()) {
                                        details[keys[k].toLowerCase()] = val;
                                        break;
                                    }
                                }
                            }
                        }
                    }
                    details.fullText = text;
                    return details;
                }

                // Helper: extract trades from eligibility text
                function extractTrades(el) {
                    var text = el ? el.innerText.trim() : '';
                    var tradesMatch = text.match(/Trades[\\s\\S]*?(?=Age|$)/i);
                    return tradesMatch ? tradesMatch[0].replace(/^Trades\\s*/i, '').trim() : '';
                }

                // Tab 1: Apprentice (pane #home -> #Overview)
                var overviewApp = document.querySelector('#Overview');
                var eligApp = document.querySelector('#Eligibility');
                if (overviewApp) {
                    var d = extractDetails(overviewApp);
                    positions.push({
                        title: 'ITI Apprentice',
                        category: 'Workmen Hiring (ITI)',
                        location: d.location || 'Gurgaon / Manesar',
                        duration: d.duration || '',
                        salary: d.stipend || d.salary || '',
                        benefits: d['other benefits'] || '',
                        trades: extractTrades(eligApp),
                        description: d.fullText || '',
                        applyUrl: 'https://www.justjob.co.in/jobseeker/vitw.aspx'
                    });
                }

                // Tab 2: Flexi Workmen (pane #menu1 -> #Overview1)
                var overviewFlexi = document.querySelector('#Overview1');
                var eligFlexi = document.querySelector('#Eligibility1');
                if (overviewFlexi) {
                    var d2 = extractDetails(overviewFlexi);
                    positions.push({
                        title: 'ITI Flexi Workmen',
                        category: 'Workmen Hiring (ITI)',
                        location: d2.location || 'Gurgaon / Manesar',
                        duration: d2.duration || '',
                        salary: d2.salary || d2.stipend || '',
                        benefits: d2['other benefits'] || '',
                        trades: extractTrades(eligFlexi),
                        description: d2.fullText || '',
                        applyUrl: 'https://www.justjob.co.in/jobseeker/vitw.aspx'
                    });
                }

                return positions;
            """)

            if positions:
                logger.info(f"Found {len(positions)} workmen hiring positions")
                for pos in positions:
                    title = pos.get('title', '').strip()
                    if not title:
                        continue
                    location = pos.get('location', 'Gurgaon / Manesar')
                    description = pos.get('description', '')
                    trades = pos.get('trades', '')
                    if trades:
                        description = f"Trades: {trades}\n\n{description}"
                    duration = pos.get('duration', '')
                    if duration:
                        description = f"Duration: {duration}\n{description}"

                    job_id = hashlib.md5(title.encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': description.strip()[:2000],
                        'location': location,
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': 'Apprentice' if 'Apprentice' in title else 'Contract',
                        'department': 'Manufacturing / ITI',
                        'apply_url': pos.get('applyUrl', WORKMEN_HIRING_URL),
                        'posted_date': '',
                        'job_function': 'Workmen Hiring (ITI)',
                        'experience_level': 'Entry Level / ITI',
                        'salary_range': pos.get('salary', ''),
                        'remote_type': 'On-site',
                        'status': 'active',
                    })
            else:
                logger.warning("No workmen hiring positions found on page")

        except Exception as e:
            logger.error(f"Error scraping workmen hiring: {str(e)}")

        return jobs

    # ------------------------------------------------------------------
    # Main careers page (/corporate/careers)
    # ------------------------------------------------------------------
    def _scrape_careers_page(self, driver):
        """Scrape hiring categories from the main careers page overlay cards."""
        jobs = []
        try:
            logger.info(f"Navigating to main careers page: {CAREERS_URL}")
            driver.get(CAREERS_URL)
            time.sleep(10)

            # Extract data from the overlay career windows (Freshers, Engineering
            # Hiring, Experienced Professionals, Workmen Hiring).
            # We skip "Workmen Hiring (ITI)" since we scrape it from its own page.
            categories = driver.execute_script("""
                var result = [];
                var overlays = document.querySelectorAll('.overlay.careerwindow');
                for (var i = 0; i < overlays.length; i++) {
                    var overlay = overlays[i];
                    var h2 = overlay.querySelector('h2');
                    var title = h2 ? h2.innerText.trim() : '';
                    if (!title) continue;

                    // Skip workmen hiring -- scraped separately
                    if (title.toLowerCase().includes('workmen')) continue;

                    // Collect overview text
                    var overview = '';
                    var overviewPanes = overlay.querySelectorAll('.tab-pane');
                    for (var j = 0; j < overviewPanes.length; j++) {
                        var pText = overviewPanes[j].innerText.trim();
                        if (pText.length > overview.length) overview = pText;
                    }
                    if (!overview) {
                        overview = overlay.innerText.trim();
                    }

                    // Collect apply links
                    var applyUrl = '';
                    var links = overlay.querySelectorAll('a[href]');
                    for (var k = 0; k < links.length; k++) {
                        var href = links[k].href || '';
                        var linkText = links[k].innerText.trim().toLowerCase();
                        if (linkText.includes('apply') && href && !href.endsWith('#')) {
                            applyUrl = href;
                            break;
                        }
                    }
                    if (!applyUrl) {
                        // Use first external link
                        for (var k = 0; k < links.length; k++) {
                            var href = links[k].href || '';
                            if (href && !href.includes('marutisuzuki.com') && !href.endsWith('#') && !href.includes('fraudulent')) {
                                applyUrl = href;
                                break;
                            }
                        }
                    }

                    result.push({
                        title: title,
                        overview: overview.substring(0, 2000),
                        applyUrl: applyUrl
                    });
                }
                return result;
            """)

            if categories:
                logger.info(f"Found {len(categories)} career categories on main page")
                for cat in categories:
                    title = cat.get('title', '').strip()
                    if not title:
                        continue

                    overview = cat.get('overview', '').strip()
                    apply_url = cat.get('applyUrl', '') or CAREERS_URL

                    # Determine employment type and department from the category
                    emp_type = ''
                    department = ''
                    exp_level = ''
                    if 'fresher' in title.lower():
                        emp_type = 'Full-time'
                        department = 'Campus Recruitment'
                        exp_level = 'Entry Level'
                    elif 'engineering' in title.lower():
                        emp_type = 'Full-time'
                        department = 'Engineering'
                        exp_level = 'Entry Level'
                    elif 'experienced' in title.lower():
                        emp_type = 'Full-time'
                        department = 'Various'
                        exp_level = 'Experienced'

                    job_id = hashlib.md5(title.encode()).hexdigest()[:12]

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': f"Hiring: {title}",
                        'description': overview[:2000],
                        'location': 'Gurgaon / Manesar / Multiple Locations',
                        'city': 'Gurgaon',
                        'state': 'Haryana',
                        'country': 'India',
                        'employment_type': emp_type,
                        'department': department,
                        'apply_url': apply_url,
                        'posted_date': '',
                        'job_function': title,
                        'experience_level': exp_level,
                        'salary_range': '',
                        'remote_type': 'On-site',
                        'status': 'active',
                    })
            else:
                logger.warning("No career categories found on main page")

        except Exception as e:
            logger.error(f"Error scraping careers page: {str(e)}")

        return jobs

    # ------------------------------------------------------------------
    # Param AI jobs page (external platform for professional roles)
    # ------------------------------------------------------------------
    def _scrape_param_ai(self, driver):
        """Scrape any active jobs from the Param AI platform."""
        jobs = []
        try:
            logger.info(f"Navigating to Param AI: {PARAM_AI_URL}")
            driver.get(PARAM_AI_URL)
            time.sleep(10)

            # Check if there are any job openings displayed
            job_data = driver.execute_script("""
                var result = [];
                var body = document.body.innerText.trim();

                // Check for "0 job openings" message
                if (body.includes('0 job opening') || body.includes('No jobs')) {
                    return result;
                }

                // Look for job cards/listings
                var cards = document.querySelectorAll(
                    '[class*="job-card"], [class*="job-listing"], [class*="opening"],' +
                    ' article, .card, [class*="position"]'
                );
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    var text = card.innerText.trim();
                    if (text.length < 10 || text.length > 1000) continue;
                    var title = text.split('\\n')[0].trim();
                    if (title.length < 3 || title.length > 200) continue;

                    var link = card.querySelector('a[href]');
                    var url = link ? link.href : '';
                    if (link && link.innerText.trim().length > 3) {
                        title = link.innerText.trim().split('\\n')[0];
                    }

                    var location = '';
                    var lines = text.split('\\n');
                    for (var j = 1; j < lines.length; j++) {
                        var line = lines[j].trim();
                        if (line.match(/Gurgaon|Gurugram|Delhi|Manesar|Mumbai|India|Pune|Chennai|Bangalore|Noida|Hyderabad/i)) {
                            location = line;
                            break;
                        }
                    }

                    result.push({title: title, url: url, location: location, fullText: text});
                }

                // Also try links with job-related patterns
                if (result.length === 0) {
                    document.querySelectorAll('a[href]').forEach(function(link) {
                        var text = (link.innerText || '').trim();
                        var href = link.href || '';
                        if (text.length < 3 || text.length > 200 || href.length < 10) return;
                        var lhref = href.toLowerCase();
                        if (lhref.includes('/job/') || lhref.includes('/jobs/') ||
                            lhref.includes('/opening') || lhref.includes('/apply')) {
                            if (!text.match(/^(home|about|contact|login|privacy|terms)$/i)) {
                                result.push({title: text.split('\\n')[0].trim(), url: href, location: '', fullText: text});
                            }
                        }
                    });
                }

                return result;
            """)

            if job_data:
                logger.info(f"Param AI found {len(job_data)} job listings")
                seen_titles = set()
                for item in job_data:
                    title = item.get('title', '').strip()
                    url = item.get('url', '').strip()
                    if not title or len(title) < 3 or title.lower() in seen_titles:
                        continue
                    seen_titles.add(title.lower())

                    location = item.get('location', '')
                    city, state, country = self.parse_location(location) if location else ('', '', 'India')
                    job_id = hashlib.md5((url or title).encode()).hexdigest()[:12]

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location or 'India',
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': 'Full-time',
                        'department': '',
                        'apply_url': url or PARAM_AI_URL,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active',
                    })
            else:
                logger.info("Param AI shows 0 job openings currently")

        except Exception as e:
            logger.error(f"Error scraping Param AI: {str(e)}")

        return jobs

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page (unused -- positions are on single pages)."""
        return False

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        # Handle common Maruti locations
        loc_lower = location_str.lower()
        if 'gurgaon' in loc_lower or 'gurugram' in loc_lower or 'manesar' in loc_lower:
            if not state:
                state = 'Haryana'
        elif 'delhi' in loc_lower:
            if not state:
                state = 'Delhi'

        return city, state, 'India'

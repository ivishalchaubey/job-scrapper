import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('ultratechcement_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class UltraTechCementScraper:
    def __init__(self):
        self.company_name = 'UltraTech Cement'
        self.url = 'https://abgcareers.peoplestrong.com/job/joblist'
        self.base_url = 'https://abgcareers.peoplestrong.com'

    def setup_driver(self):
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=AppleWebKit/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        try:
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"Primary driver setup failed: {str(e)}, trying fallback")
            driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

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

    def _is_ultratech_job(self, title, department, text=''):
        """Check if a job belongs to UltraTech Cement within ABG Careers."""
        combined = (title + ' ' + department + ' ' + text).lower()
        ultratech_keywords = ['ultratech', 'ultra tech', 'cement', 'building products', 'building solutions']
        return any(kw in combined for kw in ultratech_keywords)

    def _extract_location_from_text(self, full_text):
        """Extract location from the full text of a job card.

        PeopleStrong Angular components may not have standard class names for
        location elements. Instead, we parse the full text for known Indian cities.
        """
        if not full_text:
            return ''

        # Known Indian cities that ABG/UltraTech operates in
        india_cities = [
            'Mumbai', 'Delhi', 'New Delhi', 'Bangalore', 'Bengaluru',
            'Hyderabad', 'Chennai', 'Pune', 'Kolkata', 'Ahmedabad',
            'Jaipur', 'Lucknow', 'Surat', 'Nagpur', 'Indore',
            'Bhopal', 'Vadodara', 'Chandigarh', 'Coimbatore',
            'Gurgaon', 'Gurugram', 'Noida', 'Ghaziabad',
            'Raipur', 'Ranchi', 'Patna', 'Bhubaneswar',
            'Visakhapatnam', 'Vizag', 'Kochi', 'Thiruvananthapuram',
            'Mangalore', 'Mysore', 'Mysuru', 'Hubli',
            'Aurangabad', 'Nashik', 'Rajkot', 'Jodhpur',
            'Udaipur', 'Bikaner', 'Ajmer', 'Kota',
            'Jabalpur', 'Gwalior', 'Durg', 'Bhilai',
            'Cuttack', 'Sambalpur', 'Jharsuguda',
            'Navi Mumbai', 'Thane', 'Andheri',
            'Gulbarga', 'Bellary', 'Raichur',
            'Arakkonam', 'Reddipalayam', 'Dhar',
            'Tadipatri', 'Awarpur', 'Hirmi', 'Rawan',
            'Kotputli', 'Chirawa', 'Dalla', 'Aditya Nagar',
            'Jafrabad', 'Kovaya', 'Magdalla',
        ]

        # Search for city names in the text (case-insensitive)
        text_lower = full_text.lower()
        for city in india_cities:
            if city.lower() in text_lower:
                return f"{city}, India"

        # Try to find location patterns like "Location: CityName" or "City, State"
        loc_match = re.search(r'(?:location|place|city|site)\s*[:\-]\s*([A-Za-z\s]+?)(?:\n|,|\||\s{2,})', full_text, re.IGNORECASE)
        if loc_match:
            loc = loc_match.group(1).strip()
            if len(loc) > 2 and len(loc) < 50:
                return loc

        return ''

    def _extract_department_from_text(self, full_text):
        """Extract department from the full text of a job card.

        Look for common department/function names in the card text.
        """
        if not full_text:
            return ''

        # Common department names at UltraTech/ABG
        departments = [
            'Engineering', 'Finance', 'Human Resources', 'HR',
            'Information Technology', 'IT', 'Marketing', 'Sales',
            'Operations', 'Manufacturing', 'Production', 'Quality',
            'Supply Chain', 'Logistics', 'Procurement', 'Purchase',
            'Legal', 'Compliance', 'Administration', 'Admin',
            'Research', 'R&D', 'Projects', 'Maintenance',
            'Safety', 'EHS', 'Environment', 'HSE',
            'Commercial', 'Business Development', 'Strategy',
            'Accounts', 'Audit', 'Treasury', 'Taxation',
            'Plant', 'Mining', 'Mines', 'Mechanical',
            'Electrical', 'Instrumentation', 'Civil',
            'Technical', 'Process', 'Cement',
        ]

        # Try to find department-related patterns
        dept_match = re.search(r'(?:department|function|team|division|unit)\s*[:\-]\s*([A-Za-z\s&]+?)(?:\n|,|\||\s{2,})', full_text, re.IGNORECASE)
        if dept_match:
            dept = dept_match.group(1).strip()
            if len(dept) > 1 and len(dept) < 50:
                return dept

        # Look for department names in the text
        lines = full_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or len(line) > 60:
                continue
            for dept in departments:
                if dept.lower() == line.lower().strip():
                    return dept

        return ''

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape UltraTech Cement jobs from ABG Careers PeopleStrong page.

        ABG Careers at abgcareers.peoplestrong.com is an Angular SPA powered by
        PeopleStrong's ATS platform. The page renders job listings dynamically.

        Since this is a multi-company portal (Aditya Birla Group), we filter
        for UltraTech Cement jobs by checking the company/entity field or
        the full text of each job card for UltraTech keywords.

        The DOM structure uses Angular components without standard CSS class
        names for location/department, so we use multiple extraction strategies
        including parsing the full text content of each job entry.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            driver.get(self.url)
            time.sleep(12)

            # Scroll to load all content
            for i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # First, log the page structure to help debug
            try:
                page_info = driver.execute_script("""
                    var info = {};
                    info.title = document.title;
                    info.url = window.location.href;
                    info.bodyTextLength = document.body ? document.body.innerText.length : 0;

                    // Count elements with various selectors
                    var selectors = {
                        'a[href*="/job/"]': 'job links',
                        'a[href*="/job/detail"]': 'job detail links',
                        'div[class*="card"]': 'card divs',
                        'div[class*="job"]': 'job divs',
                        'mat-card': 'mat-cards',
                        'mat-list-item': 'mat-list-items',
                        'tr': 'table rows',
                        'li': 'list items',
                        '[class*="ng-"]': 'angular elements'
                    };
                    info.counts = {};
                    for (var sel in selectors) {
                        info.counts[selectors[sel]] = document.querySelectorAll(sel).length;
                    }

                    // Get first few links to understand structure
                    var jobLinks = document.querySelectorAll('a[href*="/job/"]');
                    info.sampleLinks = [];
                    for (var i = 0; i < Math.min(3, jobLinks.length); i++) {
                        var link = jobLinks[i];
                        var parent = link.closest('div, li, tr, mat-card, mat-list-item');
                        info.sampleLinks.push({
                            text: link.innerText.trim().substring(0, 100),
                            href: link.href,
                            parentTag: parent ? parent.tagName : 'none',
                            parentClass: parent ? parent.className.substring(0, 100) : 'none',
                            parentHTML: parent ? parent.outerHTML.substring(0, 500) : 'none',
                            parentText: parent ? parent.innerText.trim().substring(0, 300) : 'none',
                        });
                    }
                    return info;
                """)
                if page_info:
                    logger.info(f"Page: {page_info.get('title', '')} | URL: {page_info.get('url', '')}")
                    logger.info(f"Body text length: {page_info.get('bodyTextLength', 0)}")
                    counts = page_info.get('counts', {})
                    for name, count in counts.items():
                        if count > 0:
                            logger.info(f"  {name}: {count}")
                    for sample in page_info.get('sampleLinks', []):
                        logger.info(f"  Sample link: {sample.get('text', '')} -> {sample.get('href', '')}")
                        logger.info(f"    Parent: <{sample.get('parentTag', '')}> class='{sample.get('parentClass', '')}'")
                        logger.info(f"    Parent text: {sample.get('parentText', '')[:200]}")
            except Exception as e:
                logger.debug(f"Page info extraction failed: {e}")

            # Try to filter for UltraTech if search/filter UI is available
            try:
                search_input = driver.find_elements(By.CSS_SELECTOR,
                    'input[type="search"], input[type="text"][placeholder*="Search"], '
                    'input[placeholder*="search"], input[class*="search"]')
                if search_input:
                    search_input[0].clear()
                    search_input[0].send_keys('UltraTech')
                    time.sleep(3)
                    logger.info("Applied UltraTech search filter")
            except Exception:
                logger.info("Could not apply search filter, will filter results manually")

            # Try to load more jobs
            for _ in range(max_pages):
                try:
                    load_more = driver.find_elements(By.XPATH,
                        '//button[contains(text(),"Load More") or contains(text(),"Show More") '
                        'or contains(text(),"View More")]'
                        ' | //a[contains(text(),"Load More") or contains(text(),"Show More") '
                        'or contains(text(),"View More")]')
                    if load_more:
                        driver.execute_script("arguments[0].click();", load_more[0])
                        logger.info("Clicked 'Load More' button")
                        time.sleep(3)
                    else:
                        break
                except Exception:
                    break

            # Extract jobs using enhanced JavaScript - PeopleStrong SPA
            jobs = self._extract_jobs_js(driver)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs_js(self, driver):
        """Extract jobs from PeopleStrong page using enhanced JavaScript.

        PeopleStrong's Angular app uses non-standard DOM structure. The enhanced
        extraction tries multiple strategies and captures the full text content
        of each job's parent container to allow Python-side parsing of location
        and department information.
        """
        jobs = []

        try:
            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Helper: extract text from child elements with various attribute patterns
                function findFieldText(container, fieldNames) {
                    if (!container) return '';
                    for (var f = 0; f < fieldNames.length; f++) {
                        var name = fieldNames[f];
                        // Try class-based selectors
                        var el = container.querySelector('[class*="' + name + '"]');
                        if (el) return el.innerText.trim();
                        // Try data-attribute selectors
                        el = container.querySelector('[data-field="' + name + '"], [data-label="' + name + '"]');
                        if (el) return el.innerText.trim();
                        // Try aria-label
                        el = container.querySelector('[aria-label*="' + name + '"]');
                        if (el) return el.innerText.trim();
                    }
                    return '';
                }

                // Helper: try to find location/dept from text lines
                function parseTextLines(text) {
                    var result = {location: '', department: '', company: ''};
                    if (!text) return result;
                    var lines = text.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                    // Look for label: value patterns
                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i];
                        var lower = line.toLowerCase();
                        if (lower.match(/^(location|city|place|site)\s*[:\\-]/)) {
                            result.location = line.replace(/^[^:\\-]+[:\\-]\s*/, '').trim();
                        } else if (lower.match(/^(department|function|team|division|unit|category)\s*[:\\-]/)) {
                            result.department = line.replace(/^[^:\\-]+[:\\-]\s*/, '').trim();
                        } else if (lower.match(/^(company|entity|business|organization)\s*[:\\-]/)) {
                            result.company = line.replace(/^[^:\\-]+[:\\-]\s*/, '').trim();
                        }
                    }
                    return result;
                }

                // Strategy 1: PeopleStrong-specific selectors and Angular Material cards
                var cardSelectors = [
                    'mat-card', 'mat-list-item',
                    'div.job-card', 'div[class*="job-card"]', 'div[class*="jobCard"]',
                    'div[class*="job-list"]', 'div[class*="jobList"]',
                    'li[class*="job"]', 'div.card[class*="job"]',
                    'div[class*="position"]', 'div[class*="opening"]',
                    'div[class*="vacancy"]', 'div[class*="card"]',
                    'li[class*="card"]', 'app-job-card', 'app-job-list-item'
                ];

                for (var s = 0; s < cardSelectors.length; s++) {
                    var cards = document.querySelectorAll(cardSelectors[s]);
                    if (cards.length > 0) {
                        // Verify these cards contain job links
                        var validCards = [];
                        for (var i = 0; i < cards.length; i++) {
                            if (cards[i].querySelector('a[href*="/job/"]') ||
                                cards[i].querySelector('a[href*="jobdetail"]') ||
                                cards[i].querySelector('a[href*="job-detail"]')) {
                                validCards.push(cards[i]);
                            }
                        }
                        if (validCards.length === 0) continue;

                        for (var i = 0; i < validCards.length; i++) {
                            var card = validCards[i];
                            var title = '';
                            var href = '';

                            // Get title from heading or link
                            var heading = card.querySelector('h1, h2, h3, h4, h5, a[href*="/job/"]');
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
                                var jobLink = card.querySelector('a[href*="/job/"], a[href*="jobdetail"], a[href*="job-detail"]');
                                if (jobLink) href = jobLink.href;
                            }

                            // Get location using multiple approaches
                            var location = findFieldText(card, ['location', 'Location', 'city', 'City', 'place', 'Place', 'site', 'Site']);

                            // Get department using multiple approaches
                            var department = findFieldText(card, ['department', 'Department', 'function', 'Function', 'category', 'Category', 'team', 'Team', 'division', 'Division']);

                            // Get company/entity
                            var company = findFieldText(card, ['company', 'Company', 'entity', 'Entity', 'business', 'Business', 'organization', 'Organization']);

                            // Get full text for Python-side parsing
                            var fullText = card.innerText || '';

                            // Also try to find specific icon-based labels
                            // PeopleStrong often uses Material icons + text pattern
                            if (!location) {
                                var icons = card.querySelectorAll('mat-icon, i.material-icons, .mat-icon, i[class*="icon"]');
                                for (var ic = 0; ic < icons.length; ic++) {
                                    var iconText = (icons[ic].innerText || icons[ic].textContent || '').trim().toLowerCase();
                                    if (iconText === 'location_on' || iconText === 'place' || iconText === 'room') {
                                        var nextSib = icons[ic].nextElementSibling || icons[ic].parentElement;
                                        if (nextSib) {
                                            var sibText = nextSib.innerText.trim();
                                            if (sibText && sibText !== iconText && sibText.length < 100) {
                                                location = sibText;
                                                break;
                                            }
                                        }
                                    }
                                }
                            }

                            if (!department) {
                                var icons = card.querySelectorAll('mat-icon, i.material-icons, .mat-icon, i[class*="icon"]');
                                for (var ic = 0; ic < icons.length; ic++) {
                                    var iconText = (icons[ic].innerText || icons[ic].textContent || '').trim().toLowerCase();
                                    if (iconText === 'business' || iconText === 'work' || iconText === 'domain' || iconText === 'corporate_fare') {
                                        var nextSib = icons[ic].nextElementSibling || icons[ic].parentElement;
                                        if (nextSib) {
                                            var sibText = nextSib.innerText.trim();
                                            if (sibText && sibText !== iconText && sibText.length < 100) {
                                                department = sibText;
                                                break;
                                            }
                                        }
                                    }
                                }
                            }

                            // Parse text lines for label: value patterns
                            if (!location || !department) {
                                var parsed = parseTextLines(fullText);
                                if (!location && parsed.location) location = parsed.location;
                                if (!department && parsed.department) department = parsed.department;
                                if (!company && parsed.company) company = parsed.company;
                            }

                            if (title && title.length > 2 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({
                                    title: title, href: href,
                                    location: location, department: department,
                                    company: company, fullText: fullText.substring(0, 500)
                                });
                            }
                        }
                        if (results.length > 0) break;
                    }
                }

                // Strategy 2: Links with job-related hrefs - enhanced parent traversal
                if (results.length === 0) {
                    var links = document.querySelectorAll('a[href*="/job/"], a[href*="jobdetail"], a[href*="job-detail"]');
                    for (var i = 0; i < links.length; i++) {
                        var link = links[i];
                        var text = link.innerText.trim().split('\\n')[0].trim();
                        var href = link.href;
                        if (text.length > 3 && text.length < 200 && !seen[text + href]) {
                            // Skip navigation/menu links
                            if (href.includes('login') || href.includes('sign-in') || href.includes('javascript:')) continue;

                            seen[text + href] = true;
                            var loc = '';
                            var dept = '';
                            var comp = '';
                            var fullText = '';

                            // Walk up the DOM to find the containing card/list-item
                            var parent = link.closest('mat-card, mat-list-item, div[class*="card"], div[class*="job"], li, div[class*="row"], tr');
                            if (!parent) parent = link.parentElement;
                            // Go up a few more levels if parent is too small
                            if (parent && parent.innerText && parent.innerText.length < 50 && parent.parentElement) {
                                parent = parent.parentElement;
                            }
                            if (parent && parent.innerText && parent.innerText.length < 50 && parent.parentElement) {
                                parent = parent.parentElement;
                            }

                            if (parent) {
                                fullText = parent.innerText || '';

                                // Try class-based selectors
                                loc = findFieldText(parent, ['location', 'Location', 'city', 'City', 'place', 'Place']);
                                dept = findFieldText(parent, ['department', 'Department', 'function', 'Function', 'category', 'Category']);
                                comp = findFieldText(parent, ['company', 'Company', 'entity', 'Entity', 'business', 'Business']);

                                // Try Material icon patterns
                                if (!loc) {
                                    var icons = parent.querySelectorAll('mat-icon, i.material-icons, .mat-icon');
                                    for (var ic = 0; ic < icons.length; ic++) {
                                        var iconText = (icons[ic].innerText || '').trim().toLowerCase();
                                        if (iconText === 'location_on' || iconText === 'place' || iconText === 'room') {
                                            var next = icons[ic].nextElementSibling || icons[ic].parentElement;
                                            if (next) {
                                                var sibText = next.innerText.trim().split('\\n')[0].trim();
                                                if (sibText && sibText !== iconText && sibText.length > 2 && sibText.length < 100) {
                                                    loc = sibText;
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }

                                // Parse text lines
                                if (!loc || !dept) {
                                    var parsed = parseTextLines(fullText);
                                    if (!loc && parsed.location) loc = parsed.location;
                                    if (!dept && parsed.department) dept = parsed.department;
                                    if (!comp && parsed.company) comp = parsed.company;
                                }
                            }

                            results.push({
                                title: text, href: href,
                                location: loc, department: dept,
                                company: comp,
                                fullText: (fullText || '').substring(0, 500)
                            });
                        }
                    }
                }

                // Strategy 3: Table rows
                if (results.length === 0) {
                    var rows = document.querySelectorAll('table tr, div[role="row"]');
                    for (var i = 0; i < rows.length; i++) {
                        var row = rows[i];
                        var cells = row.querySelectorAll('td, div[role="cell"]');
                        if (cells.length >= 2) {
                            var titleCell = cells[0];
                            var link = titleCell.querySelector('a');
                            var title = titleCell.innerText.trim().split('\\n')[0].trim();
                            var href = link ? link.href : '';
                            var location = cells.length > 1 ? cells[1].innerText.trim() : '';
                            var dept = cells.length > 2 ? cells[2].innerText.trim() : '';
                            if (title.length > 3 && !seen[title + href]) {
                                seen[title + href] = true;
                                results.push({
                                    title: title, href: href,
                                    location: location, department: dept,
                                    company: '', fullText: row.innerText.substring(0, 500)
                                });
                            }
                        }
                    }
                }

                return results;
            """)

            if job_data:
                logger.info(f"JS extraction found {len(job_data)} jobs from ABG Careers")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '').strip()
                    href = jd.get('href', '').strip()
                    location = jd.get('location', '').strip()
                    department = jd.get('department', '').strip()
                    company = jd.get('company', '').strip()
                    full_text = jd.get('fullText', '').strip()

                    if not title or len(title) < 3:
                        continue

                    # Filter for UltraTech Cement jobs within ABG Careers
                    if company and not self._is_ultratech_job(company, '', ''):
                        if 'ultratech' not in company.lower() and 'cement' not in company.lower():
                            continue
                    # If no company field, include all jobs (ABG is parent of UltraTech)

                    # Try to extract location from full text if empty
                    if not location and full_text:
                        location = self._extract_location_from_text(full_text)
                    if not location:
                        location = 'India'

                    # Ensure India is in the location
                    if location and 'india' not in location.lower():
                        location = f"{location}, India"

                    # Try to extract department from full text if empty
                    if not department and full_text:
                        department = self._extract_department_from_text(full_text)

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
                        'country': 'India',
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
                    logger.info(f"Extracted: {title} | {location} | {department}")
            else:
                logger.warning("JS extraction returned no results")
                # Log page body preview for debugging
                try:
                    body_text = driver.execute_script(
                        'return document.body ? document.body.innerText.substring(0, 500) : ""')
                    logger.info(f"Page body preview: {body_text}")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"JS extraction failed: {e}")

        return jobs


if __name__ == "__main__":
    scraper = UltraTechCementScraper()
    jobs = scraper.scrape(max_pages=1)
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

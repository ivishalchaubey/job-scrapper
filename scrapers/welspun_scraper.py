from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
import re

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('welspun_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class WelspunScraper:
    def __init__(self):
        self.company_name = "Welspun"
        self.url = "https://welpro.welspun.com/careers?SiteName=jSIHd9FMCv/kd6koxIV5bVFzdqnRhv7lEcsAW5OEjUs="

    def setup_driver(self):
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        try:
            if os.path.exists(CHROMEDRIVER_PATH):
                service = Service(CHROMEDRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)
        except Exception:
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

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        driver = None
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)

            # Intercept XHR to capture Client-UTC header format before page loads
            driver.execute_script("""
                window.__capturedXHR = [];
                var origOpen = XMLHttpRequest.prototype.open;
                var origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
                var origSend = XMLHttpRequest.prototype.send;

                XMLHttpRequest.prototype.open = function(method, url) {
                    this._url = url;
                    this._method = method;
                    this._headers = {};
                    return origOpen.apply(this, arguments);
                };
                XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
                    this._headers[name] = value;
                    return origSetHeader.apply(this, arguments);
                };
                XMLHttpRequest.prototype.send = function(body) {
                    window.__capturedXHR.push({
                        url: this._url,
                        method: this._method,
                        headers: this._headers,
                        body: body
                    });
                    return origSend.apply(this, arguments);
                };

                // Also intercept fetch
                var origFetch = window.fetch;
                window.fetch = function(url, opts) {
                    window.__capturedXHR.push({
                        url: typeof url === 'string' ? url : url.url,
                        method: (opts && opts.method) || 'GET',
                        headers: (opts && opts.headers) || {},
                        body: (opts && opts.body) || null
                    });
                    return origFetch.apply(this, arguments);
                };
            """)

            # Now reload the page so the interceptor captures the initial API calls
            driver.get(self.url)

            # React SPA - wait for React to mount and render content inside <div id="root">
            try:
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script(
                        "var root = document.getElementById('root'); "
                        "return root && root.children.length > 0 && root.innerText.trim().length > 50;"
                    )
                )
                logger.info("React app has rendered content inside #root")
            except Exception as e:
                logger.warning(f"React render timeout: {str(e)}, using fallback wait")
                time.sleep(15)

            # Wait for the React app's API calls to complete
            time.sleep(10)

            # Check captured XHR for the Client-UTC format
            captured = driver.execute_script("return window.__capturedXHR || [];")
            if captured:
                for req in captured:
                    logger.info(f"Captured XHR: {req.get('method')} {req.get('url')} headers={req.get('headers')}")
            else:
                logger.info("No XHR requests captured")

            # Log what we see
            body_preview = driver.execute_script(
                "return document.body ? document.body.innerText.substring(0, 500) : ''"
            )
            logger.info(f"Page preview: {body_preview[:300]}")

            # Scroll to trigger lazy loading of job cards
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Extract jobs using JavaScript DOM analysis
            scraped_ids = set()
            jobs = self._extract_jobs(driver, scraped_ids)

            if not jobs:
                # Try using the Welspun API via the browser's JS context
                # The React app has the API client configured with proper auth headers
                logger.info("No jobs from DOM, attempting API extraction via browser context...")
                jobs = self._extract_via_browser_api(driver, scraped_ids)

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return jobs

    def _extract_via_browser_api(self, driver, scraped_ids):
        """Try to fetch jobs by intercepting the React app's API calls via browser JS."""
        jobs = []
        try:
            # Intercept and replay the API call using the React app's own axios/fetch
            # interceptor configuration (which adds proper Client-UTC header).
            # We inject an XHR interceptor to capture the request headers.
            api_data = driver.execute_script("""
                // Try to find the axios instance used by the React app
                // and use its interceptors to make a properly-authenticated request
                return new Promise(function(resolve) {
                    // Method 1: Intercept network requests by overriding XMLHttpRequest
                    var capturedHeaders = {};
                    var OrigXHR = XMLHttpRequest;
                    var tempXHR = new OrigXHR();

                    // Method 2: Try to trigger the app to load jobs by simulating
                    // a search/filter action, then read the DOM after
                    var searchBtns = document.querySelectorAll('button, input[type="submit"]');
                    for (var i = 0; i < searchBtns.length; i++) {
                        var txt = (searchBtns[i].innerText || searchBtns[i].value || '').toLowerCase().trim();
                        if (txt.indexOf('search') >= 0 || txt.indexOf('find') >= 0 ||
                            txt.indexOf('view') >= 0 || txt.indexOf('show') >= 0) {
                            searchBtns[i].click();
                            break;
                        }
                    }

                    // Wait for potential AJAX response
                    setTimeout(function() {
                        // Now try to read job data from the updated DOM
                        var bodyText = document.body.innerText || '';
                        resolve({domText: bodyText.substring(0, 5000)});
                    }, 5000);
                });
            """)

            if api_data and isinstance(api_data, dict):
                dom_text = api_data.get('domText', '')
                if dom_text:
                    logger.info(f"Post-search DOM preview: {dom_text[:300]}")
                    # Parse job titles from the text
                    lines = [l.strip() for l in dom_text.split('\n') if l.strip()]
                    for i, line in enumerate(lines):
                        if len(line) < 5 or len(line) > 150:
                            continue
                        if re.search(r'manager|engineer|analyst|developer|architect|lead|senior|junior|associate|director|consultant|specialist|designer|coordinator|executive|officer|intern|trainee|supervisor|assistant|technician|operator', line, re.IGNORECASE):
                            # Check next lines for location
                            loc = ''
                            for j in range(i + 1, min(i + 4, len(lines))):
                                if re.search(r'Mumbai|Pune|Anjar|Vapi|Bangalore|Delhi|Kutch|Gujarat|Hyderabad|India|Chennai|Silvassa|Dahej|Surat', lines[j], re.IGNORECASE):
                                    loc = lines[j]
                                    break
                            job_id = hashlib.md5(line.encode()).hexdigest()[:12]
                            ext_id = self.generate_external_id(job_id, self.company_name)
                            if ext_id not in scraped_ids:
                                scraped_ids.add(ext_id)
                                city, state, country = self.parse_location(loc)
                                jobs.append({
                                    'external_id': ext_id,
                                    'company_name': self.company_name,
                                    'title': line,
                                    'description': '',
                                    'location': loc if loc else 'India',
                                    'city': city,
                                    'state': state,
                                    'country': 'India',
                                    'employment_type': '',
                                    'department': '',
                                    'apply_url': self.url,
                                    'posted_date': '',
                                    'job_function': '',
                                    'experience_level': '',
                                    'salary_range': '',
                                    'remote_type': '',
                                    'status': 'active'
                                })
                    logger.info(f"Post-search text extraction found {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"Browser API extraction failed: {str(e)}")

        return jobs

    def _parse_api_job(self, item, scraped_ids):
        """Parse a job from the API response."""
        if not isinstance(item, dict):
            return None

        title = ''
        for key in ['jobTitle', 'title', 'designation', 'positionTitle', 'mrfTitle', 'name']:
            val = item.get(key, '')
            if val and isinstance(val, str) and len(val.strip()) > 2:
                title = val.strip()
                break

        if not title:
            return None

        job_id = str(item.get('id', '') or item.get('mrfId', '') or item.get('jobId', '') or '')
        if not job_id:
            job_id = hashlib.md5(title.encode()).hexdigest()[:12]

        ext_id = self.generate_external_id(job_id, self.company_name)
        if ext_id in scraped_ids:
            return None
        scraped_ids.add(ext_id)

        location = ''
        for key in ['location', 'city', 'locationName', 'workLocation']:
            val = item.get(key, '')
            if val and isinstance(val, str):
                location = val.strip()
                break

        department = ''
        for key in ['department', 'dept', 'function', 'businessUnit']:
            val = item.get(key, '')
            if val and isinstance(val, str):
                department = val.strip()
                break

        employment_type = ''
        for key in ['employmentType', 'type', 'jobType']:
            val = item.get(key, '')
            if val and isinstance(val, str):
                employment_type = val.strip()
                break

        experience = ''
        for key in ['experience', 'experienceRange', 'minExperience']:
            val = item.get(key, '')
            if val:
                experience = str(val).strip()
                break

        city, state, country = self.parse_location(location)

        return {
            'external_id': ext_id,
            'company_name': self.company_name,
            'title': title,
            'description': '',
            'location': location if location else 'India',
            'city': city,
            'state': state,
            'country': 'India',
            'employment_type': employment_type,
            'department': department,
            'apply_url': self.url,
            'posted_date': '',
            'job_function': department,
            'experience_level': experience,
            'salary_range': '',
            'remote_type': '',
            'status': 'active'
        }

    def _extract_jobs(self, driver, scraped_ids):
        """Extract job listings from Welspun React SPA DOM."""
        jobs = []
        try:
            js_jobs = driver.execute_script("""
                var results = [];
                var seen = {};

                // Welspun React SPA renders job cards with structured fields like:
                //   Company Name
                //   Designation: <title>
                //   Physical Location: <location>
                //   Business: <business>
                //   Department: <department>

                var bodyText = document.body.innerText || '';
                var allLines = bodyText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                // Strategy 1: Look for "Designation:" patterns - the Welspun SPA
                // renders job data with labeled fields
                for (var i = 0; i < allLines.length; i++) {
                    var line = allLines[i];

                    // Check for "Designation: <title>" pattern
                    var desigMatch = line.match(/^Designation\\s*:\\s*(.+)/i);
                    if (desigMatch) {
                        var title = desigMatch[1].trim();
                        if (title.length < 3 || title.length > 200) continue;
                        if (seen[title + '_' + i]) continue;
                        seen[title + '_' + i] = true;

                        // Look at surrounding lines for other fields
                        var location = '';
                        var department = '';
                        var business = '';
                        var company = '';
                        var experience = '';

                        // Search nearby lines (before and after) for related fields
                        var searchStart = Math.max(0, i - 5);
                        var searchEnd = Math.min(allLines.length, i + 8);
                        for (var j = searchStart; j < searchEnd; j++) {
                            if (j === i) continue;
                            var nearby = allLines[j];
                            var locMatch = nearby.match(/^Physical Location\\s*:\\s*(.+)/i) ||
                                           nearby.match(/^Location\\s*:\\s*(.+)/i);
                            if (locMatch && !location) {
                                location = locMatch[1].trim();
                                continue;
                            }
                            var deptMatch = nearby.match(/^Department\\s*:\\s*(.+)/i);
                            if (deptMatch && !department) {
                                department = deptMatch[1].trim();
                                continue;
                            }
                            var bizMatch = nearby.match(/^Business\\s*:\\s*(.+)/i);
                            if (bizMatch && !business) {
                                business = bizMatch[1].trim();
                                continue;
                            }
                            var compMatch = nearby.match(/^Company Name\\s*:\\s*(.+)/i);
                            if (!compMatch) {
                                // Company name might be on its own line before Designation
                                // (it appears as the first line of a card)
                            }
                            var expMatch = nearby.match(/^Experience\\s*:\\s*(.+)/i);
                            if (expMatch && !experience) {
                                experience = expMatch[1].trim();
                                continue;
                            }
                        }

                        results.push({
                            title: title,
                            url: '',
                            location: location,
                            department: department || business,
                            experience: experience,
                            employment_type: ''
                        });
                        continue;
                    }
                }

                // Strategy 2: Fallback - look for role-keyword lines if no Designation pattern found
                if (results.length === 0) {
                    for (var i = 0; i < allLines.length; i++) {
                        var line = allLines[i];
                        if (line.length < 5 || line.length > 150) continue;

                        // Skip navigation/boilerplate
                        var lower = line.toLowerCase();
                        if (/^(home|career|search|filter|apply|login|copyright|scroll|business|company|location|date)$/i.test(lower)) continue;
                        if (/current opportunities|filter jobs|all rights/i.test(lower)) continue;

                        // Check if line looks like a job title
                        if (/manager|engineer|analyst|developer|architect|lead|senior|junior|associate|director|consultant|specialist|designer|coordinator|executive|officer|intern|trainee|supervisor|assistant|technician|operator/i.test(line)) {
                            // Make sure it's not a label like "Designation: Manager"
                            if (/^(designation|department|business|location|company)/i.test(line)) continue;
                            if (seen[line]) continue;
                            seen[line] = true;

                            var loc = '';
                            for (var j = i + 1; j < Math.min(i + 5, allLines.length); j++) {
                                if (/Mumbai|Pune|Anjar|Vapi|Bangalore|Delhi|Kutch|Gujarat|Hyderabad|India|Chennai|Silvassa|Dahej|Surat/i.test(allLines[j])) {
                                    loc = allLines[j].replace(/^Physical Location\\s*:\\s*/i, '').trim();
                                    break;
                                }
                            }

                            results.push({
                                title: line,
                                url: '',
                                location: loc,
                                department: '',
                                experience: '',
                                employment_type: ''
                            });
                        }
                    }
                }

                return results;
            """)

            if js_jobs:
                logger.info(f"Extraction found {len(js_jobs)} jobs")
                seen_urls = set()
                for idx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()
                    experience = jdata.get('experience', '').strip()
                    employment_type = jdata.get('employment_type', '').strip()

                    if not title or len(title) < 3:
                        continue
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    job_id = f"welspun_{idx}"
                    if url:
                        id_match = re.search(r'(?:job|position|opening|id)[=/](\w+)', url, re.IGNORECASE)
                        if id_match:
                            job_id = id_match.group(1)
                        else:
                            job_id = hashlib.md5(url.encode()).hexdigest()[:12]

                    ext_id = self.generate_external_id(job_id, self.company_name)
                    if ext_id in scraped_ids:
                        continue
                    scraped_ids.add(ext_id)

                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': ext_id,
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location if location else 'India',
                        'city': city,
                        'state': state,
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': url if url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found via DOM extraction")

        except Exception as e:
            logger.error(f"Extraction error: {str(e)}")

        return jobs


if __name__ == "__main__":
    scraper = WelspunScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['department']}")

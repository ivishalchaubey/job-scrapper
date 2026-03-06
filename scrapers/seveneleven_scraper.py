from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('seveneleven_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class SevenElevenScraper:
    def __init__(self):
        self.company_name = '7-Eleven GSC'
        self.url = 'https://7-eleven-gsc.ripplehire.com/candidate/?token=AdexT4WYTKbaWH7lieeK'

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
        """Scrape jobs from 7-Eleven GSC (RippleHire RequireJS SPA)."""
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            driver.get(self.url)

            # RippleHire uses RequireJS to load a Backbone/jQuery SPA.
            # The token URL may land on a single-job detail page.
            # We need to navigate to the "View all roles" listing page.
            logger.info("Waiting for RippleHire SPA to render...")

            # Wait for the body to have substantial content
            try:
                WebDriverWait(driver, 30).until(
                    lambda d: len(d.execute_script(
                        "return document.body ? document.body.innerText : ''"
                    )) > 200
                )
                logger.info("Page has loaded content")
            except Exception:
                logger.warning("Timeout waiting for page content, proceeding")

            # Wait for AJAX data to populate
            time.sleep(10)

            # Check if we're on a single-job detail page.
            # RippleHire token URLs often show one job with a "View all N role(s)" link.
            # Try to click that link to go to the full listing.
            try:
                view_all_clicked = driver.execute_script("""
                    var links = document.querySelectorAll('a, button, span');
                    for (var i = 0; i < links.length; i++) {
                        var text = (links[i].innerText || '').trim().toLowerCase();
                        if (text.match(/view all \\d+ role|view all roles|all openings|all jobs|browse all/)) {
                            links[i].click();
                            return true;
                        }
                    }
                    return false;
                """)
                if view_all_clicked:
                    logger.info("Clicked 'View all roles' link to navigate to job listing")
                    time.sleep(8)
                else:
                    logger.info("No 'View all roles' link found, staying on current page")
            except Exception as e:
                logger.warning(f"Could not click view all: {str(e)}")

            # Scroll extensively to trigger lazy loading of all job cards.
            # RippleHire loads jobs in batches as the user scrolls.
            prev_height = 0
            for scroll_round in range(20):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == prev_height:
                    # Try clicking "Load More" / "Show More" buttons
                    try:
                        load_more = driver.find_elements(By.XPATH,
                            '//button[contains(text(),"Load More") or contains(text(),"Show More")]'
                            ' | //a[contains(text(),"Load More") or contains(text(),"Show More")]'
                            ' | //span[contains(text(),"Load More") or contains(text(),"Show More")]/..')
                        if load_more:
                            driver.execute_script("arguments[0].click();", load_more[0])
                            logger.info("Clicked load more button")
                            time.sleep(3)
                            continue
                    except Exception:
                        pass
                    break
                prev_height = new_height
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Extract jobs using multiple strategies
            jobs = self._extract_jobs_js(driver)

            logger.info(f"Successfully scraped {len(jobs)} jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")

        finally:
            if driver:
                driver.quit()

        return jobs

    def _extract_jobs_js(self, driver):
        """Extract jobs from RippleHire SPA using JavaScript DOM inspection."""
        jobs = []

        # Skip patterns that indicate branding/navigation, not job titles
        skip_patterns = [
            'powered by', 'ripplehire', 'copyright', 'all rights reserved',
            'home', 'about', 'contact', 'login', 'sign up', 'register',
            'privacy', 'terms', 'apply now', 'refer', 'share', 'cookie',
            'follow us', 'connect with', 'social media', 'view all',
            'view more', 'careers at', 'openings', 'opening',
            'years', 'year', 'experience', 'minimum', 'knowledge of',
            'responsibilities', 'role description', 'qualification',
        ]

        try:
            # First, log what's on the page for debugging
            body_text = driver.execute_script(
                "return document.body ? document.body.innerText.substring(0, 1000) : ''"
            )
            logger.info(f"Page content preview: {body_text[:300]}")

            job_data = driver.execute_script("""
                var results = [];
                var seen = {};

                // Helper to check if text is a likely job title
                function isJobTitle(text) {
                    if (!text || text.length < 5 || text.length > 200) return false;
                    var lower = text.toLowerCase();
                    var skipWords = ['powered by', 'ripplehire', 'copyright', 'all rights reserved',
                        'home', 'about us', 'contact us', 'login', 'sign up', 'register',
                        'privacy policy', 'terms', 'apply now', 'refer a friend', 'share',
                        'cookie', 'follow us', 'connect with', 'social media', 'loading',
                        'please wait', 'search', 'filter', 'sort by', 'no openings',
                        'view details', 'read more', 'learn more', 'click here',
                        'back to', 'go to', 'menu', 'close', 'open', 'toggle',
                        'powered by ripplehire', 'candidate portal'];
                    for (var i = 0; i < skipWords.length; i++) {
                        if (lower === skipWords[i] || lower.indexOf(skipWords[i]) === 0) return false;
                    }
                    // Should not be just numbers/symbols
                    if (!/[a-zA-Z]{3,}/.test(text)) return false;
                    return true;
                }

                // Strategy 1: Look for elements with job-related classes/IDs
                var jobSelectors = [
                    '[class*="job-title"], [class*="jobTitle"], [class*="job_title"]',
                    '[class*="opening-title"], [class*="openingTitle"]',
                    '[class*="position-title"], [class*="positionTitle"]',
                    '[class*="vacancy-title"], [class*="vacancyTitle"]',
                    '[class*="designation"]',
                    '[id*="jobTitle"], [id*="job-title"]'
                ];

                for (var s = 0; s < jobSelectors.length; s++) {
                    try {
                        var titleEls = document.querySelectorAll(jobSelectors[s]);
                        for (var i = 0; i < titleEls.length; i++) {
                            var el = titleEls[i];
                            var title = el.innerText.trim().split('\\n')[0].trim();
                            if (!isJobTitle(title)) continue;
                            if (seen[title]) continue;
                            seen[title] = true;

                            // Look for sibling/parent elements with location, experience, etc.
                            var container = el.closest('div, li, tr, article, section') || el.parentElement;
                            var containerText = container ? container.innerText : '';
                            var link = container ? container.querySelector('a[href]') : null;
                            var href = link ? link.href : '';

                            var location = '';
                            var experience = '';
                            if (container) {
                                var locEl = container.querySelector('[class*="location"], [class*="Location"], [class*="city"], [class*="place"]');
                                if (locEl) location = locEl.innerText.trim();
                                var expEl = container.querySelector('[class*="experience"], [class*="Experience"], [class*="exp"]');
                                if (expEl) experience = expEl.innerText.trim();
                            }

                            // Fallback: check text for Indian cities
                            if (!location) {
                                var cities = ['Bengaluru', 'Bangalore', 'Mumbai', 'Delhi', 'Hyderabad', 'Chennai', 'Pune', 'Kolkata', 'Gurgaon', 'Gurugram', 'Noida', 'Ahmedabad'];
                                for (var c = 0; c < cities.length; c++) {
                                    if (containerText.indexOf(cities[c]) >= 0) {
                                        location = cities[c];
                                        break;
                                    }
                                }
                            }

                            results.push({title: title, href: href, location: location, experience: experience, department: ''});
                        }
                        if (results.length > 0) break;
                    } catch(e) {}
                }

                // Strategy 2: Look for repeating card/list structures with links
                if (results.length === 0) {
                    var cardSelectors = [
                        '[class*="job-card"], [class*="jobCard"], [class*="job_card"]',
                        '[class*="opening-card"], [class*="openingCard"]',
                        '[class*="job-row"], [class*="jobRow"]',
                        '[class*="job-list"] > div, [class*="job-list"] > li',
                        '[class*="opening-list"] > div, [class*="opening-list"] > li',
                        '[class*="vacancy-list"] > div, [class*="vacancy-list"] > li',
                        '.card, .list-item, .list-group-item'
                    ];

                    for (var s = 0; s < cardSelectors.length; s++) {
                        try {
                            var cards = document.querySelectorAll(cardSelectors[s]);
                            if (cards.length === 0) continue;

                            for (var i = 0; i < cards.length; i++) {
                                var card = cards[i];
                                var text = (card.innerText || '').trim();
                                if (text.length < 5 || text.length > 500) continue;

                                var title = '';
                                var heading = card.querySelector('h1, h2, h3, h4, h5, [class*="title"], [class*="Title"]');
                                if (heading) {
                                    title = heading.innerText.trim().split('\\n')[0].trim();
                                }
                                if (!title) {
                                    // Take the first line of the card as title
                                    title = text.split('\\n')[0].trim();
                                }
                                if (!isJobTitle(title)) continue;
                                if (seen[title]) continue;
                                seen[title] = true;

                                var link = card.querySelector('a[href]');
                                var href = link ? link.href : '';

                                var location = '';
                                var locEl = card.querySelector('[class*="location"], [class*="Location"]');
                                if (locEl) location = locEl.innerText.trim();

                                results.push({title: title, href: href, location: location, experience: '', department: ''});
                            }
                            if (results.length > 0) break;
                        } catch(e) {}
                    }
                }

                // Strategy 3: Parse the page text for job-like patterns
                // RippleHire often renders jobs in a simple text format
                if (results.length === 0) {
                    var body = document.body.innerText || '';
                    var lines = body.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                    // Look for patterns: job title lines followed by location lines
                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i];
                        if (!isJobTitle(line)) continue;
                        // Check if next lines contain location info
                        var nextLines = lines.slice(i + 1, i + 5).join(' ');
                        var location = '';
                        var cities = ['Bengaluru', 'Bangalore', 'Mumbai', 'Delhi', 'Hyderabad', 'Chennai', 'Pune', 'Kolkata', 'Gurgaon', 'Gurugram', 'Noida'];
                        for (var c = 0; c < cities.length; c++) {
                            if (nextLines.indexOf(cities[c]) >= 0) {
                                location = cities[c];
                                break;
                            }
                        }

                        // Only include if it looks like a real job title (has role-related words)
                        var hasJobWord = /engineer|manager|analyst|developer|architect|lead|senior|junior|associate|director|consultant|specialist|designer|coordinator|executive|officer|intern|trainee|head|vp|president/i.test(line);
                        if (!hasJobWord && !location) continue;

                        if (!seen[line]) {
                            seen[line] = true;
                            results.push({title: line, href: '', location: location, experience: '', department: ''});
                        }
                    }
                }

                // Strategy 4: Find all links that look like job detail pages
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    for (var i = 0; i < allLinks.length; i++) {
                        var a = allLinks[i];
                        var href = a.href || '';
                        var text = (a.innerText || '').trim().split('\\n')[0].trim();
                        // Skip branding/nav links
                        if (!isJobTitle(text)) continue;
                        // Should point to a job or detail page
                        if (href.indexOf('job') >= 0 || href.indexOf('opening') >= 0 ||
                            href.indexOf('detail') >= 0 || href.indexOf('apply') >= 0 ||
                            href.indexOf('position') >= 0) {
                            if (!seen[text + href]) {
                                seen[text + href] = true;
                                results.push({title: text, href: href, location: '', experience: '', department: ''});
                            }
                        }
                    }
                }

                return results;
            """)

            if job_data:
                logger.info(f"JS extraction found {len(job_data)} candidate jobs")
                for idx, jd in enumerate(job_data):
                    title = jd.get('title', '').strip()
                    href = jd.get('href', '').strip()
                    location = jd.get('location', '').strip()
                    experience = jd.get('experience', '').strip()

                    if not title or len(title) < 3:
                        continue

                    # Final skip filter
                    title_lower = title.lower()
                    if any(sw in title_lower for sw in skip_patterns):
                        continue

                    if href and href.startswith('/'):
                        href = f"https://7-eleven-gsc.ripplehire.com{href}"

                    job_id = hashlib.md5((href or f"{title}_{idx}").encode()).hexdigest()[:12]
                    city, state, country = self.parse_location(location)

                    jobs.append({
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': '',
                        'location': location if location else 'India',
                        'city': city,
                        'state': state,
                        'country': country,
                        'employment_type': '',
                        'department': '',
                        'apply_url': href if href else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': experience,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No jobs found via JS extraction")

        except Exception as e:
            logger.error(f"JS extraction failed: {e}")

        return jobs


if __name__ == "__main__":
    scraper = SevenElevenScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']} | {job['experience_level']}")

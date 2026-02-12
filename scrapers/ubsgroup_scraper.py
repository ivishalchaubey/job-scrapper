from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import os
from pathlib import Path

from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('ubsgroup_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'


class UBSGroupScraper:
    def __init__(self):
        self.company_name = 'UBS Group'
        self.url = 'https://jobs.ubs.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid=25008&siteid=5012&PageType=searchResults&SearchType=linkquery&LinkID=6017#keyWordSearch=&locationSearch=India'

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

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'})
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        driver = None
        all_jobs = []

        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")

            driver.get(self.url)

            # Wait 15s for Taleo NG to render
            time.sleep(15)

            logger.info(f"Current URL after load: {driver.current_url}")

            # Scroll to trigger lazy loading
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Try pagination - scrape multiple pages
            page = 1
            scraped_ids = set()

            while page <= max_pages:
                logger.info(f"Scraping page {page}")
                jobs = self._scrape_page(driver, scraped_ids)
                if jobs:
                    all_jobs.extend(jobs)
                    for j in jobs:
                        scraped_ids.add(j['external_id'])
                    logger.info(f"Page {page}: found {len(jobs)} jobs, total so far: {len(all_jobs)}")
                else:
                    logger.info(f"Page {page}: no new jobs found, stopping pagination")
                    break

                # Try to click next page
                if not self._go_to_next_page(driver):
                    break
                page += 1
                time.sleep(5)

            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs

        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")

    def _go_to_next_page(self, driver):
        """Try to navigate to the next page in Taleo NG"""
        try:
            # Taleo NG pagination selectors
            next_selectors = [
                "a[aria-label='Next']",
                "a.next",
                "button.next",
                "a[title='Next']",
                "[class*='next']",
                "[class*='pager'] a:last-child",
                "a[id*='next']",
                "span[id*='next'] a",
                "div[class*='pagination'] a:last-child",
                "a[class*='paginate_button_next']",
                "li.next a",
            ]

            for selector in next_selectors:
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if next_btn.is_displayed() and next_btn.is_enabled():
                        next_btn.click()
                        time.sleep(5)
                        return True
                except:
                    continue

            # Try JavaScript click on next button
            clicked = driver.execute_script("""
                // Look for Taleo NG next button patterns
                var buttons = document.querySelectorAll('a, button, span, div, input');
                for (var i = 0; i < buttons.length; i++) {
                    var text = (buttons[i].innerText || buttons[i].value || '').trim().toLowerCase();
                    var title = (buttons[i].getAttribute('title') || '').toLowerCase();
                    var ariaLabel = (buttons[i].getAttribute('aria-label') || '').toLowerCase();
                    var cls = (buttons[i].className || '').toLowerCase();
                    if (text === 'next' || text === '>' || text === '>>' ||
                        title === 'next' || title === 'next page' ||
                        ariaLabel === 'next' || ariaLabel === 'next page' ||
                        cls.indexOf('next') !== -1) {
                        buttons[i].click();
                        return true;
                    }
                }
                return false;
            """)
            if clicked:
                time.sleep(5)
                return True

            return False
        except Exception as e:
            logger.error(f"Pagination error: {str(e)}")
            return False

    def _scrape_page(self, driver, scraped_ids=None):
        jobs = []
        if scraped_ids is None:
            scraped_ids = set()

        try:
            # --- Strategy 1: JS extraction for Taleo NG (TGnewUI) ---
            logger.info("Trying JS-based Taleo NG extraction")
            js_jobs = driver.execute_script("""
                var results = [];

                // Strategy A: Taleo NG accordion rows - each job is in a row/card
                var accordionRows = document.querySelectorAll(
                    'div.oracletaleaborot-accordion-row, ' +
                    'div[class*="accordion-row"], ' +
                    'div[class*="requisition"], ' +
                    'div[class*="searchResultItem"], ' +
                    'div[class*="SearchResultItem"], ' +
                    'div[class*="search-result"], ' +
                    'div[class*="jobItem"], ' +
                    'div[class*="job-item"], ' +
                    'li[class*="job"], ' +
                    'tr[class*="data"]'
                );

                if (accordionRows.length > 0) {
                    for (var i = 0; i < accordionRows.length; i++) {
                        var row = accordionRows[i];
                        var text = (row.innerText || '').trim();
                        if (text.length < 5) continue;

                        var lines = text.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        if (lines.length === 0) continue;

                        var title = '';
                        var location = '';
                        var department = '';
                        var url = '';

                        // Try to find title link
                        var titleLink = row.querySelector(
                            'span.titlelink a, a.jobTitle-link, a[href*="requisition"], ' +
                            'a[class*="title"], span[class*="title"] a, ' +
                            'a[href*="Requisition"], h2 a, h3 a, a'
                        );
                        if (titleLink) {
                            title = (titleLink.innerText || '').trim();
                            url = titleLink.href || '';
                        }

                        if (!title) {
                            // Look for span.titlelink
                            var titleSpan = row.querySelector('span.titlelink, span[class*="title"], span[class*="Title"]');
                            if (titleSpan) {
                                title = (titleSpan.innerText || '').trim();
                                var innerLink = titleSpan.querySelector('a');
                                if (innerLink) url = innerLink.href || '';
                            }
                        }

                        if (!title) {
                            title = lines[0];
                        }

                        // Skip navigation/header items
                        var skipWords = ['search', 'filter', 'sort', 'showing', 'results', 'page', 'next', 'previous', 'refine'];
                        var lowerTitle = title.toLowerCase();
                        var isSkip = false;
                        for (var s = 0; s < skipWords.length; s++) {
                            if (lowerTitle === skipWords[s]) { isSkip = true; break; }
                        }
                        if (isSkip) continue;
                        if (title.length < 3 || title.length > 200) continue;

                        // Extract location - Taleo often has it in a specific column/span
                        var locEl = row.querySelector(
                            'td.colLocation, span[class*="location"], ' +
                            'div[class*="location"], span[class*="Location"], ' +
                            'td:nth-child(2), span[id*="location"]'
                        );
                        if (locEl) {
                            location = (locEl.innerText || '').trim();
                        }
                        if (!location) {
                            for (var j = 1; j < lines.length; j++) {
                                if (/mumbai|delhi|bangalore|bengaluru|pune|hyderabad|chennai|kolkata|india|noida|gurgaon|gurugram|remote/i.test(lines[j])) {
                                    location = lines[j];
                                    break;
                                }
                            }
                        }

                        // Extract department
                        var deptEl = row.querySelector(
                            'td.colDepartment, span[class*="department"], ' +
                            'div[class*="department"], span[class*="Department"]'
                        );
                        if (deptEl) {
                            department = (deptEl.innerText || '').trim();
                        }

                        results.push({title: title, url: url, location: location, department: department});
                    }
                }

                // Strategy B: Table rows (Taleo classic layout)
                if (results.length === 0) {
                    var tableRows = document.querySelectorAll('table tr.dataRow, table tr.data-row, table tbody tr');
                    for (var r = 0; r < tableRows.length; r++) {
                        var tr = tableRows[r];
                        var cells = tr.querySelectorAll('td');
                        if (cells.length < 1) continue;

                        var rowTitle = '';
                        var rowUrl = '';
                        var rowLocation = '';
                        var rowDept = '';

                        // First cell usually contains the title
                        var firstLink = cells[0].querySelector('a, span.titlelink a');
                        if (firstLink) {
                            rowTitle = (firstLink.innerText || '').trim();
                            rowUrl = firstLink.href || '';
                        } else {
                            rowTitle = (cells[0].innerText || '').trim();
                        }

                        // Location is often in second or third cell
                        if (cells.length >= 2) {
                            rowLocation = (cells[1].innerText || '').trim();
                        }
                        if (cells.length >= 3) {
                            rowDept = (cells[2].innerText || '').trim();
                        }

                        if (rowTitle && rowTitle.length >= 3 && rowTitle.length <= 200) {
                            results.push({title: rowTitle, url: rowUrl, location: rowLocation, department: rowDept});
                        }
                    }
                }

                // Strategy C: Generic div-based card layout
                if (results.length === 0) {
                    var cards = document.querySelectorAll(
                        'div[class*="job"], div[class*="card"], div[class*="listing"], ' +
                        'div[class*="position"], div[class*="result"]'
                    );
                    var seenC = new Set();
                    for (var c = 0; c < cards.length; c++) {
                        var card = cards[c];
                        var cText = (card.innerText || '').trim();
                        if (cText.length < 5) continue;

                        var cLines = cText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
                        if (cLines.length === 0) continue;

                        var cTitle = '';
                        var cLink = card.querySelector('a[href]');
                        if (cLink) {
                            cTitle = (cLink.innerText || '').trim().split('\\n')[0];
                        }
                        if (!cTitle) cTitle = cLines[0];
                        if (seenC.has(cTitle) || cTitle.length < 3) continue;
                        seenC.add(cTitle);

                        var cUrl = cLink ? (cLink.href || '') : '';
                        var cLoc = '';
                        for (var cl = 1; cl < cLines.length; cl++) {
                            if (/mumbai|delhi|bangalore|bengaluru|pune|hyderabad|chennai|kolkata|india|noida|gurgaon|gurugram|remote/i.test(cLines[cl])) {
                                cLoc = cLines[cl];
                                break;
                            }
                        }

                        results.push({title: cTitle, url: cUrl, location: cLoc, department: ''});
                    }
                }

                // Strategy D: All links fallback
                if (results.length === 0) {
                    var allLinks = document.querySelectorAll('a[href]');
                    var seenL = new Set();
                    for (var l = 0; l < allLinks.length; l++) {
                        var link = allLinks[l];
                        var lText = (link.innerText || '').trim().split('\\n')[0];
                        var lHref = link.href || '';
                        if (lText.length < 5 || lText.length > 200 || seenL.has(lText)) continue;

                        var skipNav = ['home', 'about', 'contact', 'login', 'sign', 'register', 'privacy', 'terms', 'search', 'filter'];
                        var isNav = false;
                        for (var n = 0; n < skipNav.length; n++) {
                            if (lText.toLowerCase().indexOf(skipNav[n]) !== -1) { isNav = true; break; }
                        }
                        if (isNav) continue;

                        var isJobLink = /requisition|job|position|career|opening/i.test(lHref);
                        var hasJobTitle = /manager|officer|executive|engineer|analyst|lead|head|director|specialist|coordinator|associate|senior|junior|intern|trainee|designer|developer|consultant|supervisor|assistant|advisor/i.test(lText);

                        if (isJobLink || hasJobTitle) {
                            seenL.add(lText);
                            results.push({title: lText, url: lHref, location: '', department: ''});
                        }
                    }
                }

                // Deduplicate by title
                var unique = [];
                var seenTitles = new Set();
                for (var u = 0; u < results.length; u++) {
                    if (!seenTitles.has(results[u].title)) {
                        seenTitles.add(results[u].title);
                        unique.push(results[u]);
                    }
                }
                return unique;
            """)

            if js_jobs and len(js_jobs) > 0:
                logger.info(f"JS Taleo NG extraction found {len(js_jobs)} jobs")
                for jdx, jdata in enumerate(js_jobs):
                    title = jdata.get('title', '').strip()
                    url = jdata.get('url', '').strip()
                    location = jdata.get('location', '').strip()
                    department = jdata.get('department', '').strip()

                    if not title or len(title) < 3:
                        continue

                    if not url:
                        url = self.url

                    job_id = f"ubs_{jdx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': url,
                        'location': location,
                        'department': department,
                        'employment_type': '',
                        'description': '',
                        'posted_date': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    location_parts = self.parse_location(location)
                    job_data.update(location_parts)

                    if job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job {len(jobs)}: {title}")

                if jobs:
                    return jobs

            # --- Strategy 2: Selenium CSS selector-based extraction ---
            logger.info("JS extraction returned 0, trying Selenium selectors")
            job_elements = []
            selectors = [
                "div.oracletaleaborot-accordion-row",
                "div[class*='accordion-row']",
                "div[class*='searchResultItem']",
                "div[class*='requisition']",
                "tr.dataRow",
                "tr.data-row",
                "table tbody tr",
                "div[class*='job']",
                "div[class*='card']",
                "a[href*='requisition']",
                "span.titlelink a",
                "a.jobTitle-link",
            ]

            short_wait = WebDriverWait(driver, 5)
            for selector in selectors:
                try:
                    short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    valid = [e for e in elements if e.text.strip() and len(e.text.strip()) > 3]
                    if valid:
                        job_elements = valid
                        logger.info(f"Found {len(valid)} listings using selector: {selector}")
                        break
                except:
                    continue

            # Fallback: find links that look like job postings
            if not job_elements:
                all_links = driver.find_elements(By.TAG_NAME, 'a')
                job_links = []
                for link in all_links:
                    href = link.get_attribute('href') or ''
                    text = link.text.strip()
                    if ('requisition' in href.lower() or '/job' in href.lower() or 'TGnewUI' in href) and text and len(text) > 5:
                        skip_words = ['home', 'about', 'contact', 'login', 'sign', 'privacy', 'terms', 'search']
                        if not any(w in text.lower() for w in skip_words):
                            job_links.append(link)
                if job_links:
                    job_elements = job_links
                    logger.info(f"Fallback found {len(job_links)} job links")

            if not job_elements:
                logger.warning("Could not find job listings on Taleo NG page")
                return jobs

            for idx, job_elem in enumerate(job_elements, 1):
                try:
                    title = ""
                    job_url = ""

                    tag_name = job_elem.tag_name
                    if tag_name == 'a':
                        title = job_elem.text.strip().split('\n')[0]
                        job_url = job_elem.get_attribute('href')
                    elif tag_name == 'tr':
                        cells = job_elem.find_elements(By.TAG_NAME, 'td')
                        if cells:
                            try:
                                link = cells[0].find_element(By.CSS_SELECTOR, 'a, span.titlelink a')
                                title = link.text.strip()
                                job_url = link.get_attribute('href') or ''
                            except:
                                title = cells[0].text.strip()
                    else:
                        for sel in ['span.titlelink a', 'a.jobTitle-link', 'a[href*="requisition"]', 'h2 a', 'h3 a', 'a', 'h2', 'h3', 'span.titlelink']:
                            try:
                                el = job_elem.find_element(By.CSS_SELECTOR, sel)
                                title = el.text.strip()
                                job_url = el.get_attribute('href') or ''
                                if title:
                                    break
                            except:
                                continue

                    if not title:
                        text = job_elem.text.strip()
                        if text:
                            title = text.split('\n')[0].strip()

                    if not title or len(title) < 3:
                        continue

                    skip_words = ['search', 'filter', 'sort', 'showing', 'results', 'page', 'next', 'previous', 'refine', 'home', 'about']
                    if any(w == title.lower() for w in skip_words):
                        continue

                    if not job_url:
                        job_url = self.url

                    job_id = f"ubs_{idx}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

                    location = ""
                    try:
                        all_text = job_elem.text
                        lines = all_text.split('\n')
                        for line in lines:
                            line_s = line.strip()
                            if any(city in line_s for city in ['Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Pune', 'Hyderabad', 'India', 'Noida', 'Gurugram']):
                                location = line_s
                                break
                    except:
                        pass

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'apply_url': job_url,
                        'location': location,
                        'department': '',
                        'employment_type': '',
                        'description': '',
                        'posted_date': '',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }

                    location_parts = self.parse_location(location)
                    job_data.update(location_parts)

                    if job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job {len(jobs)}: {title}")
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result

        location_str = location_str.strip()
        parts = [p.strip() for p in location_str.split(',')]

        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) == 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]

        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'

        return result


if __name__ == "__main__":
    scraper = UBSGroupScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

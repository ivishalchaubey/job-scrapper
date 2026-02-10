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
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('relianceindustries_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class RelianceIndustriesScraper:
    def __init__(self):
        self.company_name = 'Reliance Industries'
        self.url = 'https://careers.ril.com/search-jobs'

    def setup_driver(self):
        """Set up Chrome driver with anti-detection options"""
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
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"ChromeDriver setup failed: {str(e)}")
            logger.info("Attempting fallback driver setup...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape jobs from Reliance Industries careers page.

        NOTE: As of Feb 2026, the careers.ril.com/search-jobs (old Phenom path)
        returns a 404 error. The RIL careers portal is now an ASP.NET site at
        careers.ril.com/rilcareers/index.aspx with a function dropdown search.
        Clicking Search without selecting a function shows all open positions in a
        paginated table at frmJobSearch.aspx.
        """
        jobs = []
        driver = None

        try:
            logger.info(f"Starting scrape for {self.company_name}")
            driver = self.setup_driver()

            # Strategy 1: Try the original URL first
            logger.info(f"Navigating to: {self.url}")
            driver.get(self.url)
            time.sleep(12)

            # Check if we got a 404 or error page
            if self._check_if_error_page(driver):
                logger.warning(f"Careers page at {self.url} returns 404/error - using ASP.NET portal instead")

                # Strategy 2: Navigate to the ASP.NET careers portal and search all jobs
                logger.info("Navigating to careers.ril.com landing page")
                driver.get('https://careers.ril.com/rilcareers/index.aspx')
                time.sleep(12)

                if self._check_if_error_page(driver):
                    logger.error("Reliance Industries careers portal is also returning errors")
                    return jobs

                # Click the Search button without selecting a function to see all jobs
                try:
                    search_btn = driver.find_element(By.ID, 'head_Button1')
                    search_btn.click()
                    logger.info("Clicked Search button to view all openings")
                    time.sleep(10)
                except Exception as e:
                    logger.error(f"Could not click search button: {str(e)}")
                    return jobs

            # Now we should be on frmJobSearch.aspx with job results
            # Scrape jobs from the table across multiple pages
            current_page = 1
            while current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")

                page_jobs = self._scrape_job_table(driver)
                if not page_jobs:
                    logger.info("No more jobs found on this page")
                    break

                jobs.extend(page_jobs)
                logger.info(f"Scraped {len(page_jobs)} jobs from page {current_page}")

                # Try to go to next page
                if current_page < max_pages:
                    if not self._go_to_next_page(driver, current_page):
                        logger.info("No more pages available")
                        break
                    time.sleep(5)

                current_page += 1

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise

        finally:
            if driver:
                driver.quit()

        return jobs

    def _check_if_error_page(self, driver):
        """Check if the current page shows a 404 or error page"""
        try:
            body_text = driver.execute_script("return document.body.innerText.substring(0, 500)")
            title = driver.title.lower()

            if '404' in title:
                return True
            if '404' in body_text and ('not found' in body_text.lower() or 'error' in body_text.lower()):
                return True
            if 'server error' in body_text.lower() and 'file or directory not found' in body_text.lower():
                return True
            if 'page not found' in body_text.lower():
                return True
            if len(body_text.strip()) < 200 and ('error' in body_text.lower() or 'not found' in body_text.lower()):
                return True
        except:
            pass
        return False

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page in the RIL job search results.

        The RIL careers portal uses ASP.NET controls for pagination:
        - input[type="submit"] buttons for Previous/Next (e.g. MainContent_rgJobs_lnkNext)
        - A select dropdown (PageDropDown) to jump to specific pages
        """
        try:
            next_page_num = current_page + 1

            # Strategy 1: Click the ASP.NET "Next" submit button
            next_clicked = driver.execute_script("""
                // Find the Next button (input[type="submit"] with value "Next")
                var inputs = document.querySelectorAll('input[type="submit"]');
                for (var i = 0; i < inputs.length; i++) {
                    var val = (inputs[i].value || '').trim().toLowerCase();
                    if (val === 'next' && !inputs[i].disabled) {
                        inputs[i].click();
                        return true;
                    }
                }
                return false;
            """)

            if next_clicked:
                logger.info(f"Clicked ASP.NET Next button for page {next_page_num}")
                time.sleep(8)
                return True

            # Strategy 2: Use the page dropdown if available
            page_selected = driver.execute_script(f"""
                var selects = document.querySelectorAll('select');
                for (var i = 0; i < selects.length; i++) {{
                    var name = (selects[i].name || '').toLowerCase();
                    var id = (selects[i].id || '').toLowerCase();
                    if (name.includes('page') || id.includes('page')) {{
                        // Select the next page option (0-indexed, so page 2 = index 1)
                        var targetIdx = {next_page_num - 1};
                        if (targetIdx < selects[i].options.length) {{
                            selects[i].selectedIndex = targetIdx;
                            selects[i].dispatchEvent(new Event('change', {{bubbles: true}}));
                            return true;
                        }}
                    }}
                }}
                return false;
            """)

            if page_selected:
                logger.info(f"Selected page {next_page_num} from dropdown")
                time.sleep(8)
                return True

            # Strategy 3: Try clicking links with page numbers
            next_page_selectors = [
                (By.XPATH, f'//a[text()="0{next_page_num}"]'),
                (By.XPATH, f'//a[text()="{next_page_num}"]'),
                (By.XPATH, '//a[contains(text(), "Next")]'),
            ]

            for selector_type, selector_value in next_page_selectors:
                try:
                    next_button = driver.find_element(selector_type, selector_value)
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    next_button.click()
                    logger.info(f"Clicked next page link for page {next_page_num}")
                    time.sleep(8)
                    return True
                except:
                    continue

            return False

        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            return False

    def _scrape_job_table(self, driver):
        """Scrape jobs from the RIL frmJobSearch.aspx table"""
        jobs = []

        try:
            # Check for "no current openings" message
            body_text = driver.execute_script("return document.body.innerText")
            if 'no current openings' in body_text.lower():
                logger.info("No current openings found")
                return jobs

            # Extract jobs using JavaScript from the table
            js_jobs = driver.execute_script("""
                var results = [];
                // The table has rows with: #, JOB TITLE, FUNCTIONAL AREA, LOCATION, POSTED ON
                var rows = document.querySelectorAll('table tr, tr');
                for (var i = 0; i < rows.length; i++) {
                    var cells = rows[i].querySelectorAll('td');
                    if (cells.length >= 4) {
                        var num = (cells[0].innerText || '').trim();
                        var titleCell = cells[1];
                        var title = (titleCell.innerText || '').trim();
                        var funcArea = (cells[2].innerText || '').trim();
                        var location = (cells[3].innerText || '').trim();
                        var postedOn = cells.length >= 5 ? (cells[4].innerText || '').trim() : '';

                        // Skip header row
                        if (num === '#' || title === 'JOB TITLE') continue;
                        if (!title || title.length < 3) continue;

                        // Extract job ID from title (format: "Title ( JOBID )")
                        var jobId = '';
                        var cleanTitle = title;
                        var idMatch = title.match(/\\(\\s*(\\d+)\\s*\\)/);
                        if (idMatch) {
                            jobId = idMatch[1];
                            cleanTitle = title.replace(/\\(\\s*\\d+\\s*\\)/, '').trim();
                        }

                        // Get link if available
                        var link = titleCell.querySelector('a[href]');
                        var url = link ? link.href : '';

                        results.push({
                            title: cleanTitle,
                            jobId: jobId,
                            department: funcArea,
                            location: location,
                            postedDate: postedOn,
                            url: url
                        });
                    }
                }
                return results;
            """)

            if js_jobs:
                logger.info(f"Table extraction found {len(js_jobs)} jobs")
                for idx, job_data in enumerate(js_jobs):
                    title = job_data.get('title', '')
                    job_id = job_data.get('jobId', '') or f"ril_{idx}"
                    department = job_data.get('department', '')
                    location = job_data.get('location', '')
                    posted_date = job_data.get('postedDate', '')
                    url = job_data.get('url', '')

                    if not title:
                        continue

                    city, state, _ = self.parse_location(location)

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
                        'apply_url': url if url else self.url,
                        'posted_date': posted_date,
                        'job_function': department,
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    })
            else:
                logger.warning("No job table rows found")

        except Exception as e:
            logger.error(f"Table extraction error: {str(e)}")

        return jobs

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job page"""
        details = {}

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            time.sleep(3)

            try:
                desc_selectors = [
                    (By.CSS_SELECTOR, 'div[class*="description"]'),
                    (By.XPATH, "//div[contains(@class, 'job-description')]"),
                    (By.CSS_SELECTOR, 'div.description'),
                ]

                for selector_type, selector_value in desc_selectors:
                    try:
                        desc_elem = driver.find_element(selector_type, selector_value)
                        details['description'] = desc_elem.text.strip()[:2000]
                        break
                    except:
                        continue
            except:
                pass

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass

        return details

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

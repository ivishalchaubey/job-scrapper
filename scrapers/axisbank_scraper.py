# Updated: Rewritten for HirePro ARISE portal (static landing page with roles table)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time

from core.logging import setup_logger
from config.scraper import HEADLESS_MODE, MAX_PAGES_TO_SCRAPE

logger = setup_logger('axisbank_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

class AxisBankScraper:
    def __init__(self):
        self.company_name = 'Axis Bank'
        self.url = 'https://axisbankarise.hirepro.in/'

    def setup_driver(self):
        """Set up Chrome driver with options"""
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

        driver = None
        try:
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info(f"ChromeDriver started with: {CHROMEDRIVER_PATH}")
        except Exception as e:
            logger.warning(f"ChromeDriver with service failed: {e}")
            try:
                driver = webdriver.Chrome(options=chrome_options)
                logger.info("Using default ChromeDriver")
            except Exception as e2:
                logger.error(f"All ChromeDriver attempts failed: {e2}")
                raise

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
        """Scrape jobs from Axis Bank ARISE HirePro landing page.

        The ARISE page is a static landing page (not a paginated job board).
        Roles are listed in a table with PDF job description links.
        There is one global 'Apply Now' registration link.
        Pagination (max_pages) is accepted for interface compatibility but not used.
        """
        jobs = []
        driver = None

        max_retries = 3
        for attempt in range(max_retries):
          try:
            logger.info(f"Starting scrape for {self.company_name} (attempt {attempt + 1}/{max_retries})")
            driver = self.setup_driver()

            try:
                driver.get(self.url)
            except Exception as nav_err:
                logger.warning(f"Navigation error: {nav_err}")
                if driver:
                    driver.quit()
                    driver = None
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                raise

            # Wait for the page to load -- it's a simple static HTML page
            time.sleep(5)

            # Verify we landed on the right page
            logger.info(f"Page title: {driver.title}, URL: {driver.current_url}")

            # --- Extract the global "Apply Now" URL ---
            apply_url = self.url  # fallback
            try:
                apply_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="registration"]')
                if not apply_links:
                    apply_links = driver.find_elements(By.XPATH, '//a[contains(text(), "Apply Now")]')
                if apply_links:
                    apply_url = apply_links[0].get_attribute('href')
                    logger.info(f"Found Apply Now URL: {apply_url}")
            except Exception as e:
                logger.warning(f"Could not find Apply Now link: {e}")

            # --- Extract roles from the table ---
            # Each role is a <tr> with two <td>s: role name and a "Download JD" PDF link.
            jobs = self._extract_roles_from_table(driver, apply_url)

            if not jobs:
                # Fallback: try extracting via JavaScript in case DOM structure varies
                logger.info("Table extraction found 0 roles, trying JS fallback")
                jobs = self._extract_roles_js_fallback(driver, apply_url)

            if not jobs:
                # Last-resort fallback: extract from PDF links paired with preceding text
                logger.info("JS fallback found 0 roles, trying PDF-link fallback")
                jobs = self._extract_roles_from_pdf_links(driver, apply_url)

            logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
            break  # Success

          except Exception as e:
            logger.error(f"Error scraping {self.company_name} (attempt {attempt + 1}): {str(e)}")
            if driver:
                driver.quit()
                driver = None
            if attempt < max_retries - 1:
                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                raise

          finally:
            if driver:
                driver.quit()
                driver = None

        return jobs

    def _extract_roles_from_table(self, driver, apply_url):
        """Extract roles from the HTML table rows under the 'Roles Available' section.

        Expected structure:
          <tr>
            <td>Role Name</td>
            <td><a href="jds/SomeFile.pdf">Download JD</a></td>
          </tr>
        """
        jobs = []
        try:
            # Find all table rows that contain a PDF download link
            rows = driver.find_elements(By.CSS_SELECTOR, 'tr')
            logger.info(f"Found {len(rows)} table rows total")

            for idx, row in enumerate(rows):
                try:
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) < 2:
                        continue

                    role_name = cells[0].text.strip()
                    if not role_name or len(role_name) < 2:
                        continue

                    # Look for a PDF link in the second cell
                    jd_url = ''
                    try:
                        pdf_link = cells[1].find_element(By.CSS_SELECTOR, 'a[href*=".pdf"]')
                        jd_url = pdf_link.get_attribute('href')
                    except:
                        # Also check other cells
                        for cell in cells[1:]:
                            try:
                                pdf_link = cell.find_element(By.CSS_SELECTOR, 'a[href*=".pdf"]')
                                jd_url = pdf_link.get_attribute('href')
                                break
                            except:
                                continue

                    if not jd_url:
                        # Skip rows without a JD PDF -- they are likely headers
                        continue

                    # Build a stable job ID from the role name
                    role_slug = role_name.lower().replace(' ', '_').replace('-', '_')
                    job_id = f"axisbank_arise_{role_slug}"

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': f"ARISE - {role_name}",
                        'description': f"Axis Bank ARISE program role in {role_name}. Job description: {jd_url}",
                        'location': 'India',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': 'Full-time',
                        'department': role_name,
                        'apply_url': apply_url,
                        'posted_date': '',
                        'job_function': role_name,
                        'experience_level': '0-5 years',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active',
                        'jd_pdf_url': jd_url,
                    }

                    jobs.append(job_data)
                    logger.info(f"Extracted role: {role_name} (JD: {jd_url})")

                except Exception as e:
                    logger.error(f"Error extracting row {idx}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Table extraction failed: {str(e)}")

        return jobs

    def _extract_roles_js_fallback(self, driver, apply_url):
        """JavaScript fallback: extract role rows from the table via JS."""
        jobs = []
        try:
            role_data = driver.execute_script("""
                var results = [];
                var rows = document.querySelectorAll('tr');
                for (var i = 0; i < rows.length; i++) {
                    var cells = rows[i].querySelectorAll('td');
                    if (cells.length < 2) continue;
                    var roleName = (cells[0].innerText || '').trim();
                    if (!roleName || roleName.length < 2) continue;
                    var pdfLink = cells[1].querySelector('a[href*=".pdf"]');
                    if (!pdfLink) continue;
                    results.push({
                        name: roleName,
                        jd_url: pdfLink.href
                    });
                }
                return results;
            """)

            if role_data:
                logger.info(f"JS fallback found {len(role_data)} roles")
                for rd in role_data:
                    role_name = rd.get('name', '').strip()
                    jd_url = rd.get('jd_url', '').strip()
                    if not role_name:
                        continue

                    role_slug = role_name.lower().replace(' ', '_').replace('-', '_')
                    job_id = f"axisbank_arise_{role_slug}"

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': f"ARISE - {role_name}",
                        'description': f"Axis Bank ARISE program role in {role_name}. Job description: {jd_url}",
                        'location': 'India',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': 'Full-time',
                        'department': role_name,
                        'apply_url': apply_url,
                        'posted_date': '',
                        'job_function': role_name,
                        'experience_level': '0-5 years',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active',
                        'jd_pdf_url': jd_url,
                    }
                    jobs.append(job_data)
                    logger.info(f"JS Extracted role: {role_name}")

        except Exception as e:
            logger.error(f"JS fallback failed: {str(e)}")

        return jobs

    def _extract_roles_from_pdf_links(self, driver, apply_url):
        """Last-resort fallback: extract roles by finding all PDF links and deriving
        role names from the PDF filename or surrounding text."""
        jobs = []
        try:
            pdf_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*=".pdf"]')
            logger.info(f"PDF-link fallback found {len(pdf_links)} PDF links")

            for pdf_link in pdf_links:
                try:
                    jd_url = pdf_link.get_attribute('href')
                    if not jd_url:
                        continue

                    # Derive role name from the PDF filename
                    # e.g. "jds/BusinessIntelligenceUnit.pdf" -> "Business Intelligence Unit"
                    filename = jd_url.split('/')[-1].replace('.pdf', '')
                    # Insert spaces before capital letters: "BusinessIntelligenceUnit" -> "Business Intelligence Unit"
                    import re
                    role_name = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', filename)
                    role_name = role_name.replace('-', ' - ')  # handle hyphens like "InternalAudit-CorporateAudits"

                    if not role_name or len(role_name) < 2:
                        continue

                    role_slug = role_name.lower().replace(' ', '_').replace('-', '_')
                    job_id = f"axisbank_arise_{role_slug}"

                    job_data = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'company_name': self.company_name,
                        'title': f"ARISE - {role_name}",
                        'description': f"Axis Bank ARISE program role in {role_name}. Job description: {jd_url}",
                        'location': 'India',
                        'city': '',
                        'state': '',
                        'country': 'India',
                        'employment_type': 'Full-time',
                        'department': role_name,
                        'apply_url': apply_url,
                        'posted_date': '',
                        'job_function': role_name,
                        'experience_level': '0-5 years',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active',
                        'jd_pdf_url': jd_url,
                    }
                    jobs.append(job_data)
                    logger.info(f"PDF-link extracted role: {role_name}")

                except Exception as e:
                    logger.error(f"Error extracting from PDF link: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"PDF-link fallback failed: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

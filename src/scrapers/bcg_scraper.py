from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
import hashlib
import time
import sys
from datetime import datetime
from pathlib import Path
import os
import stat

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.logger import setup_logger
from src.config import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('bcg_scraper')

class BCGScraper:
    def __init__(self):
        self.company_name = 'BCG'
        # Filter for India locations
        self.url = 'https://careers.bcg.com/global/en/search-results?rk=page-targeted-jobs-page54-prod-ds-Nusa6pGk&sortBy=Most%20relevant'
    
    def setup_driver(self):
        """Set up Chrome driver with options"""
        chrome_options = Options()
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        # Install and get the correct chromedriver path
        driver_path = ChromeDriverManager().install()
        
        # Fix for macOS ARM - ensure we have the actual chromedriver executable
        driver_path_obj = Path(driver_path)
        if driver_path_obj.name != 'chromedriver':
            # Navigate to find the actual chromedriver
            parent = driver_path_obj.parent
            actual_driver = parent / 'chromedriver'
            if actual_driver.exists():
                driver_path = str(actual_driver)
            else:
                # Search in subdirectories
                for file in parent.rglob('chromedriver'):
                    if file.is_file() and not file.name.endswith('.zip'):
                        driver_path = str(file)
                        break
        
        # Ensure chromedriver has execute permissions
        try:
            current_permissions = os.stat(driver_path).st_mode
            os.chmod(driver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            logger.info(f"Set execute permissions on chromedriver: {driver_path}")
        except Exception as e:
            logger.warning(f"Could not set permissions on chromedriver: {str(e)}")
        
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(SCRAPE_TIMEOUT)
        return driver
    
    def generate_external_id(self, job_id, company):
        """Generate stable external_id using MD5 hash"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Main scraping method"""
        driver = None
        all_jobs = []
        
        try:
            driver = self.setup_driver()
            logger.info(f"Starting {self.company_name} scraping from {self.url}")
            
            driver.get(self.url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            
            # Wait for job listings to load
            time.sleep(3)
            
            try:
                # Wait for search results container
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-list-item, [class*='job'], article")))
                logger.info("Job listings loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for job listings: {str(e)}")
            
            # Scrape current page
            jobs = self._scrape_page(driver, wait)
            all_jobs.extend(jobs)
            
            logger.info(f"Total jobs scraped: {len(all_jobs)}")
            return all_jobs
            
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return all_jobs
        finally:
            if driver:
                driver.quit()
                logger.info("Browser closed")
    
    def _scrape_page(self, driver, wait):
        """Scrape all jobs from current page"""
        jobs = []
        scraped_ids = set()
        
        try:
            # Scroll to load all content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Find all job listings - try multiple selectors
            job_elements = []
            selectors = [
                ".jobs-list-item",
                "article[class*='job']",
                "[data-ph-at-job-title-text]",
                ".job-result",
                "[class*='result']"
            ]
            
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        job_elements = elements
                        logger.info(f"Found {len(job_elements)} job listings using selector: {selector}")
                        break
                except:
                    continue
            
            if not job_elements:
                logger.warning("Could not find job listings with any selector")
                return jobs
            
            for idx, job_elem in enumerate(job_elements, 1):
                try:
                    job_data = self._extract_job_from_element(job_elem, driver, wait, idx)
                    if job_data and job_data['external_id'] not in scraped_ids:
                        jobs.append(job_data)
                        scraped_ids.add(job_data['external_id'])
                        logger.info(f"Extracted job {len(jobs)}: {job_data.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"Error extracting job {idx}: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"Error scraping page: {str(e)}")
        
        return jobs
    
    def _extract_job_from_element(self, job_elem, driver, wait, idx):
        """Extract job data from a job listing element"""
        try:
            # Scroll into view and hover
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", job_elem)
                time.sleep(0.3)
                actions = ActionChains(driver)
                actions.move_to_element(job_elem).perform()
                time.sleep(0.3)
            except Exception as e:
                logger.debug(f"Could not hover over job {idx}: {str(e)}")
            
            # Extract job title and URL
            title = ""
            job_url = ""
            
            try:
                # Try different selectors for title link
                title_selectors = [
                    "h3 a",
                    "a[data-ph-at-job-title-text]",
                    ".job-title a",
                    "a[href*='/job/']",
                    "h2 a",
                    "h4 a"
                ]
                
                for selector in title_selectors:
                    try:
                        title_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip()
                        job_url = title_elem.get_attribute('href')
                        if title and job_url:
                            break
                    except:
                        continue
                
                if not title:
                    # Fallback: try any link with text
                    links = job_elem.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        text = link.text.strip()
                        href = link.get_attribute('href')
                        if text and len(text) > 10 and href and '/job' in href.lower():
                            title = text
                            job_url = href
                            break
                            
            except Exception as e:
                logger.warning(f"Could not extract title: {str(e)}")
                return None
            
            if not title or not job_url:
                logger.warning(f"Missing title or URL for job {idx}")
                return None
            
            # Extract job ID from URL
            job_id = ""
            if 'jobId=' in job_url:
                job_id = job_url.split('jobId=')[-1].split('&')[0]
            elif '/job/' in job_url:
                job_id = job_url.split('/job/')[-1].split('/')[0].split('?')[0]
            else:
                job_id = f"bcg_{idx}_{hashlib.md5(job_url.encode()).hexdigest()[:8]}"
            
            # Extract location
            location = ""
            try:
                location_selectors = [
                    "[data-ph-at-job-location-text]",
                    ".job-location",
                    "[class*='location']"
                ]
                
                for selector in location_selectors:
                    try:
                        loc_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        location = loc_elem.text.strip()
                        if location:
                            break
                    except:
                        continue
                
                # If still no location, search all text
                if not location:
                    all_text = job_elem.text
                    if 'India' in all_text:
                        lines = all_text.split('\n')
                        for line in lines:
                            if 'India' in line:
                                location = line.strip()
                                break
            except Exception as e:
                logger.debug(f"Could not extract location: {str(e)}")
            
            # Extract department/category
            department = ""
            try:
                dept_selectors = [
                    "[data-ph-at-job-category-text]",
                    ".job-category",
                    "[class*='category']"
                ]
                
                for selector in dept_selectors:
                    try:
                        dept_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        department = dept_elem.text.strip()
                        if department:
                            break
                    except:
                        continue
            except:
                pass
            
            # Extract job ID text if displayed
            job_id_text = ""
            try:
                id_selectors = [
                    "[data-ph-at-job-id-text]",
                    ".job-id",
                    "[class*='job-id']"
                ]
                
                for selector in id_selectors:
                    try:
                        id_elem = job_elem.find_element(By.CSS_SELECTOR, selector)
                        job_id_text = id_elem.text.strip()
                        if job_id_text:
                            # Override job_id with displayed ID if it exists
                            job_id = job_id_text
                            break
                    except:
                        continue
            except:
                pass
            
            # Build job data
            job_data = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'company_name': self.company_name,
                'title': title,
                'apply_url': job_url,
                'location': location,
                'department': department,
                'employment_type': '',
                'description': '',
                'posted_date': ''
            }

            # Fetch full details if enabled
            if FETCH_FULL_JOB_DETAILS:
                try:
                    logger.info(f"Fetching details for: {title}")
                    details = self._fetch_job_details(driver, job_url)
                    if details:
                        job_data.update(details)
                except Exception as e:
                    logger.warning(f"Could not fetch details for {title}: {str(e)}")
            
            # Parse location
            location_parts = self.parse_location(job_data.get('location', ''))
            job_data.update(location_parts)
            
            return job_data
            
        except Exception as e:
            logger.error(f"Error extracting job data: {str(e)}")
            return None

    def _fetch_job_details(self, driver, job_url):
        """Fetch full job details by visiting the job details page"""
        details = {
            'description': '',
            'location': '',
            'department': '',
            'employment_type': '',
            'posted_date': ''
        }

        try:
            original_window = driver.current_window_handle
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            driver.get(job_url)
            wait = WebDriverWait(driver, SCRAPE_TIMEOUT)
            time.sleep(2)

            # Description
            description_selectors = [
                "[data-ph-at-id='jobDescription']",
                "[data-ph-at-id='jobdescription']",
                ".job-description",
                "[class*='job-description']",
                "[class*='description']"
            ]
            for selector in description_selectors:
                try:
                    desc_elem = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    text = desc_elem.text.strip()
                    if text:
                        details['description'] = text[:3000]
                        break
                except Exception:
                    continue

            # Location
            location_selectors = [
                "[data-ph-at-id='jobLocation']",
                "[data-ph-at-id='jobLocationText']",
                ".job-location",
                "[class*='location']"
            ]
            for selector in location_selectors:
                try:
                    loc_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = loc_elem.text.strip()
                    if text:
                        details['location'] = text
                        break
                except Exception:
                    continue

            # Department / Category
            department_selectors = [
                "[data-ph-at-id='jobCategory']",
                "[data-ph-at-id='jobCategoryText']",
                ".job-category",
                "[class*='category']"
            ]
            for selector in department_selectors:
                try:
                    dept_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = dept_elem.text.strip()
                    if text:
                        details['department'] = text
                        break
                except Exception:
                    continue

            # Employment type
            employment_selectors = [
                "[data-ph-at-id='jobType']",
                "[data-ph-at-id='jobTypeText']",
                ".job-type",
                "[class*='job-type']"
            ]
            for selector in employment_selectors:
                try:
                    type_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = type_elem.text.strip()
                    if text:
                        details['employment_type'] = text
                        break
                except Exception:
                    continue

            # Posted date
            posted_selectors = [
                "[data-ph-at-id='jobPostedDate']",
                "[class*='posted']",
                "[class*='date']"
            ]
            for selector in posted_selectors:
                try:
                    date_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    text = date_elem.text.strip()
                    if text and len(text) < 50:
                        details['posted_date'] = text
                        break
                except Exception:
                    continue

            # Fallback: get main content text if description is still empty
            if not details['description']:
                try:
                    main_content = driver.find_element(By.CSS_SELECTOR, "main, [role='main']")
                    full_text = main_content.text.strip()
                    if full_text:
                        details['description'] = full_text[:3000]
                except Exception:
                    pass

            driver.close()
            driver.switch_to.window(original_window)

        except Exception as e:
            logger.error(f"Error fetching job details from {job_url}: {str(e)}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass

        return details
    
    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        result = {
            'city': '',
            'state': '',
            'country': ''
        }
        
        if not location_str:
            return result
        
        # Clean up location string
        location_str = location_str.strip()
        
        # Common BCG location formats:
        # "Gurgaon, Haryana, India"
        # "Mumbai, India"
        # "Available in 5 locations"
        
        if 'Available in' in location_str or 'location' in location_str.lower():
            # Multi-location job
            result['country'] = 'India'  # Since we're filtering for India
            return result
        
        # Try to parse comma-separated location
        parts = [p.strip() for p in location_str.split(',')]
        
        if len(parts) >= 1:
            result['city'] = parts[0]
        
        if len(parts) == 3:
            # Format: City, State, Country
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            # Format: City, Country
            result['country'] = parts[1]
        
        # Default to India if India mentioned
        if 'India' in location_str or 'IND' in location_str:
            result['country'] = 'India'
        
        return result

if __name__ == "__main__":
    scraper = BCGScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs:
        print(f"- {job['title']} | {job['location']}")

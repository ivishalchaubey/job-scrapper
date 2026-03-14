from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import html
import time
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.logging import setup_logger
from core.webdriver_utils import setup_chrome_driver
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE
from scrapers.csv_url_resolver import get_company_url

logger = setup_logger('statebankofindia_scraper')

class StateBankOfIndiaScraper:
    def __init__(self):
        self.company_name = "State Bank of India"
        # sbi.co.in/web/careers/current-openings redirects to sbi.bank.in/web/careers/current-openings
        default_url = "https://sbi.bank.in/web/careers/current-openings"
        self.url = get_company_url(self.company_name, default_url)
    
    def setup_driver(self):
        """Set up Chrome driver using cross-platform utility"""
        return setup_chrome_driver(headless_mode=HEADLESS_MODE)

    def generate_external_id(self, job_id, company):
        """Generate stable external ID"""
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _get_headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    def _clean_text(self, value):
        if not value:
            return ''
        text = html.unescape(value)
        text = re.sub(r'[ \t\r\f\v]+', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        return text.strip()

    def _extract_apply_start_date(self, text):
        if not text:
            return ''

        match = re.search(
            r'apply\s+online\s+from\s+(\d{2}[.-]\d{2}[.-]\d{4})\s+to\s+\d{2}[.-]\d{2}[.-]\d{4}',
            text,
            re.IGNORECASE,
        )
        return match.group(1) if match else ''

    def _normalize_date(self, value):
        if not value:
            return ''

        value = str(value).strip()
        for fmt in ('%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(value, fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return value

    def _clean_title(self, title):
        if not title:
            return ''
        title = re.sub(r'\s*\((?:Apply Online|Online Registration).*?\)\s*$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s+', ' ', title)
        return title.strip()

    def _is_current_opening(self, description, apply_url):
        if not description or not apply_url:
            return False
        upper_description = description.upper()
        return (
            'APPLY ONLINE' in upper_description or
            'PRINT APPLICATION' in upper_description or
            'APPLY NOW' in upper_description
        )

    def _scrape_page_html(self, page_html):
        jobs = []
        soup = BeautifulSoup(page_html, 'html.parser')
        cards = soup.select('div.card')

        for card in cards:
            accordion = card.select_one('div.accordion.lateral')
            if not accordion:
                continue

            header = accordion.select_one('div.text-uppercase')
            content = card.select_one('div.accordion-content')
            if not header:
                continue

            header_paragraphs = header.find_all('p')
            if not header_paragraphs:
                continue

            raw_title = self._clean_text(header_paragraphs[0].get_text(' ', strip=True))
            if not raw_title:
                continue
            title = self._clean_title(raw_title)

            adv_no = ''
            for paragraph in header_paragraphs[1:]:
                text = self._clean_text(paragraph.get_text(' ', strip=True))
                adv_match = re.search(r'ADVERTISEMENT\s+NO:\s*(.+)$', text, re.IGNORECASE)
                if adv_match:
                    adv_no = adv_match.group(1).strip()
                    break

            article_id = (accordion.get('data-articleid') or '').strip()
            job_id = adv_no or article_id or hashlib.md5(raw_title.encode()).hexdigest()[:12]

            button = accordion.select_one('button')
            last_date = ''
            if button:
                button_text = self._clean_text(button.get_text(' ', strip=True))
                last_date_match = re.search(r'LAST DATE TO APPLY\s*:\s*(.+)$', button_text, re.IGNORECASE)
                if last_date_match:
                    last_date = last_date_match.group(1).strip()

            apply_url = ''
            description = ''
            if content:
                links = content.select('a[href]')
                for link in links:
                    link_text = self._clean_text(link.get_text(' ', strip=True))
                    if 'APPLY' in link_text.upper():
                        apply_url = urljoin(self.url, link.get('href', ''))
                        break

                description = self._clean_text(content.get_text('\n', strip=True))

            if not apply_url:
                continue

            apply_period_text = self._clean_text(header.get_text(' ', strip=True))
            posted_date = self._normalize_date(self._extract_apply_start_date(apply_period_text))
            if not self._is_current_opening(description, apply_url):
                continue

            job = {
                'external_id': self.generate_external_id(job_id, self.company_name),
                'job_id': job_id,
                'company_name': self.company_name,
                'title': title,
                'description': description,
                'location': '',
                'city': '',
                'state': '',
                'country': '',
                'employment_type': '',
                'department': (accordion.get('data-type-department') or '').strip(),
                'apply_url': apply_url,
                'posted_date': posted_date,
                'job_function': (accordion.get('data-type-role') or '').strip(),
                'experience_level': '',
                'salary_range': '',
                'remote_type': '',
                'status': 'active'
            }
            jobs.append(job)

        return jobs

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        """Scrape recruitment openings from SBI careers page"""
        try:
            logger.info(f"Starting scrape for {self.company_name}")
            response = requests.get(self.url, headers=self._get_headers(), timeout=SCRAPE_TIMEOUT)
            response.raise_for_status()
            jobs = self._scrape_page_html(response.text)
            if jobs:
                logger.info(f"Successfully scraped {len(jobs)} total recruitment notices from {self.company_name}")
                return jobs
            logger.warning("HTML parser found no recruitment notices, falling back to Selenium")
        except Exception as e:
            logger.warning(f"HTML scraping failed for {self.company_name}: {str(e)}")

        jobs = []
        driver = None
        try:
            driver = self.setup_driver()
            driver.get(self.url)
            time.sleep(15)

            for scroll_i in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * %s);" % str((scroll_i + 1) / 5))
                time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            page_jobs = self._scrape_page_js(driver)
            jobs.extend(page_jobs)
            logger.info(f"Successfully scraped {len(jobs)} total recruitment notices from {self.company_name}")
        except Exception as e:
            logger.error(f"Error scraping {self.company_name}: {str(e)}")
            raise
        finally:
            if driver:
                driver.quit()

        return jobs

    def _scrape_page_js(self, driver):
        """Scrape SBI recruitment notices using JavaScript extraction"""
        jobs = []
        time.sleep(3)

        try:
            # SBI page structure: recruitment notices with titles in uppercase,
            # ADVERTISEMENT NO: CRPD/xxx, LAST DATE TO APPLY, and "APPLY ONLINE" links
            js_jobs = driver.execute_script("""
                var jobs = [];
                var seen = {};
                var bodyText = document.body.innerText || '';
                var lines = bodyText.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });

                // Method 1: Parse recruitment blocks from text content
                // Each recruitment block starts with a title in CAPS and has an ADVERTISEMENT NO
                var currentTitle = '';
                var currentAdvNo = '';
                var currentLastDate = '';
                var currentApplyUrl = '';

                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];

                    // Detect recruitment title - typically all uppercase, starts with RECRUITMENT/ENGAGEMENT
                    if ((line.startsWith('RECRUITMENT') || line.startsWith('ENGAGEMENT') ||
                         line.startsWith('SELECTION') || line.startsWith('EMPANELMENT')) &&
                        line.length > 20 && line.length < 500) {

                        // Save previous block if exists
                        if (currentTitle && currentAdvNo && !seen[currentAdvNo]) {
                            seen[currentAdvNo] = true;
                            jobs.push({
                                title: currentTitle,
                                advNo: currentAdvNo,
                                lastDate: currentLastDate,
                                applyUrl: currentApplyUrl
                            });
                        }

                        currentTitle = line;
                        currentAdvNo = '';
                        currentLastDate = '';
                        currentApplyUrl = '';
                    }

                    // Extract advertisement number
                    if (line.includes('ADVERTISEMENT NO') || line.includes('ADVT. NO')) {
                        var advMatch = line.match(/CRPD\\/[\\w-]+\\/\\d+/);
                        if (advMatch) {
                            currentAdvNo = advMatch[0];
                        } else {
                            // Try next line
                            if (i + 1 < lines.length) {
                                advMatch = lines[i+1].match(/CRPD\\/[\\w-]+\\/\\d+/);
                                if (advMatch) currentAdvNo = advMatch[0];
                            }
                        }
                    }

                    // Extract last date
                    if (line.includes('LAST DATE TO APPLY')) {
                        var dateMatch = line.match(/\\d{2}-\\d{2}-\\d{4}/);
                        if (dateMatch) {
                            currentLastDate = dateMatch[0];
                        }
                    }
                }

                // Save the last block
                if (currentTitle && currentAdvNo && !seen[currentAdvNo]) {
                    seen[currentAdvNo] = true;
                    jobs.push({
                        title: currentTitle,
                        advNo: currentAdvNo,
                        lastDate: currentLastDate,
                        applyUrl: currentApplyUrl
                    });
                }

                // Method 2: Also find "APPLY ONLINE" links and match them
                var applyLinks = document.querySelectorAll('a[href*="recruitment.sbi"], a[href*="apply"]');
                var linkMap = {};
                applyLinks.forEach(function(link) {
                    var text = (link.textContent || '').trim();
                    var href = link.href || '';
                    if (text.includes('APPLY') && href.length > 10) {
                        // Try to find the associated advertisement
                        var parent = link.parentElement;
                        for (var p = 0; p < 5; p++) {
                            if (parent && parent.parentElement) {
                                parent = parent.parentElement;
                            }
                        }
                        var pText = (parent ? parent.innerText : '') || '';
                        var advMatch = pText.match(/CRPD\\/[\\w-]+\\/\\d+/);
                        if (advMatch) {
                            linkMap[advMatch[0]] = href;
                        }
                    }
                });

                // Attach apply URLs
                for (var k = 0; k < jobs.length; k++) {
                    if (linkMap[jobs[k].advNo]) {
                        jobs[k].applyUrl = linkMap[jobs[k].advNo];
                    }
                }

                // Method 3: Also find PDF links for detailed notifications
                var pdfLinks = document.querySelectorAll('a[href*=".pdf"]');
                var pdfMap = {};
                pdfLinks.forEach(function(link) {
                    var href = link.href || '';
                    var parent = link.parentElement;
                    for (var p = 0; p < 5; p++) {
                        if (parent && parent.parentElement) parent = parent.parentElement;
                    }
                    var pText = (parent ? parent.innerText : '') || '';
                    var advMatch = pText.match(/CRPD\\/[\\w-]+\\/\\d+/);
                    if (advMatch && href.includes('.pdf')) {
                        if (!pdfMap[advMatch[0]]) pdfMap[advMatch[0]] = href;
                    }
                });

                return jobs;
            """)

            if js_jobs:
                logger.info(f"JS extraction found {len(js_jobs)} recruitment notices")
                for job_data in js_jobs:
                    title = job_data.get('title', '')
                    if not title or len(title) < 10:
                        continue

                    adv_no = job_data.get('advNo', '')
                    last_date = job_data.get('lastDate', '')
                    apply_url = job_data.get('applyUrl', '')

                    # Clean up title - make it more readable
                    clean_title = title
                    # Remove "(APPLY ONLINE FROM ...)" part from title if present
                    paren_match = re.search(r'\(APPLY ONLINE.*?\)', clean_title)
                    if paren_match:
                        clean_title = clean_title[:paren_match.start()].strip()
                    # Also remove other parenthetical notes
                    paren_match2 = re.search(r'\(ONLINE REGISTRATION.*?\)', clean_title)
                    if paren_match2:
                        clean_title = clean_title[:paren_match2.start()].strip()
                    paren_match3 = re.search(r'\(LIST OF.*?\)', clean_title)
                    if paren_match3:
                        clean_title = clean_title[:paren_match3.start()].strip()
                    paren_match4 = re.search(r'\(INTERVIEW.*?\)', clean_title)
                    if paren_match4:
                        clean_title = clean_title[:paren_match4.start()].strip()
                    paren_match5 = re.search(r'\(FINAL RESULT.*?\)', clean_title)
                    if paren_match5:
                        clean_title = clean_title[:paren_match5.start()].strip()
                    paren_match6 = re.search(r'\(REVISED.*?\)', clean_title)
                    if paren_match6:
                        clean_title = clean_title[:paren_match6.start()].strip()

                    job_id = adv_no or hashlib.md5(title.encode()).hexdigest()[:12]

                    job = {
                        'external_id': self.generate_external_id(job_id, self.company_name),
                        'job_id': job_id,
                        'company_name': self.company_name,
                        'title': clean_title,
                        'description': '',
                        'location': '',
                        'city': '',
                        'state': '',
                        'country': '',
                        'employment_type': '',
                        'department': '',
                        'apply_url': apply_url if apply_url else self.url,
                        'posted_date': '',
                        'job_function': '',
                        'experience_level': '',
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active'
                    }
                    jobs.append(job)
            else:
                logger.warning("JS extraction found no recruitment notices")

        except Exception as e:
            logger.error(f"Error in JS extraction: {str(e)}")

        return jobs

    def parse_location(self, location_str):
        """Parse location string into city, state, country"""
        if not location_str:
            return '', '', 'India'

        parts = [p.strip() for p in location_str.split(',')]
        city = parts[0] if len(parts) > 0 else ''
        state = parts[1] if len(parts) > 1 else ''

        return city, state, 'India'

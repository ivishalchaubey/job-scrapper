import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET

import requests

from core.logging import setup_logger
from config.scraper import MAX_PAGES_TO_SCRAPE

logger = setup_logger('axisbank_scraper')


class AxisBankScraper:
    def __init__(self):
        self.company_name = "Axis Bank"
        self.token = "WIXhCuz0XRZ7H0GZCwjJ"
        self.source = "CAREERSITE"
        self.url = (
            "https://axisbank.ripplehire.com/candidate/"
            "?token=WIXhCuz0XRZ7H0GZCwjJ&source=CAREERSITE#list"
        )
        self.list_api_url = "https://axisbank.ripplehire.com/candidate/candidatejobsearch"
        self.detail_api_url = "https://axisbank.ripplehire.com/candidate/candidatejobdetail"
        self.base_apply_url = (
            "https://axisbank.ripplehire.com/candidate/"
            "?token=WIXhCuz0XRZ7H0GZCwjJ&source=CAREERSITE#apply/job/"
        )

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _clean_html_text(self, raw_text):
        if not raw_text:
            return ''
        text = html.unescape(str(raw_text))
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _extract_experience(self, exp_text, description_text):
        seed = exp_text or description_text or ''
        if not seed:
            return ''
        match = re.search(r'(\d+\s*-\s*\d+\s*Years?)', seed, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r'(\d+\+?\s*Years?)', seed, re.IGNORECASE)
        if match:
            return match.group(1)
        return exp_text or ''

    def _build_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/xml,text/xml,*/*;q=0.8',
        })
        return session

    def _fetch_job_list_page(self, session, page_index, page_size):
        params = {
            "page": page_index,
            "search": "*:*",
            "campaignSeq": "",
            "token": self.token,
            "source": self.source,
            "pagesize": page_size,
        }
        payload = {
            "careerSiteUrlParams": json.dumps(params, separators=(',', ':')),
            "lang": "en",
        }
        response = session.post(self.list_api_url, data=payload, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        total_count_text = root.findtext('totalJobCount') or '0'
        total_count = int(total_count_text) if total_count_text.isdigit() else 0

        job_parent = root.find('jobVoList')
        job_nodes = job_parent.findall('jobVoList') if job_parent is not None else []
        return total_count, job_nodes

    def _fetch_job_detail(self, session, job_seq):
        params = {
            "token": self.token,
            "jobSeq": str(job_seq),
            "source": self.source,
            "lang": "en",
        }
        try:
            response = session.get(self.detail_api_url, params=params, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except Exception as e:
            logger.warning(f"Detail fetch failed for job {job_seq}: {str(e)}")
            return {
                "description": "",
                "employment_type": "",
                "posted_date": "",
                "department": "",
            }

        job_node = root.find('jobVO')
        if job_node is None:
            return {
                "description": "",
                "employment_type": "",
                "posted_date": "",
                "department": "",
            }

        raw_description = job_node.findtext('jobDesc') or ''
        description = self._clean_html_text(raw_description)
        employment_type = (job_node.findtext('jobType') or '').strip()
        posted_date = (job_node.findtext('jobPostingDate') or '').strip()
        department = (job_node.findtext('jobPositions') or '').strip()

        return {
            "description": description[:15000] if description else "",
            "employment_type": employment_type,
            "posted_date": posted_date,
            "department": department,
        }

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        jobs = []
        page_size = 10
        session = self._build_session()

        logger.info(f"Starting scrape for {self.company_name} via RippleHire API")

        for page_index in range(max_pages):
            try:
                total_count, job_nodes = self._fetch_job_list_page(session, page_index, page_size)
            except Exception as e:
                logger.error(f"Job list fetch failed for page={page_index}: {str(e)}")
                break

            if not job_nodes:
                logger.info(f"No jobs returned on page={page_index}; stopping")
                break

            logger.info(
                f"Page {page_index + 1}: fetched {len(job_nodes)} jobs "
                f"(total available: {total_count})"
            )

            for job_node in job_nodes:
                try:
                    job_seq = (job_node.findtext('jobSeq') or '').strip()
                    title = (job_node.findtext('jobTitle') or '').strip()
                    location = (job_node.findtext('locations') or '').strip()
                    exp_text = (job_node.findtext('jobReqExp') or '').strip()

                    if not job_seq or not title:
                        continue

                    detail = self._fetch_job_detail(session, job_seq)
                    description = detail.get('description', '')
                    employment_type = detail.get('employment_type', '')
                    department = detail.get('department', '')
                    posted_date = detail.get('posted_date', '')

                    experience_level = self._extract_experience(exp_text, description)
                    apply_url = f"{self.base_apply_url}{job_seq}"

                    jobs.append({
                        'external_id': self.generate_external_id(job_seq, self.company_name),
                        'company_name': self.company_name,
                        'title': title,
                        'description': description,
                        'location': location or 'India',
                        'city': location if location else '',
                        'state': '',
                        'country': 'India',
                        'employment_type': employment_type,
                        'department': department,
                        'apply_url': apply_url,
                        'posted_date': posted_date,
                        'job_function': department,
                        'experience_level': experience_level,
                        'salary_range': '',
                        'remote_type': '',
                        'status': 'active',
                    })
                except Exception as e:
                    logger.error(f"Error processing Axis job node: {str(e)}")
                    continue

                time.sleep(0.05)

            if len(job_nodes) < page_size:
                break

        logger.info(f"Successfully scraped {len(jobs)} total jobs from {self.company_name}")
        return jobs

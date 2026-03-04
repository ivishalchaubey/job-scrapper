# Scraper Project Rules & Best Practices

## Project Overview
Django-based job scraping backend. Scrapes India-based job listings from 300+ company career pages using platform-specific APIs and Selenium fallbacks. Each company has its own scraper file in `scrapers/`.

## Key Files
- `scrapers/registry.py` — Central registry: imports, SCRAPER_MAP, ALL_COMPANY_CHOICES
- `config/scraper.py` — Settings: SCRAPE_TIMEOUT, HEADLESS_MODE, MAX_PAGES_TO_SCRAPE, FETCH_FULL_JOB_DETAILS
- `core/logging.py` — Logger setup
- `company-list.xlsx` — Master list: Company Name, Career Page Link, Status (Done/Pending/Broken)
- `multipage-optimization-guide.md` — Pagination and speed optimization reference
- `scraper-test-results.md` — Test results history
- `FAILED_SCRAPERS.md` — Known broken scrapers with root causes

## Golden Rule: API First, Selenium Last
Always prefer API-based scrapers over Selenium. API scrapers are 5-10x faster, more reliable (80-92% pass rate vs 32% for generic Selenium), and don't require ChromeDriver.

**Platform preference order:**
1. Greenhouse API (most reliable, single GET, all jobs in one response)
2. Lever API (single GET, all jobs in one response)
3. Workday API (POST with pagination, very reliable)
4. Oracle HCM API (GET with pagination, very reliable)
5. SmartRecruiters API (GET, reliable)
6. Phenom API (GET with pagination)
7. DarwinBox v2 Selenium (decent reliability)
8. DarwinBox v1 Selenium (lower reliability)
9. PeopleStrong Selenium (moderate reliability)
10. Generic Selenium (last resort, 32% pass rate)

---

## Scraper File Conventions

### Naming
- File: `scrapers/{companyname}_scraper.py` (lowercase, no spaces, no hyphens)
- Class: `{CompanyName}Scraper` (PascalCase)
- Examples: `coinbase_scraper.py` -> `CoinbaseScraper`, `bajajfinserv_scraper.py` -> `BajajFinservScraper`

### Required Imports
```python
# API-based scrapers
import requests
import hashlib
from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE

# Selenium-based scrapers (add these)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
from datetime import datetime
from pathlib import Path
from config.scraper import HEADLESS_MODE, FETCH_FULL_JOB_DETAILS
```

### Required Class Structure
```python
class {CompanyName}Scraper:
    def __init__(self):
        self.company_name = '{Exact Company Name}'  # Must match xlsx
        self.url = '{careers_page_url}'
        self.api_url = '{api_endpoint}'  # If API-based

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        # Must accept max_pages parameter
        # Must return list of job dicts
        pass

    def parse_location(self, location_str):
        # Must return dict with city, state, country
        pass
```

### Required Job Data Fields
Every job dict MUST have all 17 fields:
```python
{
    'external_id': str,        # MD5 hash from generate_external_id()
    'company_name': str,       # self.company_name
    'title': str,              # Job title (MUST be actual job title, not page elements)
    'description': str,        # Job description (can be empty '')
    'location': str,           # Raw location string
    'city': str,               # Parsed city name
    'state': str,              # Parsed state name
    'country': str,            # Default 'India'
    'employment_type': str,    # Full Time, Part Time, Contract, Intern, or ''
    'department': str,         # Department/category or ''
    'apply_url': str,          # Direct apply link
    'posted_date': str,        # YYYY-MM-DD format or ''
    'job_function': str,       # Job function/family or ''
    'experience_level': str,   # Experience requirement or ''
    'salary_range': str,       # Salary info or ''
    'remote_type': str,        # On-site, Remote, Hybrid, or ''
    'status': 'active'         # Always 'active'
}
```

---

## Platform-Specific Templates

### 1. Greenhouse API
**When to use:** Company has `boards.greenhouse.io/{slug}` career page or uses Greenhouse ATS.
**API:** `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`
**Pagination:** None (returns all jobs in single response)
**India filter:** Client-side keyword matching on `location.name` field

```python
import requests
import hashlib
from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, MAX_PAGES_TO_SCRAPE

logger = setup_logger('{company}_scraper')

class {Company}Scraper:
    def __init__(self):
        self.company_name = '{Company Name}'
        self.url = 'https://boards.greenhouse.io/{slug}'
        self.api_url = 'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs'

    def generate_external_id(self, job_id, company):
        unique_string = f"{company}_{job_id}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
        all_jobs = []
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }
        india_keywords = [
            'India', 'Bangalore', 'Bengaluru', 'Mumbai', 'Delhi',
            'Hyderabad', 'Chennai', 'Pune', 'Gurugram', 'Gurgaon',
            'Noida', 'Kolkata', 'Ahmedabad', 'Jaipur', 'Kochi',
            'Thiruvananthapuram', 'Chandigarh', 'Lucknow', 'Indore'
        ]
        try:
            response = requests.get(self.api_url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            postings = data.get('jobs', [])
            for posting in postings:
                title = posting.get('title', '')
                if not title:
                    continue
                location_obj = posting.get('location', {})
                location = location_obj.get('name', '') if isinstance(location_obj, dict) else ''
                if not any(kw in location for kw in india_keywords):
                    continue
                job_id = str(posting.get('id', ''))
                if not job_id:
                    job_id = hashlib.md5(title.encode()).hexdigest()[:12]
                absolute_url = posting.get('absolute_url', '')
                date_str = posting.get('updated_at', '')
                posted_date = date_str[:10] if date_str else ''
                loc = self.parse_location(location)
                all_jobs.append({
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'description': '',
                    'location': location,
                    'city': loc.get('city', ''),
                    'state': loc.get('state', ''),
                    'country': loc.get('country', 'India'),
                    'employment_type': '',
                    'department': '',
                    'apply_url': absolute_url or self.url,
                    'posted_date': posted_date,
                    'job_function': '',
                    'experience_level': '',
                    'salary_range': '',
                    'remote_type': '',
                    'status': 'active'
                })
        except Exception as e:
            logger.error(f"Error: {str(e)}")
        return all_jobs

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1: result['city'] = parts[0]
        if len(parts) >= 2: result['state'] = parts[1]
        if len(parts) >= 3: result['country'] = parts[2]
        if 'India' in location_str: result['country'] = 'India'
        return result
```

### 2. Lever API
**When to use:** Company has `jobs.lever.co/{slug}` career page.
**API:** `GET https://api.lever.co/v0/postings/{slug}?mode=json`
**Pagination:** None (returns all jobs in single response)
**India filter:** Client-side keyword matching on `categories.location` + `categories.country` == 'IN'

Key fields mapping:
- `text` -> title
- `categories.location` -> location
- `categories.department` -> department
- `categories.team` -> job_function
- `categories.commitment` -> employment_type (Full-time, Part-time, Intern, Contract)
- `categories.allLocations` -> additional locations
- `hostedUrl` or `applyUrl` -> apply_url
- `createdAt` -> posted_date (Unix ms timestamp, divide by 1000)
- `id` -> job_id

### 3. Workday API
**When to use:** Company has `{tenant}.wd{N}.myworkdayjobs.com/{site}` career page.
**API:** `POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`
**Pagination:** Offset-limit (limit=20, offset increments)
**India filter:** API-level via `appliedFacets.Location_Country = ["c4f78be1a8f14da0ab49ce1162348a5e"]`

Key payload:
```python
payload = {
    "appliedFacets": {"Location_Country": ["c4f78be1a8f14da0ab49ce1162348a5e"]},
    "limit": 20,
    "offset": 0,
    "searchText": ""
}
```
India country code is always: `c4f78be1a8f14da0ab49ce1162348a5e`

Key response fields:
- `jobPostings[].title` -> title
- `jobPostings[].locationsText` -> location
- `jobPostings[].postedOn` -> posted_date
- `jobPostings[].bulletFields[]` -> employment_type, remote_type
- `jobPostings[].externalPath` -> job URL path (append to base_job_url)
- `total` -> total job count for pagination

### 4. Oracle HCM API
**When to use:** Company has `*.oraclecloud.com/hcmUI/CandidateExperience/en/sites/{site}/jobs`.
**API:** `GET https://{instance}.fa.{region}.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions`
**Pagination:** Offset-limit (page_size=25)
**India filter:** Via site number; some use locationId filter

Key finder params:
```python
finder = f'findReqs;siteNumber={site_number},facetsList=LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;CATEGORIES;ORGANIZATIONS;POSTING_DATES;FLEX_FIELDS,limit={page_size},offset={offset}'
```

Key response fields:
- `items[0].requisitionList[].Title` -> title
- `items[0].requisitionList[].PrimaryLocation` -> location
- `items[0].requisitionList[].Id` -> job_id
- `items[0].requisitionList[].PostedDate` -> posted_date
- `items[0].TotalJobsCount` -> total for pagination

### 5. DarwinBox v2 (Selenium)
**When to use:** URL pattern `{subdomain}.darwinbox.in/ms/candidatev2/main/careers/allJobs`
**Method:** Selenium JS extraction of job tiles
**Pagination:** None (single page scroll-load)

Key JS selectors:
- Job tiles: `div.job-tile`, `a[href*="jobDetails"]`
- Title: Inner text of link
- Location: Text containing India city/state names
- URL: href attribute

### 6. DarwinBox v1 (Selenium)
**When to use:** URL pattern `{subdomain}.darwinbox.in/ms/candidate/careers`
**Method:** Navigate to careers -> find allJobs link -> extract from allJobs page
**Pagination:** None

Key patterns:
- Must find allJobs link first: `a[href*="allJobs"], a[href*="openJobs"]`
- Job URLs match: `/ms/candidate/{hash}/careers/{jobhash}`
- or: `a[href*="jobDetails"]`

### 7. PeopleStrong (Selenium)
**When to use:** URL pattern `{subdomain}.peoplestrong.com/job/joblist`
**Method:** Selenium with "Load More" button pagination
**Pagination:** Button click loop up to max_pages

---

## Selenium Anti-Detection (Required for ALL Selenium Scrapers)

```python
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
        driver = webdriver.Chrome(options=chrome_options)
    except Exception:
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    })
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver
```

---

## Speed Optimization Rules (from multipage-optimization-guide.md)

### NEVER do:
- `time.sleep(15)` for initial page load — use `WebDriverWait` with 15s timeout
- 5 scrolls with `time.sleep(2)` each — one scroll with 1s sleep
- `time.sleep(5)` after pagination click — poll for content change (20 checks x 0.2s)
- `page_load_timeout` — causes crashes
- Redundant sleep after `_go_to_next_page()` — it already waits

### ALWAYS do:
- Smart waits: `WebDriverWait(driver, 15).until(EC.presence_of_element_located(...))`
- Quick scroll: scroll down (1s), scroll up (0.5s)
- Change detection for pagination: capture old content, click, poll for new content
- JS extraction (`execute_script`) over Selenium `find_elements` — faster and more reliable

### Target Speed:
| Metric | Bad | Good |
|--------|-----|------|
| Initial load | 27s | 3-5s |
| Per page | ~19s | ~3s |
| 30 pages | ~600s | ~90s |

---

## India Location Keywords (Standard Set)
Use this list for client-side India filtering:
```python
india_keywords = [
    'India', 'Bangalore', 'Bengaluru', 'Mumbai', 'Delhi',
    'Hyderabad', 'Chennai', 'Pune', 'Gurugram', 'Gurgaon',
    'Noida', 'Kolkata', 'Ahmedabad', 'Jaipur', 'Kochi',
    'Thiruvananthapuram', 'Chandigarh', 'Lucknow', 'Indore',
    'New Delhi', 'NCR', 'Haryana', 'Karnataka', 'Maharashtra',
    'Tamil Nadu', 'Telangana', 'Gujarat', 'Rajasthan',
    'Uttar Pradesh', 'West Bengal', 'Kerala'
]
```

---

## Registry Registration (scrapers/registry.py)

### Step 1: Add import (grouped by batch)
```python
# Batch N - Platform type (count)
from scrapers.{company}_scraper import {Company}Scraper
```

### Step 2: Add to SCRAPER_MAP
```python
'{company name lowercase}': {Company}Scraper,
# Add aliases if needed:
'{alternate name}': {Company}Scraper,
```

### Step 3: Add to ALL_COMPANY_CHOICES
```python
'{Display Name}',  # In the appropriate batch section
```

---

## Testing Requirements

### Every scraper MUST:
1. Return >0 jobs (exact count required, not just ">0")
2. Accept `max_pages` parameter
3. Return list of dicts with all 17 required fields
4. Have `title` be actual job titles (NOT page elements, nav links, filter labels, or language selectors)
5. Have `apply_url` be a valid URL to the job posting
6. **Multipage support verified** — paginated scrapers (Workday, Oracle HCM, Phenom, etc.) MUST return more jobs with `max_pages=2` than `max_pages=1` (unless total jobs < page size)

### Test command (basic):
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from scrapers.{company}_scraper import {Company}Scraper
s = {Company}Scraper()
jobs = s.scrape(max_pages=1)
print(f'Jobs: {len(jobs)}')
for j in jobs[:3]:
    print(f'  - {j[\"title\"]} | {j[\"location\"]}')
"
```

### Multipage test (REQUIRED for paginated scrapers):
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from scrapers.{company}_scraper import {Company}Scraper
s = {Company}Scraper()
j1 = s.scrape(max_pages=1)
j2 = s.scrape(max_pages=2)
j3 = s.scrape(max_pages=3)
print(f'max_pages=1: {len(j1)} jobs')
print(f'max_pages=2: {len(j2)} jobs')
print(f'max_pages=3: {len(j3)} jobs')
# For paginated scrapers: j2 > j1 (unless total < page_size)
# For single-call APIs (Greenhouse/Lever): j1 == j2 == j3
"
```

**Multipage verification rules:**
- **Workday API** (limit=20): `max_pages=1` → 20 jobs, `max_pages=2` → 40 jobs, `max_pages=3` → 60 jobs (capped by total)
- **Oracle HCM API** (page_size=25): `max_pages=1` → 25, `max_pages=2` → 50 (capped by total)
- **Greenhouse/Lever API**: Single call returns ALL jobs regardless of `max_pages` — this is correct behavior
- **Selenium paginated** (Phenom, PeopleStrong): More jobs with higher `max_pages`
- **If `max_pages=2` returns same count as `max_pages=1`** for a paginated scraper and total > page_size → pagination is BROKEN, must fix before committing

### India filtering verification:
- Watch for **"Indiana" (US state)** false positives when filtering for "India"
- Check sample job locations are actually in India, not just containing an India keyword substring
- For Lever API: check `allLocations` field — jobs may list India as one of many locations

### When a scraper returns 0 jobs:
1. Check if the API/URL is still accessible
2. Check if the company still has India job postings
3. If the platform is inaccessible, replace with a company on a known-working platform
4. Do NOT commit scrapers that return 0 jobs

---

## Common Failure Patterns (Avoid These)

1. **Page elements as job titles** — Generic selectors like `div[class*="job"]` catch nav links, buttons, headers. Fix: use platform-specific selectors or JS extraction.
2. **Non-India jobs** — Location filter not applied. Fix: always filter at API level when possible, or client-side with india_keywords.
3. **Language selectors as titles** — Extracting "English", "Deutsch". Fix: title validation, minimum length checks.
4. **Filter labels as titles** — "ALL JOBS (351)", "19 Results". Fix: skip entries matching count patterns.
5. **Blind sleeps** — `time.sleep(15)` everywhere. Fix: use WebDriverWait + smart polling.
6. **Wrong URL** — Career page moved or restructured. Fix: verify URL returns actual job listings before building scraper.

---

## Batch Building Workflow

When building a batch of scrapers:

1. **Select companies** from `company-list.xlsx` (Pending status)
2. **Identify platform** from career URL — prioritize API platforms
3. **Test API** before building — verify it returns India jobs with exact count
4. **Build scraper** from closest template (see Platform-Specific Templates above)
5. **Test scraper** — must return >0 jobs with exact count
6. **Register in registry.py** — import, SCRAPER_MAP, ALL_COMPANY_CHOICES
7. **Update company-list.xlsx** — change Status to Done
8. **If scraper returns 0 jobs** — replace company, do NOT force broken scrapers
9. **Commit** only after ALL scrapers in batch pass

---

## Workday India Country Code
The Workday API uses a fixed country code for India across all tenants:
```
c4f78be1a8f14da0ab49ce1162348a5e
```

## Greenhouse API Validation
Before building a Greenhouse scraper, test the slug:
```bash
curl -s "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('jobs',[])),'total jobs')"
```

## Lever API Validation
Before building a Lever scraper, test the slug:
```bash
curl -s "https://api.lever.co/v0/postings/{slug}?mode=json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d),'total jobs')"
```

---

## Do NOT:
- Change working URLs that are tested and confirmed
- Set `page_load_timeout` on Selenium drivers (causes crashes)
- Use `find_elements` when JS `execute_script` works (slower, less reliable)
- Commit scrapers returning 0 jobs
- Skip the `max_pages` parameter
- Use inheritance for scrapers (all are standalone classes)
- Add unnecessary dependencies
- Commit without testing all scrapers in the batch
- Over-engineer — keep scrapers simple and focused on extraction

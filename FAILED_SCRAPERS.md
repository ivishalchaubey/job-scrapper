# Failed Scrapers

Scrapers listed below are currently non-functional due to issues that cannot be resolved by fixing scraping logic alone.

---

## URL Issues (Need URL Updates)

### Starbucks
- **File:** `src/scrapers/starbucks_scraper.py`
- **Current URL:** `https://www.starbucks.in/careers`
- **Issue:** Returns HTTP 404. The Starbucks India careers page has moved.
- **Suggested URL:** `https://careers.starbucks.in` (Taleo platform, 283+ jobs available)

### Shoppers Stop
- **File:** `src/scrapers/shoppersstop_scraper.py`
- **Current URL:** `https://www.shoppersstop.com/careers`
- **Issue:** Points to the e-commerce storefront which has no career listings.
- **Suggested URL:** `https://career.shoppersstop.com` or `https://ss-people.darwinbox.in/ms/candidate/careers` (DarwinBox platform)

### Maruti Suzuki
- **File:** `src/scrapers/marutisuzuki_scraper.py`
- **Current URL:** `https://www.marutisuzuki.com/corporate/career/current-openings`
- **Issue:** Informational page only. No individual job listings or structured data to scrape.
- **Suggested URL:** `https://maruti.app.param.ai/jobs/` (Param.ai platform with actual job postings)

### Qualcomm
- **File:** `src/scrapers/qualcomm_scraper.py`
- **Current URL:** `https://qualcomm.wd5.myworkdayjobs.com/External?locationCountry=...`
- **Issue:** Workday API returns HTTP 422 on all payload formats. Qualcomm may have migrated from `wd5` to `wd12` subdomain.
- **Suggested URL:** Try `https://qualcomm.wd12.myworkdayjobs.com/External?locationCountry=...`

---

## Anti-Bot Protection (Blocked by WAF)

### Tesla
- **File:** `src/scrapers/tesla_scraper.py`
- **Current URL:** `https://www.tesla.com/careers/search/?country=IN`
- **Issue:** Akamai Bot Manager blocks all headless Chrome access. The scraper already has the most sophisticated anti-detection in the project (stealth JS injection, 7 API patterns, full CDP hooks) but Akamai still detects and blocks it.
- **Resolution:** Requires residential proxy service or non-headless browser automation (Playwright with real browser profile).

---

## Network/Infrastructure Issues

### Adani Group
- **File:** `src/scrapers/adanigroup_scraper.py`
- **Current URL:** `https://careers.adanigroup.com/`
- **Issue:** `ERR_CONNECTION_TIMED_OUT` - Server does not respond. Network-level issue, not a code bug. May be geo-restricted or temporarily down.

### Axis Bank
- **File:** `src/scrapers/axisbank_scraper.py`
- **Current URL:** `https://axisbank.skillate.com/jobs`
- **Issue:** `ERR_CONNECTION_TIMED_OUT` - Skillate portal unreachable. The hosting platform may be experiencing issues.

### HDFC Bank
- **File:** `src/scrapers/hdfcbank_scraper.py`
- **Current URL:** `https://hdfcbank.skillate.com/jobs`
- **Issue:** `ERR_CONNECTION_TIMED_OUT` - Skillate portal unreachable. Same platform as Axis Bank.

### TCS
- **File:** `src/scrapers/tcs_scraper.py`
- **Current URL:** `https://ibegin.tcs.com/iBegin/jobs/search`
- **Issue:** DNS intermittently down. The scraper already has a fallback URL (`https://ibegin.tcsapps.com/candidate/`). Works when the domain is accessible.

---

## Genuinely Zero Open Positions

These scrapers are fully functional but return 0 jobs because the company has no open positions listed on their career portal at the time of testing (Feb 2026). They will automatically pick up jobs when the company posts new openings.

### Tata Play
- **File:** `src/scrapers/tataplay_scraper.py`
- **Platform:** Oracle HCM (REST API)
- **URL:** `https://hcoe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs`
- **Issue:** API responds successfully with `TotalJobsCount: 0`. No open requisitions posted.

### Go Digit Insurance
- **File:** `src/scrapers/godigit_scraper.py`
- **Platform:** DarwinBox v2
- **URL:** `https://godigit.darwinbox.in/ms/candidatev2/main/careers/allJobs`
- **Issue:** Page loads correctly and shows "0 Open jobs available". No positions listed.

### TVS Motor Company
- **File:** `src/scrapers/tvsmotor_scraper.py`
- **Platform:** DarwinBox v2
- **URL:** `https://tvsmsampark.darwinbox.in/ms/candidatev2/main/careers/allJobs`
- **Issue:** Page loads correctly and shows "0 Open jobs available". No positions listed.

### GMMCO
- **File:** `src/scrapers/gmmco_scraper.py`
- **Platform:** DarwinBox v1
- **URL:** `https://gmmco.darwinbox.in/ms/candidate/careers`
- **Issue:** Page loads correctly and shows "No jobs found". No positions listed.

### Star Health Insurance
- **File:** `src/scrapers/starhealth_scraper.py`
- **Platform:** PeopleStrong
- **URL:** `https://starhealthcareers.peoplestrong.com/job/joblist`
- **Issue:** Page loads correctly and shows "No Jobs Available". No positions listed.

### United Breweries (Heineken India)
- **File:** `src/scrapers/unitedbreweries_scraper.py`
- **Platform:** iCIMS/SuccessFactors (Heineken global careers)
- **URL:** `https://careers.theheinekencompany.com/India/search/?createNewAlert=false&q=&locationsearch=India`
- **Issue:** Scraper works correctly including age gate bypass (fills DOB inputs and clicks Enter). Page loads and shows "There are currently no open positions matching India". Heineken has 0 India openings at this time.

### DBS Bank
- **File:** `src/scrapers/dbsbank_scraper.py`
- **Platform:** Custom DBS careers portal with category-based navigation
- **URL:** `https://www.dbs.com/careers/jobs.page?market=India`
- **Issue:** Intermittent - the scraper navigates category pages (`job-listing.page?category=...&market=India`) and clicks "Load More" buttons to extract jobs from `div.job` cards. Returns 228 jobs when the site loads fully, but sometimes returns 0 when category links fail to render or the page loads slowly. Likely a timing/network sensitivity issue on DBS's end.

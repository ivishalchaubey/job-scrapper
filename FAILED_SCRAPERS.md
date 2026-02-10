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

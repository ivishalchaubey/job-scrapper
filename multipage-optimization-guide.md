# Multipage Scraper Optimization Guide

## Overview
Reference for fixing scrapers that return 0 jobs on pagination or run too slowly. Apply these patterns to all scrapers needing multipage support and speed fixes.

---

## Problem 1: Pagination Not Working (0 jobs after page 1)

### Root Cause
Wrong CSS selectors in `_go_to_next_page()`. The selectors in the code don't match actual DOM elements on the live page.

### Fix Process

1. **Discover actual selectors** — Create a debug script that loads the page and dumps real DOM attributes:
```python
# Debug script pattern (_debug_<company>.py) — DELETE after use
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--no-sandbox')
opts.add_argument('--user-agent=AppleWebKit/537.36')
driver = webdriver.Chrome(options=opts)
driver.get(SCRAPER_URL)
time.sleep(10)

# Dump pagination elements
pagination = driver.execute_script("""
    var results = [];
    var els = document.querySelectorAll('a[href*="page"], button[class*="next"], [data-ph-at-id*="pagination"], [aria-label*="Next"], .pagination a, .pager a');
    els.forEach(el => results.push({
        tag: el.tagName, text: el.innerText.trim().substring(0,50),
        classes: el.className, href: el.href||'',
        dataAttrs: Object.keys(el.dataset).map(k => k+'='+el.dataset[k]).join(', '),
        displayed: el.offsetParent !== null
    }));
    return results;
""")
print("PAGINATION ELEMENTS:", pagination)

# Dump job listing elements
jobs = driver.execute_script("""
    var results = [];
    var els = document.querySelectorAll('[data-ph-at-id*="job"], [class*="job-card"], [class*="job-listing"], [class*="search-result"], li[class*="job"], tr[class*="data"]');
    els.forEach(el => results.push({
        tag: el.tagName, classes: el.className,
        dataAttrs: Object.keys(el.dataset).map(k => k+'='+el.dataset[k]).join(', '),
        textPreview: el.innerText.trim().substring(0,80)
    }));
    return results;
""")
print("JOB ELEMENTS:", jobs[:3])
driver.quit()
```

2. **Update selectors** in the scraper based on debug output
3. **Test with `max_pages=3`** — should get 3× single page job count
4. **Delete the debug script**

### Selector Priority Order (try first match)
```python
# Pagination next button — try these in order:
(By.CSS_SELECTOR, 'a[data-ph-at-id="pagination-next-link"]'),  # Phenom
(By.CSS_SELECTOR, 'a.next-btn'),                                 # Phenom fallback
(By.CSS_SELECTOR, 'button[data-ph-at-id="load-more-jobs-button"]'),
(By.CSS_SELECTOR, 'a[aria-label="Next"]'),
(By.CSS_SELECTOR, 'button[aria-label="Next"]'),
(By.XPATH, '//a[contains(text(), "Next")]'),
```

---

## Problem 2: Scraping Too Slow (20s+ per page)

### Root Cause
Blind `time.sleep()` calls everywhere — initial load, scrolling, pagination clicks, extract loops. These add up to ~20s per page.

### Fix: Replace Blind Sleeps with Smart Waits

#### Initial Page Load — Use WebDriverWait instead of sleep(15)
```python
# BEFORE (slow):
driver.get(self.url)
time.sleep(15)

# AFTER (fast — returns as soon as content appears):
driver.get(self.url)
try:
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-ph-at-id="jobs-list-item"]'))
    )
except:
    time.sleep(5)  # Fallback only if selector unknown
```

#### Scrolling — One quick scroll instead of 5 slow ones
```python
# BEFORE (slow — 5 scrolls × 2s = 10s):
for _ in range(5):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
driver.execute_script("window.scrollTo(0, 0);")
time.sleep(2)

# AFTER (fast — 1.5s total):
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(1)
driver.execute_script("window.scrollTo(0, 0);")
time.sleep(0.5)
```

#### Pagination Click — Poll for page change instead of sleep(5)
```python
# BEFORE (slow — always waits 5s):
driver.execute_script("arguments[0].click();", btn)
time.sleep(5)

# AFTER (fast — detects actual page change, usually <1s):
# Capture first job text BEFORE click
old_first = driver.execute_script("""
    var card = document.querySelector('[data-ph-at-id="jobs-list-item"]');
    return card ? card.innerText.substring(0, 50) : '';
""")

driver.execute_script("arguments[0].click();", btn)

# Poll until content changes (max 4s, usually ~0.5s)
for _ in range(20):
    time.sleep(0.2)
    new_first = driver.execute_script("""
        var card = document.querySelector('[data-ph-at-id="jobs-list-item"]');
        return card ? card.innerText.substring(0, 50) : '';
    """)
    if new_first and new_first != old_first:
        break
time.sleep(0.5)  # Brief settle after change detected
```

#### Job Extraction Scrolling — Minimal scroll
```python
# BEFORE (slow — 3 scrolls × 2s + 1s = 7s):
for _ in range(3):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
driver.execute_script("window.scrollTo(0, 0);")
time.sleep(1)

# AFTER (fast — 0.8s):
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(0.5)
driver.execute_script("window.scrollTo(0, 0);")
time.sleep(0.3)
```

#### Main Loop — Remove redundant sleep after _go_to_next_page
```python
# BEFORE (redundant — _go_to_next_page already waits):
if not self._go_to_next_page(driver):
    break
time.sleep(5)  # DELETE THIS — pagination handler already waits

# AFTER:
if page < max_pages - 1:
    if not self._go_to_next_page(driver):
        break
# No extra sleep needed
```

### Speed Results
| Metric | Before | After |
|--------|--------|-------|
| Initial load | 27s | 3-5s |
| Per page | ~19s | ~3s |
| 30 pages total | ~600s (10 min) | ~90s (1.5 min) |

---

## Complete Optimized Scraper Template

```python
def scrape(self, max_pages=MAX_PAGES_TO_SCRAPE):
    driver = None
    all_jobs = []
    try:
        driver = self.setup_driver()
        driver.get(self.url)

        # Smart wait for content (NOT blind sleep)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'JOB_CARD_SELECTOR'))
            )
        except:
            time.sleep(5)

        # Quick scroll for lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)

        for page in range(max_pages):
            page_jobs = self._extract_jobs(driver)
            if not page_jobs:
                break
            all_jobs.extend(page_jobs)

            if page < max_pages - 1:
                if not self._go_to_next_page(driver):
                    break
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        if driver:
            driver.quit()
    return all_jobs

def _extract_jobs(self, driver):
    # Single quick scroll
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.5)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.3)

    # Use JS extraction (faster than Selenium find_elements)
    js_jobs = driver.execute_script("""...""")
    # ... process js_jobs ...

def _go_to_next_page(self, driver):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.5)

    # Capture current state for change detection
    old_first = driver.execute_script("""
        var card = document.querySelector('JOB_CARD_SELECTOR');
        return card ? card.innerText.substring(0, 50) : '';
    """)

    # Try selectors
    for sel_type, sel_val in PAGINATION_SELECTORS:
        try:
            btn = driver.find_element(sel_type, sel_val)
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                # Poll for change
                for _ in range(20):
                    time.sleep(0.2)
                    new_first = driver.execute_script("""
                        var card = document.querySelector('JOB_CARD_SELECTOR');
                        return card ? card.innerText.substring(0, 50) : '';
                    """)
                    if new_first and new_first != old_first:
                        break
                time.sleep(0.5)
                return True
        except:
            continue
    return False
```

---

## Rules
1. **NEVER change URLs** — all URLs are tested and working
2. **NEVER set page_load_timeout** — causes crashes
3. **Use short UA** in chrome_options + full UA via CDP
4. **Always use JS extraction** (`execute_script`) over Selenium `find_elements` — faster and more reliable
5. **Always clean up debug scripts** after fixing
6. **Test with max_pages=3** to verify pagination works (should get 3× page 1 count)
7. **Anti-detection**: short UA + CDP override + `navigator.webdriver=undefined` + `useAutomationExtension:False` + `excludeSwitches:['enable-logging','enable-automation']`

## Platform-Specific Notes
- **Phenom** (ABB, PepsiCo): `data-ph-at-id="jobs-list-item"`, `data-ph-at-id="pagination-next-link"`, `a.next-btn`
- **Workday**: POST API, no pagination selectors needed
- **SuccessFactors**: `tr.data-row`, standard pagination
- **Eightfold AI**: `div[class*='position-card']`, API-based
- **Skillate** (Axis, HDFC): `div.job-card`

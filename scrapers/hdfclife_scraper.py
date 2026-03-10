from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib
import time
import json
import os
from pathlib import Path


from core.logging import setup_logger
from config.scraper import SCRAPE_TIMEOUT, HEADLESS_MODE, FETCH_FULL_JOB_DETAILS, MAX_PAGES_TO_SCRAPE

logger = setup_logger('hdfclife_scraper')

CHROMEDRIVER_PATH = '/Users/ivishalchaubey/.wdm/drivers/chromedriver/mac64/144.0.7559.133_fresh/chromedriver-mac-arm64/chromedriver'

# Hardcoded token and IV used by the HDFC Life careers portal JS.
# These values are embedded in the public JS at /hdfc-careers/js/custom.js
HDFC_API_TOKEN = (
    "ob1VbQlyRRaKms81nzKB91hjb4QvmP-5f7jSdTgmOIzNvWh5-eLFykYnBx7_1flXG7MGYXSwcVKplNypX26VC1"
    "9wHmYI4RZFD9uiUfjj3pyUOG-YX7-TkGzIUTpMEE2Bm9YDYBpNRzI6FGns0csd0t1XU7hoVuwazD_NEMJiv2f6"
    "8HaM7zf_YKHIJHamig2p7jWtBnaUSvm5UZi3wJSw_B7A6qiIFKFYstdxQJCTv7G1jyTmBIWWi23rQ8"
)
HDFC_API_IV = "vS7YzoFtgUU1Ovf"
HDFC_API_URL = "https://mist.api-hdfclife.com/career-portal/get-open-requisition"

# AES-GCM Encrypter class (JS) that mirrors the site's own Encrypter.
# Injected into the browser context so we can encrypt/decrypt payloads.
ENCRYPTER_JS = """
class __HdfcEncrypter {
    constructor(encryptionkey, iv) {
        this.algorithm = "AES-GCM";
        this.key = this.getKey(encryptionkey);
        this.iv = this.getIV(iv);
    }
    getKey(encryptionKey) {
        return crypto.subtle.importKey(
            "raw",
            this.stringToArrayBuffer(encryptionKey.substr(0, 32)),
            { name: this.algorithm },
            false,
            ["encrypt", "decrypt"]
        );
    }
    getIV(iv) { return this.stringToArrayBuffer(atob(iv)); }
    stringToArrayBuffer(str) {
        const buf = new ArrayBuffer(str.length);
        const bufView = new Uint8Array(buf);
        for (let i = 0; i < str.length; i++) { bufView[i] = str.charCodeAt(i); }
        return buf;
    }
    async encrypt(data) {
        const key = await this.key;
        const iv = this.iv;
        const encodedData = new TextEncoder().encode(JSON.stringify(data));
        return crypto.subtle.encrypt({ name: this.algorithm, iv }, key, encodedData)
            .then(encryptedData => {
                const arr = new Uint8Array(encryptedData);
                const str = String.fromCharCode.apply(null, arr);
                return btoa(str);
            });
    }
    async decrypt(encryptedData) {
        const key = await this.key;
        const iv = this.iv;
        const decodedData = atob(encryptedData);
        const arr = new Uint8Array(decodedData.length);
        for (let i = 0; i < decodedData.length; i++) { arr[i] = decodedData.charCodeAt(i); }
        return crypto.subtle.decrypt({ name: this.algorithm, iv }, key, arr)
            .then(decryptedData => {
                return JSON.parse(new TextDecoder().decode(decryptedData));
            });
    }
}
"""


class HDFCLifeScraper:
    def __init__(self):
        self.company_name = "HDFC Life"
        self.url = "https://www.hdfclife.com/hdfc-careers/find-your-fit.html?jobRole=Sales%20&location=&reqId=undefined"
        self.base_url = 'https://www.hdfclife.com'

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
        except Exception as e:
            logger.warning(f"Auto-detect failed: {str(e)}, trying explicit path")
            service = Service(CHROMEDRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
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
            # Load the find-your-fit page with a jobRole param to trigger JS loading.
            # We use jobRole=Sales to get the page into a state where jQuery and
            # crypto.subtle are available, but we call the API ourselves afterwards.
            fit_url = f"{self.url.rstrip('/')}/find-your-fit.html?jobRole=Sales"
            logger.info(f"Starting {self.company_name} scraping from {fit_url}")
            driver.get(fit_url)

            # Wait for jQuery and crypto to be ready
            for attempt in range(12):
                ready = driver.execute_script(
                    "return (typeof $ !== 'undefined' && typeof crypto !== 'undefined' "
                    "&& typeof crypto.subtle !== 'undefined');"
                )
                if ready:
                    logger.info(f"Page JS context ready after {(attempt + 1) * 2}s")
                    break
                time.sleep(2)
            else:
                logger.warning("jQuery/crypto not available after waiting; attempting API call anyway")

            # Call the encrypted API via Selenium's JS context.
            # The request body matches what the site's own JS sends.
            all_jobs = self._call_api(driver)
            logger.info(f"Total unique jobs scraped: {len(all_jobs)}")

        except Exception as e:
            logger.error(f"Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
        return all_jobs

    def _call_api(self, driver):
        """Call the HDFC Life encrypted API and return parsed job list."""
        jobs = []

        # Build the JS that encrypts the request, calls the API, decrypts the
        # response, and returns the structured job data back to Python.
        js_code = """
        var callback = arguments[arguments.length - 1];
        try {
            // Define Encrypter inline (execute_async_script has its own scope)
            class __Enc {
                constructor(ek, iv) {
                    this.algorithm = "AES-GCM";
                    this.key = this._getKey(ek);
                    this.iv = this._getIV(iv);
                }
                _s2ab(str) {
                    var buf = new ArrayBuffer(str.length);
                    var v = new Uint8Array(buf);
                    for (var i = 0; i < str.length; i++) v[i] = str.charCodeAt(i);
                    return buf;
                }
                _getKey(ek) {
                    return crypto.subtle.importKey("raw", this._s2ab(ek.substr(0,32)),
                        {name: this.algorithm}, false, ["encrypt","decrypt"]);
                }
                _getIV(iv) { return this._s2ab(atob(iv)); }
                async encrypt(data) {
                    var key = await this.key;
                    var ed = new TextEncoder().encode(JSON.stringify(data));
                    var enc = await crypto.subtle.encrypt({name:this.algorithm,iv:this.iv},key,ed);
                    var arr = new Uint8Array(enc);
                    var s = String.fromCharCode.apply(null, arr);
                    return btoa(s);
                }
                async decrypt(encData) {
                    var key = await this.key;
                    var d = atob(encData);
                    var arr = new Uint8Array(d.length);
                    for (var i=0;i<d.length;i++) arr[i]=d.charCodeAt(i);
                    var dec = await crypto.subtle.decrypt({name:this.algorithm,iv:this.iv},key,arr);
                    return JSON.parse(new TextDecoder().decode(dec));
                }
            }

            var token = "%s";
            var iv = "%s";
            var apiUrl = "%s";

            var encrypter = new __Enc(token.substring(0, 32), iv);

            var reqBody = {
                "jobRole": "All",
                "functionParam": [],
                "locationParam": [],
                "dob": "",
                "totalWorkExpParam": "",
                "totalSalesExpParam": "",
                "totalBFSIExp": "",
                "qualification": "",
                "living": ""
            };

            encrypter.encrypt(reqBody).then(function(encryptedPayload) {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', apiUrl, true);
                xhr.setRequestHeader('Content-Type', 'application/json; charset=utf-8');
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        try {
                            var response = JSON.parse(xhr.responseText);
                            if (response && response.data) {
                                var decrypter = new __Enc(
                                    response.data.token.substring(0, 32),
                                    response.data.iv
                                );
                                decrypter.decrypt(response.data.payload).then(function(decrypted) {
                                    // Extract all jobs from all role groups
                                    var allJobs = [];
                                    if (decrypted.results && decrypted.results.results) {
                                        decrypted.results.results.forEach(function(roleGroup) {
                                            if (roleGroup.REQUISITION && roleGroup.REQUISITION.results) {
                                                roleGroup.REQUISITION.results.forEach(function(job) {
                                                    allJobs.push({
                                                        jobRole: roleGroup.JOB_ROLE || '',
                                                        reqId: job.REQID || '',
                                                        designation: job.DESIGNATION || '',
                                                        city: job.CITY || '',
                                                        locName: job.LOC_NAME || '',
                                                        deptName: job.DEPT_NAME || '',
                                                        experience: job.EXPERIENCE || '',
                                                        salary: job.SALARY || '',
                                                        band: job.BAND || '',
                                                        jobCode: job.JOB_CODE || '',
                                                        jobCategory: job.JOBCATEGORY || '',
                                                        noOpening: job.NO_OPENING || ''
                                                    });
                                                });
                                            }
                                        });
                                    }
                                    callback(JSON.stringify({success: true, jobs: allJobs}));
                                }).catch(function(err) {
                                    callback(JSON.stringify({success: false, error: 'decrypt: ' + err}));
                                });
                            } else {
                                callback(JSON.stringify({success: false, error: 'no data field', raw: xhr.responseText.substring(0, 200)}));
                            }
                        } catch(e) {
                            callback(JSON.stringify({success: false, error: 'parse: ' + e.message}));
                        }
                    } else {
                        callback(JSON.stringify({success: false, error: 'http ' + xhr.status}));
                    }
                };
                xhr.onerror = function() {
                    callback(JSON.stringify({success: false, error: 'network error'}));
                };
                xhr.send(JSON.stringify({
                    token: token,
                    iv: iv,
                    payload: encryptedPayload
                }));
            }).catch(function(err) {
                callback(JSON.stringify({success: false, error: 'encrypt: ' + err}));
            });
        } catch(e) {
            callback(JSON.stringify({success: false, error: 'js: ' + e.message}));
        }
        """ % (HDFC_API_TOKEN, HDFC_API_IV, HDFC_API_URL)

        try:
            # execute_async_script waits for the callback to fire
            driver.set_script_timeout(60)
            raw = driver.execute_async_script(js_code)
            result = json.loads(raw)

            if not result.get('success'):
                logger.error(f"API call failed: {result.get('error', 'unknown')}")
                return jobs

            api_jobs = result.get('jobs', [])
            logger.info(f"API returned {len(api_jobs)} jobs")

            seen_ids = set()
            for jdata in api_jobs:
                req_id = jdata.get('reqId', '').strip()
                designation = jdata.get('designation', '').strip()
                city = jdata.get('city', '').strip()
                loc_name = jdata.get('locName', '').strip()
                dept_name = jdata.get('deptName', '').strip()
                experience = jdata.get('experience', '').strip()
                salary = jdata.get('salary', '').strip()
                job_role = jdata.get('jobRole', '').strip()

                title = designation if designation else job_role
                if not title or len(title) < 3:
                    continue

                dedup_key = req_id if req_id else f"{title}_{city}"
                if dedup_key in seen_ids:
                    continue
                seen_ids.add(dedup_key)

                location = city
                if loc_name and loc_name != city:
                    location = loc_name

                apply_url = (
                    f"{self.url.rstrip('/')}/find-your-fit.html?jobRole={job_role}&reqId={req_id}"
                    if req_id else self.url
                )

                job_id = req_id if req_id else hashlib.md5(title.encode()).hexdigest()[:12]
                loc_data = self.parse_location(location)

                jobs.append({
                    'external_id': self.generate_external_id(job_id, self.company_name),
                    'company_name': self.company_name,
                    'title': title,
                    'apply_url': apply_url,
                    'location': location,
                    'department': dept_name,
                    'employment_type': '',
                    'description': '',
                    'posted_date': '',
                    'city': loc_data.get('city', ''),
                    'state': loc_data.get('state', ''),
                    'country': loc_data.get('country', 'India'),
                    'job_function': dept_name or job_role,
                    'experience_level': experience,
                    'salary_range': salary,
                    'remote_type': '',
                    'status': 'active',
                })

            logger.info(f"Parsed {len(jobs)} unique jobs from API response")

        except Exception as e:
            logger.error(f"Error calling HDFC Life API: {str(e)}")

        return jobs

    def _go_to_next_page(self, driver):
        # The API returns all jobs at once (no pagination), so this is unused.
        return False

    def parse_location(self, location_str):
        result = {'city': '', 'state': '', 'country': 'India'}
        if not location_str:
            return result
        parts = [p.strip() for p in location_str.split(',')]
        if len(parts) >= 1:
            result['city'] = parts[0]
        if len(parts) >= 3:
            result['state'] = parts[1]
            result['country'] = parts[2]
        elif len(parts) == 2:
            result['country'] = parts[1]
        if 'India' in location_str:
            result['country'] = 'India'
        return result


if __name__ == "__main__":
    scraper = HDFCLifeScraper()
    jobs = scraper.scrape()
    print(f"\nTotal jobs found: {len(jobs)}")
    for job in jobs[:20]:
        print(f"- {job['title']} | {job['location']} | {job['department']} | {job['salary_range']}")
    if len(jobs) > 20:
        print(f"... and {len(jobs) - 20} more")

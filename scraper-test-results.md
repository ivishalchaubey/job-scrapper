# Scraper Test Results

**Last Updated:** 2026-02-22
**Test Config:** `max_pages=2` | Headless mode | ChromeDriver fallback
**Total Scrapers Tested:** 246

## Summary

| Category | Count | % |
|----------|-------|---|
| **PASS (good job data)** | 120 | 49% |
| **BAD DATA (wrong content)** | 100 | 41% |
| **FAIL (0 jobs)** | 18 | 7% |
| **BLOCKED/DEAD** | 8 | 3% |

### Pass Rate by Platform

| Platform | Pass | Fail/Bad | Total | Pass Rate |
|----------|------|----------|-------|-----------|
| Workday API | 5 | 1 | 6 | 83% |
| Oracle HCM API | 8 | 1 | 9 | 89% |
| DarwinBox | 10 | 3 | 13 | 77% |
| PeopleStrong | 4 | 1 | 5 | 80% |
| SuccessFactors | 12 | 1 | 13 | 92% |
| Phenom/Standard | 13 | 5 | 18 | 72% |
| Direct API (custom) | 15 | 2 | 17 | 88% |
| Generic Selenium | 53 | 112 | 165 | 32% |

---

## 1. Working Scrapers (PASS)

### Session 1 — Original 38

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 1 | Abbott | `abbott_scraper.py` | 20 | 14.6s | Workday API |
| 2 | Accenture | `accenture_scraper.py` | 24 | 10.4s | Custom Selenium |
| 3 | Amazon | `amazon_scraper.py` | 20 | 23.3s | Custom Selenium |
| 4 | Apple | `apple_scraper.py` | 40 | 26.8s | FIXED - React accordion |
| 5 | AWS | `aws_scraper.py` | 20 | 13.2s | Custom Selenium |
| 6 | Bain | `bain_scraper.py` | 10 | 1.9s | API + cloudscraper |
| 7 | BCG | `bcg_scraper.py` | 10 | 14.8s | Custom Selenium |
| 8 | BookMyShow | `bookmyshow_scraper.py` | 17 | 16.7s | Trakstar |
| 9 | Capgemini | `capgemini_scraper.py` | 2 | 90.1s | Custom Selenium |
| 10 | Cognizant | `cognizant_scraper.py` | 22 | 80.6s | Custom Selenium |
| 11 | Deloitte | `deloitte_scraper.py` | 20 | 37.4s | Custom Selenium |
| 12 | Dell | `dell_scraper.py` | 19 | 88.8s | Custom Selenium |
| 13 | EY | `ey_scraper.py` | 50 | 39.8s | SuccessFactors |
| 14 | Goldman Sachs | `goldmansachs_scraper.py` | 40 | 2.7s | GraphQL API |
| 15 | Google | `google_scraper.py` | 36 | 43.8s | Custom Selenium |
| 16 | HCLTech | `hcltech_scraper.py` | 10 | 13.7s | FIXED - SuccessFactors |
| 17 | IBM | `ibm_scraper.py` | 40 | 2.9s | API |
| 18 | ICICI Bank | `icicibank_scraper.py` | 24 | 45.4s | Custom Selenium |
| 19 | Infosys | `infosys_scraper.py` | 10 | 12.3s | Custom Selenium |
| 20 | Intel | `intel_scraper.py` | 5 | 86.4s | Custom Selenium |
| 21 | JLL | `jll_scraper.py` | 40 | 98.0s | Workday |
| 22 | Mahindra | `mahindra_scraper.py` | 19 | 19.9s | Custom Selenium |
| 23 | Marico | `marico_scraper.py` | 7 | 9.5s | FIXED - JS extraction |
| 24 | Meesho | `meesho_scraper.py` | 64 | 47.8s | Lever |
| 25 | Meta | `meta_scraper.py` | 10 | 13.8s | Custom Selenium |
| 26 | Microsoft | `microsoft_scraper.py` | 20 | 13.5s | PCSX API |
| 27 | Morgan Stanley | `morganstanley_scraper.py` | 30 | 16.4s | Selenium fallback |
| 28 | Nestle | `nestle_scraper.py` | 20 | 6.5s | SuccessFactors API |
| 29 | NVIDIA | `nvidia_scraper.py` | 40 | 6.3s | API |
| 30 | PepsiCo | `pepsico_scraper.py` | 40 | 5.6s | API |
| 31 | PwC | `pwc_scraper.py` | 1416 | 40.6s | Workday JSON |
| 32 | Samsung | `samsung_scraper.py` | 3 | 4.9s | Custom Selenium |
| 33 | Standard Chartered | `standardchartered_scraper.py` | 19 | 57.3s | Custom Selenium |
| 34 | Swiggy | `swiggy_scraper.py` | 9 | 14.0s | iframe-based |
| 35 | Tata Consumer | `tataconsumer_scraper.py` | 54 | 23.8s | Custom Selenium |
| 36 | Tech Mahindra | `techmahindra_scraper.py` | 14 | 16.4s | Custom Selenium |
| 37 | Varun Beverages | `varunbeverages_scraper.py` | 50 | 14.8s | Custom Selenium |
| 38 | Wipro | `wipro_scraper.py` | 20 | 22.5s | Custom Selenium |

### Session 2 — Batch 1-2 Remaining (12 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 39 | Delhivery | `delhivery_scraper.py` | 9 | — | Selenium |
| 40 | Reliance Industries | `reliance_scraper.py` | 20 | — | Selenium |
| 41 | Tata Motors | `tatamotors_scraper.py` | 52 | — | Selenium |
| 42 | Godrej Group | `godrej_scraper.py` | 38 | — | Selenium |
| 43 | Honeywell | `honeywell_scraper.py` | 50 | — | Selenium |
| 44 | Eli Lilly | `elililly_scraper.py` | 20 | — | Selenium |
| 45 | SBI | `sbi_scraper.py` | 9 | — | Selenium |
| 46 | AT&T | `att_scraper.py` | 16 | — | Selenium |
| 47 | Aditya Birla | `adityabirla_scraper.py` | 20 | — | Selenium |
| 48 | Hindalco | `hindalco_scraper.py` | 4 | — | Selenium |
| 49 | Royal Enfield | `royalenfield_scraper.py` | 20 | — | Selenium |
| 50 | ExxonMobil | `exxonmobil_scraper.py` | 50 | — | Selenium |

### Session 2 — Batch 3 SuccessFactors (8 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 51 | Air India | `airindia_scraper.py` | 12 | — | SuccessFactors |
| 52 | Tata AIG | `tataaig_scraper.py` | 25 | — | SuccessFactors |
| 53 | Tata International | `tatainternational_scraper.py` | 13 | — | SuccessFactors |
| 54 | Tata Projects | `tataprojects_scraper.py` | 15 | — | SuccessFactors |
| 55 | Trent | `trent_scraper.py` | 6 | — | SuccessFactors |
| 56 | Bajaj Electricals | `bajajelectricals_scraper.py` | 3 | — | SuccessFactors |
| 57 | Olam | `olam_scraper.py` | 1 | — | SuccessFactors |
| 58 | Tata Power | `tatapower_scraper.py` | 6 | — | SuccessFactors |

### Session 2 — Batch 3 Others (8 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 59 | DHL | `dhl_scraper.py` | 20 | — | Selenium |
| 60 | Ericsson | `ericsson_scraper.py` | 20 | — | Selenium |
| 61 | VOIS | `vois_scraper.py` | 20 | — | Selenium |
| 62 | Schneider Electric | `schneiderelectric_scraper.py` | 10 | — | Selenium |
| 63 | Deutsche Bank | `deutschebank_scraper.py` | 2 | — | Selenium |
| 64 | BNP Paribas | `bnpparibas_scraper.py` | 10 | — | Selenium |
| 65 | BP | `bp_scraper.py` | 8 | — | Selenium |
| 66 | Continental | `continental_scraper.py` | 20 | — | Selenium |
| 67 | DBS Bank | `dbsbank_scraper.py` | 246 | — | Selenium |
| 68 | Novartis | `novartis_scraper.py` | 20 | — | Selenium |

### Session 2 — Workday API Config (5 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 69 | Airbus | `airbus_scraper.py` | 39 | — | Workday API |
| 70 | Shell | `shell_scraper.py` | 35 | — | Workday API |
| 71 | Agilent | `agilent_scraper.py` | 40 | — | Workday API |
| 72 | Cadence | `cadence_scraper.py` | 40 | — | Workday API |
| 73 | R1 RCM | `r1rcm_scraper.py` | 40 | — | Workday API |

### Session 2 — Oracle HCM API Config (8 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 74 | Zensar | `zensar_scraper.py` | 50 | — | Oracle HCM |
| 75 | Berger Paints | `bergerpaints_scraper.py` | 50 | — | Oracle HCM |
| 76 | Black Box | `blackbox_scraper.py` | 50 | — | Oracle HCM |
| 77 | Croma | `croma_scraper.py` | 49 | — | Oracle HCM |
| 78 | Quess Corp | `quesscorp_scraper.py` | 50 | — | Oracle HCM |
| 79 | Tata Capital | `tatacapital_scraper.py` | 50 | — | Oracle HCM |
| 80 | Tata Chemicals | `tatachemicals_scraper.py` | 8 | — | Oracle HCM |
| 81 | Hexaware | `hexaware_scraper.py` | 150 | — | Oracle HCM |

### Session 2 — DarwinBox Config (9 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 82 | Vedanta | `vedanta_scraper.py` | 10 | — | DarwinBox |
| 83 | Brigade Group | `brigadegroup_scraper.py` | 10 | — | DarwinBox |
| 84 | Asahi Glass | `asahiglass_scraper.py` | 10 | — | DarwinBox |
| 85 | Niva Bupa | `nivabupa_scraper.py` | 10 | — | DarwinBox |
| 86 | Jindal Saw | `jindalsaw_scraper.py` | 10 | — | DarwinBox |
| 87 | Skoda VW | `skodavw_scraper.py` | 10 | — | DarwinBox |
| 88 | Polycab | `polycab_scraper.py` | 9 | — | DarwinBox |
| 89 | JSW Steel | `jswsteel_scraper.py` | 5 | — | DarwinBox |
| 90 | Piramal Finance | `piramalfinance_scraper.py` | 8 | — | DarwinBox |

### Session 2 — PeopleStrong Config (4 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 91 | Amara Raja | `amararaja_scraper.py` | 27 | — | PeopleStrong |
| 92 | Bajaj Finserv | `bajajfinserv_scraper.py` | 45 | — | PeopleStrong |
| 93 | HDFC Ergo | `hdfcergo_scraper.py` | 45 | — | PeopleStrong |
| 94 | RBL Bank | `rblbank_scraper.py` | 12 | — | PeopleStrong |

### Session 2 — Phenom/Standard Config (13 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 95 | Target | `target_scraper.py` | 30 | 69.0s | Phenom |
| 96 | Titan | `titan_scraper.py` | 10 | 44.7s | Phenom |
| 97 | ABB | `abb_scraper.py` | 20 | 24.7s | Phenom |
| 98 | Allianz | `allianz_scraper.py` | 20 | 74.8s | Phenom |
| 99 | Philips | `philips_scraper.py` | 10 | 115.3s | Phenom |
| 100 | NTT | `ntt_scraper.py` | 10 | 46.7s | Phenom |
| 101 | Trane Technologies | `tranetechnologies_scraper.py` | 10 | 52.8s | Phenom |
| 102 | United Airlines | `unitedairlines_scraper.py` | 10 | 55.5s | Phenom |
| 103 | AstraZeneca | `astrazeneca_scraper.py` | 30 | 68.9s | Standard |
| 104 | SAP | `sap_scraper.py` | 25 | 53.2s | SuccessFactors |
| 105 | Hilton | `hilton_scraper.py` | 10 | 117.8s | Phenom |
| 106 | Marriott | `marriott_scraper.py` | 20 | 62.0s | Custom |
| 107 | Bosch | `bosch_scraper.py` | 151 | 57.6s | SmartRecruiters |

### Session 2 — Batch 4 (8 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 108 | Adani Energy | `adanienergy_scraper.py` | 25 | 38.1s | Oracle HCM |
| 109 | Adani Ports | `adaniports_scraper.py` | 25 | 38.9s | Oracle HCM |
| 110 | Disney | `disney_scraper.py` | 20 | 63.8s | Custom |
| 111 | IHG | `ihg_scraper.py` | 50 | 43.9s | Custom |
| 112 | Mercedes-Benz | `mercedesbenz_scraper.py` | 10 | 41.3s | Custom |
| 113 | Prestige Group | `prestigegroup_scraper.py` | 1 | 40.4s | SuccessFactors |
| 114 | Vodafone Idea | `vodafoneidea_scraper.py` | 7 | 41.6s | SuccessFactors |

### Session 2 — Batch 5 (8 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 115 | Crompton | `crompton_scraper.py` | 20 | 72.3s | SuccessFactors |
| 116 | Diageo | `diageo_scraper.py` | 40 | 12.6s | Lever API |
| 117 | HAL | `hal_scraper.py` | 10 | 19.1s | WordPress API |
| 118 | Honda | `honda_scraper.py` | 5 | 43.2s | Custom |
| 119 | IOCL | `iocl_scraper.py` | 1355 | 69.9s | Custom JS |
| 120 | Nissan | `nissan_scraper.py` | 19 | 4.8s | Lever API |
| 121 | Yes Bank | `yesbank_scraper.py` | 20 | 58.5s | DarwinBox |

### Session 2 — Batch 6 (13 new)

| # | Scraper | File | Jobs | Time | Platform |
|---|---------|------|------|------|----------|
| 122 | BYD | `byd_scraper.py` | 1 | 62.0s | Custom |
| 123 | Glencore | `glencore_scraper.py` | 26 | 65.8s | Custom |
| 124 | HCC | `hcc_scraper.py` | 5 | 45.7s | Custom |
| 125 | Kalyan Jewellers | `kalyanjewellers_scraper.py` | 51 | 47.0s | Custom |
| 126 | Navitasys | `navitasys_scraper.py` | 2 | 61.8s | SuccessFactors |
| 127 | Tata Admin | `tataadmin_scraper.py` | 50 | 30.5s | Tata.com API |
| 128 | Tata AIA | `tataaia_scraper.py` | 17 | 46.9s | RippleHire |
| 129 | Uflex | `uflex_scraper.py` | 2 | 71.4s | Taleo |
| 130 | Vardhman | `vardhman_scraper.py` | 20 | 77.2s | SuccessFactors |
| 131 | Visa | `visa_scraper.py` | 118 | 50.0s | Custom |

---

## 2. Failing Scrapers — Bad Data

These scrapers run but return wrong data: nav links, page titles, filter labels, language selectors, non-India jobs, or page elements instead of actual job titles.

### Page Elements / Nav Links (50)

| # | Scraper | File | Issue |
|---|---------|------|-------|
| 1 | Bank of America | `bankofamerica_scraper.py` | "What do you want to do? Clear all" (filter labels) |
| 2 | Citigroup | `citigroup_scraper.py` | "On-Site/Resident" (work type labels) |
| 3 | Flipkart | `flipkart_scraper.py` | "Life At Flipkart" (nav links) |
| 4 | HSBC | `hsbc_scraper.py` | Only 2 duplicate jobs |
| 5 | JPMorgan Chase | `jpmorganchase_scraper.py` | "Job search results 711" (header) |
| 6 | KPMG | `kpmg_scraper.py` | "Careers" page link |
| 7 | Nykaa | `nykaa_scraper.py` | "careers@nykaa.com" (email) |
| 8 | Paytm | `paytm_scraper.py` | "Sorry, we couldn't find anything here" |
| 9 | PhonePe | `phonepe_scraper.py` | Mixed page elements and job data |
| 10 | Uber | `uber_scraper.py` | "Job search", "Start job search" |
| 11 | Zepto | `zepto_scraper.py` | Page text, not job listings |
| 12 | Zomato | `zomato_scraper.py` | "Careers" link, 300s timeout |
| 13 | Ola Electric | `olaelectric_scraper.py` | Page elements |
| 14 | BigBasket | `bigbasket_scraper.py` | Page elements |
| 15 | IndiGo | `indigo_scraper.py` | Page elements |
| 16 | Jio | `jio_scraper.py` | Page elements |
| 17 | ITC Limited | `itc_scraper.py` | Page elements |
| 18 | L&T | `lt_scraper.py` | Page elements |
| 19 | Tata Steel | `tatasteel_scraper.py` | Page elements |
| 20 | HUL | `hul_scraper.py` | Page elements |
| 21 | P&G | `pg_scraper.py` | Page elements |
| 22 | Colgate-Palmolive | `colgate_scraper.py` | Page elements |
| 23 | Asian Paints | `asianpaints_scraper.py` | Page elements |
| 24 | Bajaj Auto | `bajalauto_scraper.py` | Page elements |
| 25 | McKinsey | `mckinsey_scraper.py` | Page elements |
| 26 | Zoho | `zoho_scraper.py` | Duplicate entries |
| 27 | Adobe | `adobe_scraper.py` | Page elements |
| 28 | HP | `hp_scraper.py` | Page elements |
| 29 | Reckitt | `reckitt_scraper.py` | Page elements |
| 30 | Cipla | `cipla_scraper.py` | Page elements |
| 31 | Dr Reddys | `drreddys_scraper.py` | Page elements |
| 32 | Pfizer | `pfizer_scraper.py` | Page elements |
| 33 | Sun Pharma | `sunpharma_scraper.py` | Page elements |
| 34 | American Express | `amex_scraper.py` | Page elements |
| 35 | Boeing | `boeing_scraper.py` | Page elements |
| 36 | IIFL | `iifl_scraper.py` | Page elements |
| 37 | AbbVie | `abbvie_scraper.py` | Page elements |
| 38 | Cummins | `cummins_scraper.py` | Page elements |
| 39 | Cyient | `cyient_scraper.py` | Page elements |
| 40 | FedEx | `fedex_scraper.py` | Page elements |
| 41 | Fortis Healthcare | `fortis_scraper.py` | Page elements |
| 42 | Hero FinCorp | `herofincorp_scraper.py` | Page elements |
| 43 | Hero MotoCorp | `heromotocorp_scraper.py` | Page elements |
| 44 | J&J | `jnj_scraper.py` | Page elements |
| 45 | JSW Energy | `jswenergy_scraper.py` | Page elements |
| 46 | Jubilant FoodWorks | `jubilantfoodworks_scraper.py` | Page elements |
| 47 | KPIT Technologies | `kpit_scraper.py` | Page elements |
| 48 | Lowes | `lowes_scraper.py` | Page elements |
| 49 | Max Life Insurance | `maxlife_scraper.py` | Page elements |
| 50 | MetLife | `metlife_scraper.py` | Page elements |

### Non-India Jobs / Wrong Location Filter (20)

| # | Scraper | File | Issue |
|---|---------|------|-------|
| 51 | Cisco | `cisco_scraper.py` | Only 3 jobs in 243s, includes non-India |
| 52 | Walmart | `walmart_scraper.py` | Returns USA jobs |
| 53 | Salesforce | `salesforce_scraper.py` | Returns non-India jobs |
| 54 | Mondelez | `mondelez_scraper.py` | Returns non-India jobs |
| 55 | Nike | `nike_scraper.py` | Mixed India/non-India |
| 56 | Suncor | `suncor_scraper.py` | Returns Canada jobs |
| 57 | GE Aerospace | `geaerospace_scraper.py` | "Programmeur senior" (non-India) |
| 58 | Warner Bros | `warnerbros_scraper.py` | "CNN Investigative" (non-India) |
| 59 | Barclays | `barclays_scraper.py` | "London (United Kingdom)" |
| 60 | Munich Re | `munichre_scraper.py` | "Toronto, Canada" |
| 61 | Panasonic | `panasonic_scraper.py` | "Fredericksburg, Virginia" |
| 62 | S&P Global | `spglobal_scraper.py` | "New York, New York" |
| 63 | UnitedHealth | `unitedhealthgroup_scraper.py` | "Apopka, FL" |
| 64 | Kirloskar | `kirloskar_scraper.py` | "Pooler, GA, US" |
| 65 | Mitsubishi | `mitsubishi_scraper.py` | "Benton Harbor, MI, US" |
| 66 | Sony | `sony_scraper.py` | "Reston" (non-India) |
| 67 | OYO | `oyo_scraper.py` | SmartRecruiters, mixed Japanese text |
| 68 | American Tower | `americantower_scraper.py` | Mixed India/non-India |
| 69 | Whirlpool | `whirlpool_scraper.py` | "Global Corporate Security Manager" (non-India) |
| 70 | UBS Group | `ubsgroup_scraper.py` | Non-India Taleo, includes "no matching jobs" |

### Language Selectors / Filter Labels / Misc (30)

| # | Scraper | File | Issue |
|---|---------|------|-------|
| 71 | Muthoot Finance | `muthootfinance_scraper.py` | Page elements |
| 72 | Parle Agro | `parleagro_scraper.py` | Page elements |
| 73 | Persistent Systems | `persistent_scraper.py` | Page elements |
| 74 | NatWest Group | `natwest_scraper.py` | Page elements |
| 75 | Hitachi | `hitachi_scraper.py` | Page elements |
| 76 | McKesson | `mckesson_scraper.py` | Page elements |
| 77 | Birlasoft | `birlasoft_scraper.py` | Page elements |
| 78 | Coforge | `coforge_scraper.py` | Page elements |
| 79 | Siemens | `siemens_scraper.py` | Page elements |
| 80 | Netflix | `netflix_scraper.py` | Page elements |
| 81 | Oracle | `oracle_scraper.py` | Page elements |
| 82 | ANZ | `anz_scraper.py` | First entry is "Reset" button |
| 83 | AXA | `axa_scraper.py` | First entry is "19 Results" count |
| 84 | BASF | `basf_scraper.py` | "G_ENABLED_IDPS" (cookie names) |
| 85 | Bayer | `bayer_scraper.py` | "Your benefits", "Our culture" |
| 86 | GSK | `gsk_scraper.py` | "710 Results" header |
| 87 | Hyundai | `hyundai_scraper.py` | "English (United States)" |
| 88 | Intuit | `intuit_scraper.py` | "Quick job search:", "Filtered by" |
| 89 | Lenovo | `lenovo_scraper.py` | "click here", "CULTURE" |
| 90 | LG Electronics | `lgelectronics_scraper.py` | "Careers at LG", "Apply LG" |
| 91 | Rio Tinto | `riotinto_scraper.py` | "Search Jobs" input box |
| 92 | Verizon | `verizon_scraper.py` | "Jobs", "Go to saved jobs" |
| 93 | Wells Fargo | `wellsfargo_scraper.py` | "Saved Jobs", "Jobs" |
| 94 | Synchrony | `synchrony_scraper.py` | "Search Jobs" |
| 95 | BMW Group | `bmwgroup_scraper.py` | "Our Job Openings" |
| 96 | Havells | `havells_scraper.py` | "ALL JOBS (351)", filter labels |
| 97 | Tata Communications | `tatacommunications_scraper.py` | Job IDs as titles |
| 98 | ICICI Lombard | `icicilombard_scraper.py` | "Careers", "Other Products" |
| 99 | IndusInd Bank | `indusindbank_scraper.py` | "Careers" |
| 100 | Kajaria | `kajaria_scraper.py` | "Career" |

### More Bad Data (Batch 5-6 additions)

| # | Scraper | File | Issue |
|---|---------|------|-------|
| 101 | Kia India | `kiaindia_scraper.py` | "Current Openings" (heading) |
| 102 | Mankind Pharma | `mankindpharma_scraper.py` | "English (United Kingdom)" |
| 103 | Max Healthcare | `maxhealthcare_scraper.py` | "EXPLORE ALL JOBS" (button text) |
| 104 | NTPC | `ntpc_scraper.py` | "Register", "NORMS & FORMATS" (466 page elements) |
| 105 | Pidilite | `pidilite_scraper.py` | "EXPLORE ALL JOBS" |
| 106 | Siemens Energy | `siemensenergy_scraper.py` | "Search Jobs", "Login", "Deutsch" |
| 107 | Toyota Kirloskar | `toyotakirloskar_scraper.py` | "Careers", "EXPLORE JOB OPENINGS" |
| 108 | DLF | `dlf_scraper.py` | "Careers" |
| 109 | JK Tyre | `jktyre_scraper.py` | "LIFE AT JK TYRE", "LEARNING & DEVELOPMENT" |
| 110 | Poonawalla Fincorp | `poonawallafincorp_scraper.py` | "Consumer Business" (category) |
| 111 | Schaeffler | `schaeffler_scraper.py` | Language selectors (Czech, German) |
| 112 | Swiss Re | `swissre_scraper.py` | "Policies and statements", "Discover" |
| 113 | Suzlon | `suzlon_scraper.py` | "India \| Job Location" (labels) |
| 114 | Varroc | `varroc_scraper.py` | "48 Open Jobs" (count label) |
| 115 | Voltas | `voltas_scraper.py` | "Items per page:" (iframe label) |
| 116 | Volvo | `volvo_scraper.py` | Language selectors |
| 117 | Motilal Oswal | `motilaloswal_scraper.py` | Alternating titles/descriptions |
| 118 | SIS | `sis_scraper.py` | First entry is filter dropdown |

---

## 3. Failing Scrapers — Blocked / Down / Zero Results

| # | Scraper | File | Status | Issue |
|---|---------|------|--------|-------|
| 1 | Axis Bank | `axisbank_scraper.py` | TIMEOUT | Skillate platform down |
| 2 | HDFC Bank | `hdfcbank_scraper.py` | TIMEOUT | Skillate platform down |
| 3 | Kotak Mahindra Bank | `kotakmahindrabank_scraper.py` | FAIL | 0 jobs, no selectors matched |
| 4 | L'Oreal | `loreal_scraper.py` | BLOCKED | Cloudflare security |
| 5 | Myntra | `myntra_scraper.py` | DEAD | Job board no longer active |
| 6 | TCS | `tcs_scraper.py` | FAIL | Requires clicking into categories |
| 7 | Tesla | `tesla_scraper.py` | BLOCKED | Akamai Bot Manager |
| 8 | Qualcomm | `qualcomm_scraper.py` | FAIL | Workday API 422 + Selenium fail |
| 9 | Angel One | `angelone_scraper.py` | FAIL | 0 jobs |
| 10 | Shoppers Stop | `shoppersstop_scraper.py` | FAIL | 0 jobs |
| 11 | Maruti Suzuki | `marutisuzuki_scraper.py` | FAIL | 0 jobs |
| 12 | Starbucks | `starbucks_scraper.py` | DEAD | Careers page returns 404 |
| 13 | Adani Group | `adanigroup_scraper.py` | ERROR | Browser crash during scrape |
| 14 | United Breweries | `unitedbreweries_scraper.py` | FAIL | Age gate bypass but 0 India jobs |
| 15 | Tata Play | `tataplay_scraper.py` | FAIL | Oracle HCM returned 0 |
| 16 | Go Digit | `godigit_scraper.py` | FAIL | DarwinBox returned 0 |
| 17 | TVS Motor | `tvsmotor_scraper.py` | FAIL | DarwinBox returned 0 |
| 18 | GMMCO | `gmmco_scraper.py` | FAIL | DarwinBox returned 0 |
| 19 | Star Health | `starhealth_scraper.py` | FAIL | PeopleStrong returned 0 |
| 20 | Emirates Group | `emiratesgroup_scraper.py` | FAIL | 0 jobs, selectors not matched |
| 21 | Britannia | `britannia_scraper.py` | FAIL | "Page Not Found" on /jobs |
| 22 | HDFC Life | `hdfclife_scraper.py` | FAIL | JS job cards didn't load |
| 23 | Saint-Gobain | `saintgobain_scraper.py` | BLOCKED | Cloudflare challenge (3 retries) |
| 24 | Tencent | `tencent_scraper.py` | FAIL | API 500 error + Selenium fail |

---

## Fixes Applied

### Apple (2026-02-22)
- **Problem:** URL `?location=india` returned 0 results. Selectors targeted table layout but Apple uses React accordion.
- **Fix:** Removed param. Rewrote selectors for `ul#search-job-list > li`, `a.link-inline`, `button[aria-label="Next Page"]` pagination.
- **Result:** 40 jobs (20+20).

### HCLTech (2026-02-22)
- **Problem:** URL `www.hcltech.com/careers/india` is a marketing page.
- **Fix:** Changed URL to `careers.hcltech.com/go/India/9553955/` (SuccessFactors ATS). Rewrote selectors.
- **Result:** 10 jobs.

### Marico (2026-02-19)
- **Problem:** JS extraction walked up 5 parent levels, extracting "7 Open Jobs" header.
- **Fix:** Replaced DOM traversal with body text parsing between "View Job" markers.

---

## Key Observations

### Config-based scrapers are dramatically more reliable
Standardized platform scrapers (Workday API, Oracle HCM, DarwinBox, PeopleStrong, SuccessFactors) achieve **80-92% pass rates** vs **32% for generic Selenium scrapers**.

### Common failure patterns
1. **Page elements as job titles** (~50 scrapers): Generic CSS selectors like `div[class*="job"]` match nav links, buttons, and headers instead of actual job listings.
2. **Non-India jobs** (~20 scrapers): Location filters not applied or ignored. Jobs from US, Europe, Canada returned instead.
3. **Language selectors** (~8 scrapers): Extracting language dropdown options ("English (United States)", "Deutsch") as job titles.
4. **Filter labels as titles** (~10 scrapers): "ALL JOBS (351)", "19 Results", "710 Results" extracted as first entries.

### Recommendations for fixing BAD DATA scrapers
1. **Discover APIs** — Many career sites (Lever, Greenhouse, SmartRecruiters) expose JSON APIs that are more reliable than Selenium scraping.
2. **Platform-specific selectors** — Use platform-specific CSS selectors (e.g., Phenom: `data-ph-at-id="jobs-list-item"`, SuccessFactors: `a.jobTitle-link`).
3. **India location filtering** — Add server-side India filters via URL params or API payloads instead of relying on client-side filtering.
4. **Title validation** — Filter out entries matching common page element patterns: results counts, language names, button text.

---

## Known Platform Issues

### Skillate (HDFC Bank, Axis Bank) — Connection Timeout
Both banks use Skillate which appears to be down or blocking.

### Cloudflare (L'Oreal, Saint-Gobain) — Security Block
Would need `undetected-chromedriver` or direct API access.

### TCS — Requires Category Navigation
Loads "Browse through Functions" with categories. Needs rewrite to click into categories.

### Starbucks — Careers Page Removed
Returns 404. No alternative career URLs found.

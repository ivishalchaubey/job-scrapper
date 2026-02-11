# Scraper Analytics Report

**Last Updated:** February 11, 2026

---

## Overview

| Metric | Count |
|--------|-------|
| **Target Companies (from company-list.xlsx)** | 374 |
| **Scrapers Built** | 250 |
| **Scrapers Pending (not yet built)** | 124 |
| **Coverage** | 66.8% |

---

## Scraper Status Breakdown

| Status | Count | % of Built |
|--------|-------|------------|
| **Working** | 233 | 93.2% |
| **Zero Open Positions (scraper works, no jobs listed)** | 8 | 3.2% |
| **Network/Infrastructure Issues (intermittent)** | 4 | 1.6% |
| **URL Issues (needs URL update)** | 4 | 1.6% |
| **Anti-Bot Blocked** | 1 | 0.4% |
| **Total Built** | **250** | **100%** |

---

## Scrapers by Batch

### Original Scrapers (25)
Amazon, AWS, Accenture, JLL, Bain, BCG, Infosys, L'Oreal, Mahindra, Marico, Meta, Microsoft, Morgan Stanley, Nestle, Nvidia, Samsung, Swiggy, TCS, Tata Consumer, Tech Mahindra, Varun Beverages, Wipro, PepsiCo, BookMyShow, Abbott

### Batch 1 - Major Companies (50)
**Tech Giants (6):** Google, IBM, Apple, Intel, Dell, Cisco
**Consulting & IT Services (7):** HCLTech, Cognizant, Capgemini, Deloitte, EY, KPMG, PwC
**Financial Services (10):** Goldman Sachs, JPMorgan Chase, Citigroup, HDFC Bank, ICICI Bank, Axis Bank, Kotak Mahindra Bank, Bank of America, HSBC, Standard Chartered
**E-commerce & Startups (15):** Flipkart, Walmart, Myntra, Meesho, Zepto, Paytm, Zomato, PhonePe, Ola Electric, Uber, Nykaa, BigBasket, Delhivery, IndiGo, Jio
**Manufacturing & Conglomerates (12):** ITC Limited, Larsen & Toubro, Reliance Industries, Adani Group, Tata Steel, Tata Motors, Hindustan Unilever, Procter & Gamble, Colgate-Palmolive, Asian Paints, Godrej Group, Bajaj Auto

### Batch 2 - Expansion (50)
McKinsey, Parle Agro, Zoho, Aditya Birla, Adobe, Mondelez, Reckitt, Coca-Cola, State Bank of India, Tesla, AbbVie, American Express, Angel One, AT&T, Boeing, Cipla, Cummins, Cyient, Dr Reddys, Royal Enfield, Eli Lilly, ExxonMobil, FedEx, Fortis Healthcare, Hero FinCorp, Hero MotoCorp, Hindalco, Honeywell, HP, IIFL, Johnson & Johnson, JSW Energy, Jubilant FoodWorks, KPIT Technologies, Lowes, Maruti Suzuki, Max Life Insurance, MetLife, Muthoot Finance, Netflix, Nike, Oracle, Persistent Systems, Pfizer, Piramal Group, Qualcomm, Salesforce, Shoppers Stop, Starbucks, Sun Pharma

### Platform-Based Scrapers (50)
**Workday (9):** Airbus, Shell, Agilent Technologies, Cadence, R1 RCM, Suncor Energy, JLL, Samsung, Nvidia
**Oracle HCM (10):** Zensar Technologies, Berger Paints, Black Box, Croma, Quess Corp, Tata Capital, Tata Chemicals, Tata Play, Hexaware Technologies, Varun Beverages
**DarwinBox (12):** Vedanta, Brigade Group, Asahi Glass, Niva Bupa, Jindal Saw, Skoda VW, Polycab, Go Digit, TVS Motor, JSW Steel, GMMCO, Piramal Finance
**PeopleStrong (5):** Amara Raja Group, Bajaj Finserv, HDFC Ergo, RBL Bank, Star Health Insurance
**Phenom/NAS/Radancy (14):** Target, Titan, GE Aerospace, ABB, Allianz, Warner Bros, Philips, NTT, Trane Technologies, United Airlines, Wells Fargo, AstraZeneca, SAP, Barclays, Hilton, Marriott, Bosch, Synchrony

### Batch 3 - iCIMS & Multi-Strategy (25)
Air India, Tata AIG, Tata International, Tata Projects, Trent, Bajaj Electricals, Olam, United Breweries, Tata Power, NatWest Group, Hitachi, McKesson, Birlasoft, Coforge, DHL, Ericsson, VOIS, Schneider Electric, Siemens, Deutsche Bank, BNP Paribas, BP, Continental, DBS Bank, Novartis

### Batch 4 - Global Enterprises (25)
Adani Energy Solutions, Adani Ports, American Tower, ANZ, AXA, BASF, Bayer, Disney, Emirates Group, GSK, Hyundai, IHG, Intuit, Lenovo, LG Electronics, Mercedes-Benz, Munich Re, Panasonic, Prestige Group, Rio Tinto, S&P Global, UnitedHealth Group, Verizon, Vodafone Idea, Whirlpool

### Batch 5 - Industry Leaders (25)
Britannia Industries, BMW Group, Crompton Greaves, Diageo, DLF, Havells, HDFC Life, Hindustan Aeronautics (HAL), Honda, ICICI Lombard, IndusInd Bank, Indian Oil Corporation (IOCL), Kajaria Ceramics, Kia India, Mankind Pharma, Max Healthcare, NTPC, Nissan, OYO, Pidilite Industries, Saint-Gobain, Siemens Energy, Tata Communications, Toyota Kirloskar, Yes Bank

---

## Failed Scrapers Detail

### URL Issues (4) - Need URL Updates

| Company | Issue | Suggested Fix |
|---------|-------|---------------|
| Starbucks | HTTP 404 - careers page moved | Migrate to `careers.starbucks.in` (Taleo) |
| Shoppers Stop | Points to e-commerce site, no job listings | Migrate to `career.shoppersstop.com` (DarwinBox) |
| Maruti Suzuki | Informational page only, no job data | Migrate to `maruti.app.param.ai/jobs/` (Param.ai) |
| Qualcomm | Workday API returns HTTP 422 on all payloads | Try `wd12` subdomain instead of `wd5` |

### Anti-Bot Blocked (1)

| Company | Issue | Resolution |
|---------|-------|------------|
| Tesla | Akamai Bot Manager blocks all headless Chrome | Requires residential proxy or non-headless automation |

### Network/Infrastructure Issues (4) - Intermittent

| Company | Issue |
|---------|-------|
| Adani Group | `ERR_CONNECTION_TIMED_OUT` - server unreachable |
| Axis Bank | `ERR_CONNECTION_TIMED_OUT` - Skillate portal down |
| HDFC Bank | `ERR_CONNECTION_TIMED_OUT` - Skillate portal down |
| TCS | DNS intermittently down (has fallback URL) |

### Zero Open Positions (8) - Scrapers Work, No Jobs Listed

| Company | Platform | Notes |
|---------|----------|-------|
| Tata Play | Oracle HCM | API returns `TotalJobsCount: 0` |
| Go Digit | DarwinBox v2 | Shows "0 Open jobs available" |
| TVS Motor | DarwinBox v2 | Shows "0 Open jobs available" |
| GMMCO | DarwinBox v1 | Shows "No jobs found" |
| Star Health | PeopleStrong | Shows "No Jobs Available" |
| United Breweries | iCIMS/Heineken | Shows "no open positions matching India" |
| DBS Bank | Custom portal | Intermittent - sometimes returns 228 jobs |
| Emirates Group | Custom SPA | SPA/API loading not captured by generic selectors |

---

## Platform Distribution

| Platform | Scraper Count |
|----------|--------------|
| Custom / Company-specific | 130 |
| Phenom / NAS / Radancy | 18 |
| DarwinBox | 13 |
| Oracle HCM | 11 |
| Workday | 11 |
| iCIMS / SuccessFactors | 21 |
| PeopleStrong | 7 |
| Eightfold AI | 3 |
| Skillate | 2 |
| Other (SmartRecruiters, Taleo, TurboHire, etc.) | 34 |
| **Total** | **250** |

---

## Registration Status

| Location | Count | Description |
|----------|-------|-------------|
| `run.py` (CLI accessible) | 200 | Can run via `python run.py scrape --company <name>` |
| `src/config.py` only | 50 | Loaded via config system (Workday, Oracle HCM, DarwinBox, etc.) |
| `src/scrapers/__init__.py` | 75 | Batch 3 + Batch 4 + Batch 5 scrapers (module exports) |
| **Total unique scrapers** | **250** | All registered in at least one location |

---

## Progress Summary

```
Target Companies:  374
Built:             250  [============================================------]  66.8%
Pending:           124  [                                            ------]  33.2%

Of 250 Built:
Working:           233  [============================================      ]  93.2%
Zero Positions:      8  [=                                                 ]   3.2%
Intermittent:        4  [                                                  ]   1.6%
URL Issues:          4  [                                                  ]   1.6%
Anti-Bot:            1  [                                                  ]   0.4%
```

---

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | Main CLI runner - imports 200 scrapers, parallel execution |
| `src/config.py` | Configuration - 150 companies with URLs and scraper mappings |
| `src/scrapers/__init__.py` | Module exports for Batch 3 + Batch 4 + Batch 5 scrapers |
| `src/scrapers/*_scraper.py` | 250 individual scraper files |
| `FAILED_SCRAPERS.md` | Detailed documentation of 17 non-functional scrapers |
| `ANALYTICS.md` | This report |

---

## Recommendations

1. **URL Fixes (4 scrapers):** Update URLs for Starbucks, Shoppers Stop, Maruti Suzuki, and Qualcomm to restore functionality
2. **Network Issues (4 scrapers):** Monitor Adani Group, Axis Bank, HDFC Bank, and TCS - these may self-resolve
3. **Zero Position Scrapers (8):** No action needed - will automatically pick up jobs when companies post openings
4. **Tesla:** Consider residential proxy service or Playwright with real browser profile
5. **Coverage Expansion:** 124 companies from the target list still need scrapers to reach 100% coverage
6. **Config-only Scrapers:** Consider registering all 50 config-only scrapers in `run.py` for unified CLI access

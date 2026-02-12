# Job Scraper System

Production-ready job scraping system for **275 companies** across India — covering tech giants, consulting firms, financial institutions, e-commerce, manufacturing, pharma, and more.

Built with **Django + Django REST Framework + MongoDB + Selenium**.

---

## Quick Start

```bash
# 1. Clone and enter directory
cd backend

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your MongoDB URI if not using defaults

# 5. Run migrations (SQLite for Django internals)
python manage.py migrate

# 6. Setup MongoDB indexes
python -c "from scripts.setup_indexes import create_indexes; create_indexes()"

# 7. Start the server
python manage.py runserver 0.0.0.0:8000
```

Open http://localhost:8000 for the dashboard, or http://localhost:8000/api/docs for Swagger UI.

---

## CLI Usage

All operations go through `run.py`:

```bash
# Scrape all 275 companies (10 parallel workers)
python run.py scrape --workers 10

# Scrape a single company
python run.py scrape --company Google
python run.py scrape --company "Goldman Sachs"
python run.py scrape --company "HDFC Bank"

# Custom timeout per scraper (default: 180s)
python run.py scrape --workers 15 --timeout 120

# Start Django dev server
python run.py server

# Clean all data (jobs + scraping history)
python run.py clean
```

### Speed Reference

| Workers | Approx Time (275 companies) | Use Case               |
|---------|----------------------------|------------------------|
| 3       | ~45 min                    | Slow connections       |
| 5       | ~30 min                    | Conservative           |
| 10      | ~15 min                    | Recommended            |
| 15      | ~10 min                    | Fast connections       |

---

## Project Structure

```
backend/
  manage.py                              # Django management (DJANGO_SETTINGS_MODULE=config.settings)
  run.py                                 # CLI: scrape, server, clean
  requirements.txt                       # -> requirements/base.txt
  db.sqlite3                             # SQLite (Django auth/admin/sessions only)
  .env.example                           # Environment variables template

  config/                                # Django project configuration
    settings/
      __init__.py                        # Auto-selects dev/prod via DJANGO_ENV
      base.py                            # Shared settings (DB, REST, CORS, etc.)
      development.py                     # DEBUG=True, ALLOWED_HOSTS=['*']
      production.py                      # Secure cookies, strict hosts
    urls.py                              # Root URL routing
    wsgi.py / asgi.py                    # WSGI/ASGI entry points
    scraper.py                           # Scraper config (COMPANIES dict, timeouts)

  core/                                  # Shared utilities
    db.py                                # MongoDB connection (get_db, get_collection)
    logging.py                           # setup_logger (console + file)

  apps/                                  # Django applications
    data_store/                          # Job data API (MongoDB-backed)
      services.py                        # Job CRUD, stats, scraping history
      views.py                           # REST endpoints (jobs, stats, health)
      serializers.py                     # DRF serializers (plain, no ORM)
      urls.py                            # /api/ routes
    scraper_manager/                     # Scraper control API
      services.py                        # ScrapeTask CRUD (MongoDB)
      views.py                           # Start/cancel/status endpoints
      serializers.py                     # Task + request serializers
      urls.py                            # /api/scraper/ routes
      engine.py                          # ThreadPoolExecutor scrape orchestration
    dashboard/                           # Web UI
      views.py                           # Template rendering
      urls.py                            # /, /jobs/, /scrapers/
      templates/dashboard/               # HTML templates (JS-driven)
      templatetags/                      # Custom template tags

  scrapers/                              # 275 scraper files
    registry.py                          # SCRAPER_MAP + ALL_COMPANY_CHOICES
    amazon_scraper.py
    google_scraper.py
    ... (275 scraper files)

  scripts/                               # Management scripts
    setup_indexes.py                     # MongoDB index creation

  requirements/                          # Split dependencies
    base.txt                             # Core dependencies
    development.txt                      # Dev extras
    production.txt                       # Production (gunicorn)

  logs/                                  # Runtime logs (auto-created)
```

---

## Architecture

### Tech Stack

| Layer           | Technology                  |
|-----------------|----------------------------|
| Framework       | Django 4.2 + DRF            |
| App Database    | MongoDB (pymongo)           |
| Django Database | SQLite (auth/admin/sessions)|
| Scraping        | Selenium + Chrome headless  |
| API Docs        | drf-spectacular (Swagger)   |
| Task Execution  | ThreadPoolExecutor          |

### Design Decisions

- **pymongo** (not djongo/mongoengine) — direct MongoDB access, no ORM adapter hacks
- **SQLite** for Django internals — auth, admin, sessions stay in SQLite
- **MongoDB** for all app data — jobs, scraping_runs, scrape_tasks collections
- **Service pattern** — `services.py` in each app handles all MongoDB operations
- **Function-based views** — cleaner with MongoDB dicts (no ORM querysets)
- **Plain Serializers** — not ModelSerializer (no Django models for app data)
- **Split settings** — base/development/production via `DJANGO_ENV` env var

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=jobs_db

# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_ENV=development          # development | production

# Production only
ALLOWED_HOSTS=your-domain.com
```

---

## API Endpoints

### Dashboard (HTML)

| Method | URL          | Description         |
|--------|-------------|---------------------|
| GET    | `/`          | Dashboard home      |
| GET    | `/jobs/`     | Jobs browser        |
| GET    | `/scrapers/` | Scrapers overview   |

### Data Store API

| Method | URL                    | Description                          |
|--------|------------------------|--------------------------------------|
| GET    | `/api/jobs/`           | List jobs (paginated, filterable)    |
| GET    | `/api/jobs/<id>/`      | Get single job by ID                 |
| GET    | `/api/stats/`          | Dashboard stats (totals, rates)      |
| GET    | `/api/companies/`      | Company list with job counts         |
| GET    | `/api/history/`        | Scraping run history                 |
| GET    | `/api/health/`         | Health check (DB status)             |

### Scraper Manager API

| Method | URL                                | Description                  |
|--------|------------------------------------|------------------------------|
| POST   | `/api/scraper/start/`              | Start scraping (all/subset)  |
| POST   | `/api/scraper/start/<company>/`    | Scrape single company        |
| GET    | `/api/scraper/tasks/`              | List all scrape tasks        |
| GET    | `/api/scraper/tasks/<task_id>/`    | Get task progress            |
| POST   | `/api/scraper/tasks/<task_id>/cancel/` | Cancel running task      |
| GET    | `/api/scraper/scrapers/`           | List all 275 scrapers        |

### Documentation

| Method | URL              | Description          |
|--------|-----------------|----------------------|
| GET    | `/api/docs/`     | Swagger UI           |
| GET    | `/api/schema/`   | OpenAPI 3.0 schema   |

### Job List Filters

```
GET /api/jobs/?company_name=Google&city=Bangalore&page=1&page_size=20
GET /api/jobs/?search=engineer&ordering=-updated_at
GET /api/jobs/?employment_type=Full-time&department=Engineering
```

**Parameters:**
- `company_name` — Filter by company (case-insensitive exact match)
- `city` — Filter by city (regex match)
- `country` — Filter by country
- `employment_type` — Filter by type (Full-time, Part-time, etc.)
- `department` — Filter by department
- `search` — Full-text search across title, company, city, department
- `ordering` — Sort field, prefix `-` for descending (default: `-updated_at`)
- `page` — Page number (default: 1)
- `page_size` — Results per page (default: 50)

---

## API Examples

```bash
# Health check
curl http://localhost:8000/api/health/
# {"status": "healthy", "database": "connected", "scrapers": 275}

# Dashboard stats
curl http://localhost:8000/api/stats/
# {"total_jobs": 19551, "active_companies": 254, "success_rate": 100.0, ...}

# List jobs with filters
curl "http://localhost:8000/api/jobs/?company_name=Google&page_size=5"

# Search jobs
curl "http://localhost:8000/api/jobs/?search=engineer&city=Bangalore"

# Company stats
curl http://localhost:8000/api/companies/

# List all scrapers
curl http://localhost:8000/api/scraper/scrapers/
# {"total": 275, "companies": ["ABB", "AbbVie", "Abbott", ...]}

# Start scraping via API
curl -X POST http://localhost:8000/api/scraper/start/ \
  -H "Content-Type: application/json" \
  -d '{"companies": ["Google", "Amazon"], "max_workers": 5}'

# Start scraping all companies
curl -X POST http://localhost:8000/api/scraper/start/ \
  -H "Content-Type: application/json" \
  -d '{"all": true, "max_workers": 10}'

# Check task progress
curl http://localhost:8000/api/scraper/tasks/<task_id>/
```

---

## MongoDB Collections

### `jobs`

| Field            | Type     | Description                      |
|------------------|----------|----------------------------------|
| `external_id`    | string   | Stable MD5 hash (company + ID)   |
| `company_name`   | string   | Company name                     |
| `title`          | string   | Job title                        |
| `description`    | string   | Job description                  |
| `location`       | string   | Full location string             |
| `city`           | string   | City                             |
| `state`          | string   | State/province                   |
| `country`        | string   | Country                          |
| `employment_type`| string   | Full-time, Part-time, etc.       |
| `department`     | string   | Department/division              |
| `apply_url`      | string   | Application URL                  |
| `posted_date`    | string   | Posting date                     |
| `job_function`   | string   | Job category                     |
| `experience_level`| string  | Entry, Mid, Senior, etc.         |
| `salary_range`   | string   | Salary information               |
| `remote_type`    | string   | Remote, Hybrid, On-site          |
| `status`         | string   | active / inactive                |
| `created_at`     | datetime | First scraped                    |
| `updated_at`     | datetime | Last updated                     |

**Indexes:** `external_id` (unique), `company_name`, `status`, text index on `title`.

### `scraping_runs`

| Field          | Type     | Description            |
|----------------|----------|------------------------|
| `company_name` | string   | Company scraped        |
| `run_date`     | datetime | When the run happened  |
| `jobs_scraped`  | int     | Number of jobs found   |
| `status`       | string   | success / failed       |
| `error_message`| string   | Error details (if any) |

### `scrape_tasks`

| Field                | Type     | Description                    |
|----------------------|----------|--------------------------------|
| `task_id`            | string   | UUID task identifier           |
| `company_name`       | string   | Target company (or empty=all)  |
| `status`             | string   | pending/running/completed/failed/cancelled |
| `total_companies`    | int      | Total companies to scrape      |
| `completed_companies`| int      | Companies done so far          |
| `total_jobs_found`   | int      | Running total of jobs           |
| `started_at`         | datetime | Task start time                |
| `finished_at`        | datetime | Task end time                  |
| `results`            | dict     | Per-company results            |
| `error_message`      | string   | Error details (if any)         |

---

## Scraper Configuration

Edit `config/scraper.py` to customize:

```python
SCRAPE_TIMEOUT = 30           # Page load timeout (seconds)
HEADLESS_MODE = True          # Run Chrome headless
MAX_PAGES_TO_SCRAPE = 15      # Max pagination pages
FETCH_FULL_JOB_DETAILS = False
```

The `COMPANIES` dict in the same file maps company names to their career page URLs and scraper identifiers. All 275 companies are configured here or define their own URLs in their scraper `__init__`.

---

## Settings (Development vs Production)

Settings are split across three files in `config/settings/`:

| File              | Purpose                                    |
|-------------------|--------------------------------------------|
| `base.py`         | Shared: installed apps, middleware, DB, etc.|
| `development.py`  | `DEBUG=True`, `ALLOWED_HOSTS=['*']`        |
| `production.py`   | `DEBUG=False`, secure cookies, strict hosts|

The active settings file is selected by the `DJANGO_ENV` environment variable (defaults to `development`).

---

## Production Deployment

```bash
# Set environment
export DJANGO_ENV=production
export DJANGO_SECRET_KEY=your-production-secret
export ALLOWED_HOSTS=your-domain.com
export MONGO_URI=mongodb://your-mongo-host:27017
export MONGO_DB_NAME=jobs_db

# Install production deps
pip install -r requirements/production.txt

# Run migrations
python manage.py migrate

# Setup indexes
python -c "from scripts.setup_indexes import create_indexes; create_indexes()"

# Collect static files
python manage.py collectstatic --noinput

# Start with gunicorn
gunicorn config.wsgi:application -w 4 -b 0.0.0.0:8000
```

### Scheduled Scraping (Cron)

```bash
# Scrape all companies daily at 2 AM
0 2 * * * cd /path/to/backend && venv/bin/python run.py scrape --workers 10

# Scrape specific company every 6 hours
0 */6 * * * cd /path/to/backend && venv/bin/python run.py scrape --company Google
```

---

## Supported Companies (275)

### Tech Giants
Amazon, AWS, Google, Apple, Microsoft, Meta, IBM, Intel, Dell, Cisco, Nvidia, Adobe, Oracle, SAP, Salesforce, Netflix, Tesla

### Consulting & IT Services
Accenture, TCS, Infosys, Wipro, HCLTech, Cognizant, Capgemini, Tech Mahindra, Deloitte, EY, KPMG, PwC, McKinsey, BCG, Bain, Birlasoft, Coforge, Persistent Systems, Cyient, KPIT Technologies, Hexaware Technologies, Zoho

### Financial Services
Goldman Sachs, JPMorgan Chase, Morgan Stanley, Citigroup, HDFC Bank, ICICI Bank, Axis Bank, Kotak Mahindra Bank, Bank of America, HSBC, Standard Chartered, State Bank of India, Deutsche Bank, BNP Paribas, DBS Bank, Wells Fargo, Barclays, American Express, Angel One, IIFL, IndusInd Bank, Yes Bank, RBL Bank, Bajaj Finserv, HDFC Ergo, Muthoot Finance, Motilal Oswal, Poonawalla Fincorp, UBS Group

### E-commerce & Startups
Flipkart, Walmart, Myntra, Meesho, Zepto, Paytm, Zomato, Swiggy, PhonePe, Ola Electric, Uber, Nykaa, BigBasket, Delhivery, BookMyShow, OYO, Jio

### Manufacturing & Conglomerates
ITC Limited, Larsen & Toubro, Reliance Industries, Adani Group, Tata Steel, Tata Motors, Hindustan Unilever, Procter & Gamble, Colgate-Palmolive, Asian Paints, Godrej Group, Bajaj Auto, Mahindra, Marico, Tata Consumer, Tata Power, Tata Communications, Tata Projects, Tata AIG, Tata AIA, and many more...

### Pharma & Healthcare
Abbott, AbbVie, Cipla, Dr Reddys, Eli Lilly, Fortis Healthcare, GSK, Johnson & Johnson, Mankind Pharma, Max Healthcare, Max Life Insurance, MetLife, Novartis, Pfizer, Piramal Group, Sun Pharma, Star Health Insurance

### Auto & Industrial
Bajaj Auto, BMW Group, Honda, Hyundai, Kia India, Maruti Suzuki, Mercedes-Benz, Nissan, Royal Enfield, Toyota Kirloskar, BYD, Volvo, Schaeffler, Continental, Bosch, Cummins, Havells, Crompton, Siemens, Siemens Energy, Schneider Electric, ABB, Honeywell

### And More...
Airlines (Air India, IndiGo, United Airlines, Emirates Group), Hospitality (Hilton, Marriott, IHG, Starbucks), Energy (BP, ExxonMobil, Shell, IOCL, NTPC, Adani Energy, JSW Energy, Suncor, Suzlon, Tata Power), Telecom (Verizon, Vodafone Idea, VOIS, Ericsson, NTT, American Tower), Real Estate (DLF, Prestige Group, Brigade Group), and more.

---

## Troubleshooting

### MongoDB Connection Issues

```bash
# Check MongoDB is running
brew services list | grep mongodb       # macOS
sudo systemctl status mongod            # Linux

# Start MongoDB
brew services start mongodb-community   # macOS
sudo systemctl start mongod             # Linux

# Test connection
python -c "from core.db import get_db; print(get_db().name)"
```

### Chrome/Selenium Issues

```bash
# Update webdriver-manager
pip install --upgrade webdriver-manager

# Verify Selenium
python -c "from selenium import webdriver; print('Selenium OK')"
```

### Django Check

```bash
# Verify project configuration
python manage.py check

# Run migrations
python manage.py migrate
```

### Port Already in Use

```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9
```

### Virtual Environment

```bash
# Always activate before running
source venv/bin/activate    # macOS/Linux
venv\Scripts\activate       # Windows

# You should see (venv) in your prompt
(venv) user@mac backend %
```

---

## License

MIT License

# Job Scraper System

Production-ready job scraping system for **125 companies** including tech giants, consulting firms, financial institutions, e-commerce, manufacturing, pharma, and more across India.

---

## ⚡ Quick Reference

**Always use an action with run.py:**

```bash
# ✅ BEST - Fast parallel scraping (10 workers)
python run.py scrape --workers 10

# ✅ GOOD - Default parallel scraping (5 workers)
python run.py scrape

# ✅ CORRECT - Scrape single company
python run.py scrape --company Google

# ✅ CORRECT - Start API server
python run.py api

# ✅ CORRECT - Export data
python run.py export

# ❌ WRONG - Missing action (will error)
python run.py
```

**Available Actions:**
- `scrape` - Run web scraping (all or specific company)
  - `--workers N` - Number of parallel workers (default: 5, recommended: 10)
- `export` - Export data to XML
- `api` - Start API server
- `clean` - Clean database

**Speed Tips:**
- Use `--workers 10` for fastest scraping (10-15 minutes)
- Use `--workers 5` for balanced speed (20 minutes)
- Use `--workers 3` for conservative/slow connections

---

## Features

- ✅ **125 Scrapers** covering major companies in India (25 existing + 100 new)
- ⚡ **Multithreaded Scraping** - 5-10x faster with parallel execution
- 📊 **Auto Analytics Reports** - Detailed markdown reports after each run
- ✅ **Swagger UI** - Interactive API documentation at `/api/docs`
- ✅ **OpenAPI 3.0** - Complete API specification
- ✅ Selenium with Chrome headless browser
- ✅ MongoDB/PostgreSQL database with stable external_id tracking
- ✅ XML export following Scoutit's opportunity schema
- ✅ REST API with 10 endpoints
- ✅ Scraping run history and logging
- ✅ Zero-job detection and error handling
- ✅ Pagination and filtering support
- ✅ Full job details extraction
- ✅ Health checks and system monitoring
- ✅ Real-time progress tracking

## Project Structure

```
python-job-scrape/
├── src/
│   ├── api/
│   │   └── app.py              # Flask REST API
│   ├── database/
│   │   └── db.py               # Database operations
│   ├── scrapers/
│   │   ├── amazon_scraper.py   # Amazon jobs scraper
│   │   ├── accenture_scraper.py # Accenture jobs scraper
│   │   └── jll_scraper.py      # JLL/Workday scraper
│   ├── utils/
│   │   ├── logger.py           # Logging utility
│   │   └── xml_generator.py   # XML export generator
│   └── config.py               # Configuration settings
├── data/                       # Application data (auto-created)
├── logs/                       # Log files (auto-created)
├── output/                     # XML exports (auto-created)
├── run.py                      # Main runner script
└── requirements.txt            # Python dependencies

```

## Setup

### 1. Install PostgreSQL

**macOS (Homebrew):**

```bash
brew install postgresql@15
brew services start postgresql@15
```

**Ubuntu/Debian:**

```bash
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**Windows:**
Download from [postgresql.org](https://www.postgresql.org/download/)

### 2. Create Database

```bash
# Create the database (use your system username)
psql postgres -c "CREATE DATABASE jobs_db;"

# Verify
psql -l
```

### 3. Configure Environment

Copy the example environment file and update with your database credentials:

```bash
cp .env.example .env
```

Edit `.env` and set your database username (typically your system username on macOS):

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=jobs_db
DB_USER=your_username  # Your system username on macOS
DB_PASSWORD=           # Leave blank if no password set
```

### 4. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Test Database Connection

```bash
python test_db.py
```

You should see:

```
✓ Database connection successful!
✓ Tables created/verified!
```

### 7. Verify Installation

```bash
python -c "from selenium import webdriver; print('Selenium installed successfully')"
```

## Usage

### Important: Always Include the Action

The `run.py` script requires an action. Available actions:
- `scrape` - Run web scraping
- `export` - Export data to XML
- `api` - Start API server
- `clean` - Clean database

---

### 1. Scrape All Companies (125 Companies) - ⚡ FAST MODE

```bash
# Basic syntax (5 parallel workers - DEFAULT)
python run.py scrape

# Fast mode (10 parallel workers)
python run.py scrape --workers 10

# Conservative mode (3 workers)
python run.py scrape --workers 3

# From activated virtual environment
source venv/bin/activate
python run.py scrape --workers 10
```

**This will:**
- ✅ Scrape jobs from all 125 companies **IN PARALLEL**
- ✅ Save to database in real-time
- ✅ Show live progress for each company
- ✅ Generate detailed analytics report (markdown file)
- ⚡ Time: ~10-20 minutes with 10 workers (5-6x faster!)
- 📊 Creates `SCRAPING_ANALYTICS_YYYYMMDD_HHMMSS.md`

**Speed Comparison:**
- Old sequential: ~60 minutes
- New parallel (5 workers): ~20 minutes
- New parallel (10 workers): ~10-15 minutes

---

### 2. Scrape Specific Company

```bash
# Tech Giants
python run.py scrape --company Google
python run.py scrape --company Amazon
python run.py scrape --company Apple
python run.py scrape --company Tesla
python run.py scrape --company Netflix

# Consulting & IT
python run.py scrape --company McKinsey
python run.py scrape --company Deloitte
python run.py scrape --company EY
python run.py scrape --company KPMG
python run.py scrape --company PwC

# Financial Services
python run.py scrape --company "Goldman Sachs"
python run.py scrape --company "JPMorgan Chase"
python run.py scrape --company "HDFC Bank"
python run.py scrape --company "ICICI Bank"

# E-commerce & Startups
python run.py scrape --company Flipkart
python run.py scrape --company Myntra
python run.py scrape --company Meesho
python run.py scrape --company Zomato
python run.py scrape --company Paytm

# Note: Use quotes for company names with spaces
python run.py scrape --company "Morgan Stanley"
python run.py scrape --company "Larsen & Toubro"
```

**Tip:** See `scraper_progress_log.json` for complete list of 125 companies

---

### 3. Export to XML

```bash
# Export all jobs
python run.py export

# Export specific company
python run.py export --company Google
python run.py export --company Tesla
python run.py export --company "Goldman Sachs"
```

**Output:** XML files saved to `output/` directory

---

### 4. Start API Server

```bash
python run.py api
```

**Access:**
- API Root: `http://localhost:8000`
- **Swagger UI (Interactive Docs):** `http://localhost:8000/api/docs` 🚀
- Health Check: `http://localhost:8000/api/health`
- Companies List: `http://localhost:8000/api/companies`

---

### 5. Clean Database

```bash
python run.py clean
```

**Warning:** This will delete all scraped data!

---

### Common Commands

```bash
# 1. Activate virtual environment (always do this first)
source venv/bin/activate

# 2. Run all scrapers (FAST - 10 workers)
python run.py scrape --workers 10

# 3. Check real-time progress (in terminal output)
# You'll see: ✓ Google: 25 jobs (3.2s)

# 4. View analytics report
ls -lt SCRAPING_ANALYTICS_*.md | head -1
cat SCRAPING_ANALYTICS_20260206_*.md

# 5. Start API to view results
python run.py api

# 6. Open Swagger UI in browser
open http://localhost:8000/api/docs
```

---

## 📊 Analytics Reports

After each scrape run, an analytics report is automatically generated:

**Report includes:**
- ✅ Total companies scraped (success/failed)
- ✅ Total jobs found
- ✅ Top performers by job count
- ✅ List of failed scrapes with errors
- ✅ Performance metrics (duration, speed)
- ✅ Jobs distribution breakdown
- ✅ Recommendations for improvements

**File format:** `SCRAPING_ANALYTICS_YYYYMMDD_HHMMSS.md`

**Example:**
```bash
# After running scrape
python run.py scrape --workers 10

# Report is saved automatically
# View it:
cat SCRAPING_ANALYTICS_20260206_153045.md
```

## API Endpoints

### Interactive Testing
Visit **`http://localhost:8000/api/docs`** for interactive Swagger UI with:
- Try It Out functionality
- Request/response examples
- Schema documentation
- All 10 endpoints

### Endpoint Summary

#### System Endpoints
- `GET /` - API information
- `GET /api/health` - Health check
- `GET /api/companies` - List all 125 companies
- `GET /api/docs` - Swagger UI

#### Job Endpoints
- `GET /api/jobs` - Get all jobs (pagination & filters)
- `GET /api/jobs/{company}` - Get jobs by company

#### Statistics
- `GET /api/stats` - Scraping statistics & history

#### Scraping
- `POST /api/scrape/{company}` - Trigger scraping

#### Export
- `GET /api/export/xml` - Export all jobs as XML
- `GET /api/export/xml/{company}` - Export company jobs as XML

### Quick API Examples

```bash
# Health check
curl http://localhost:8000/api/health

# List all companies
curl http://localhost:8000/api/companies

# Get Google jobs
curl http://localhost:8000/api/jobs/Google

# Get jobs with filters
curl "http://localhost:8000/api/jobs?location=Bangalore&limit=20"

# Get statistics
curl http://localhost:8000/api/stats

# Export to XML
curl http://localhost:8000/api/export/xml/Google -o google_jobs.xml
```

See `API_DOCUMENTATION.md` for complete API guide.

## Database Schema

### Jobs Table

- `external_id` - Stable MD5 hash identifier
- `company_name` - Company name
- `title` - Job title
- `description` - Job description
- `location` - Full location string
- `city`, `state`, `country` - Parsed location
- `employment_type` - Full-time, Part-time, etc.
- `department` - Department/division
- `apply_url` - Live application URL
- `posted_date` - Job posting date
- `job_function` - Job category
- `experience_level` - Entry, Mid, Senior, etc.
- `salary_range` - Salary information
- `remote_type` - Remote, Hybrid, On-site
- `status` - active/inactive
- `created_at`, `updated_at` - Timestamps

### Scraping Runs Table

- Logs each scraping run
- Tracks success/failure
- Records job counts
- Stores error messages

## XML Output Format

Follows Scoutit's opportunity schema:

```xml
<?xml version="1.0" encoding="utf-8"?>
<opportunities xmlns="http://www.scoutit.com/schema/opportunities">
  <opportunity>
    <external_id>abc123...</external_id>
    <company>Amazon</company>
    <title>Software Engineer</title>
    <apply_url>https://...</apply_url>
    <location>Bangalore, Karnataka, India</location>
    <city>Bangalore</city>
    <state>Karnataka</state>
    <country>India</country>
    <!-- Optional fields only included if data exists -->
  </opportunity>
</opportunities>
```

## Configuration

Edit `src/config.py` to customize:

- `HEADLESS_MODE` - Run browser in headless mode (default: True)
- `SCRAPE_TIMEOUT` - Page load timeout in seconds
- `API_PORT` - API server port (default: 5000)
- `DEBUG_MODE` - Flask debug mode

## Logs

Logs are saved in `logs/` directory:

- Daily log files: `scraper_YYYYMMDD.log`
- Console output with timestamps
- Error tracking and debugging info

## Database

PostgreSQL database: `jobs_db`

You can view it using:

- psql CLI: `psql jobs_db`
- pgAdmin
- Any PostgreSQL client
- TablePlus, DBeaver, etc.

## Features Implemented

✅ **Two Scraping Runs**: Run `python run.py scrape` multiple times  
✅ **XML Output**: Exports in Scoutit schema format  
✅ **Stable external_id**: MD5 hash based on company + job ID  
✅ **Valid apply URLs**: Direct links to job applications  
✅ **No Fabricated Data**: Empty fields left blank  
✅ **Zero-Job Detection**: Logs when no jobs found  
✅ **Error Handling**: Logs failures with error messages  
✅ **API for Validation**: View job counts and data via REST API

## Testing

### Automated Tests

```bash
# Test all scraper structures
python test_all_new_scrapers.py
python test_batch2_scrapers.py

# Test scraper functionality (actual scraping)
python test_scraper_functionality.py

# End-to-end test
python test_end_to_end.py
```

### Manual Testing

#### Swagger UI (Recommended)
1. Start API: `python run.py api`
2. Open: `http://localhost:8000/api/docs`
3. Use "Try it out" feature to test endpoints

#### Using cURL
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/companies
curl http://localhost:8000/api/jobs/Google
```

#### Using Postman
Import these endpoints:
- `GET http://localhost:8000/api/jobs`
- `GET http://localhost:8000/api/stats`
- `GET http://localhost:8000/api/jobs/Google`
- `GET http://localhost:8000/api/export/xml`

## Production Deployment

1. Set `HEADLESS_MODE = True` in config.py
2. Use production WSGI server (gunicorn):
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 src.api.app:app
   ```
3. Set up cron job for scheduled scraping:
   ```bash
   0 2 * * * cd /path/to/project && venv/bin/python run.py scrape
   ```

## Troubleshooting

### Error: "the following arguments are required: action"

**Problem:** Running `python run.py` without action
```bash
# ❌ Wrong
python run.py

# ✅ Correct - Add action
python run.py scrape       # To scrape
python run.py api          # To start API
python run.py export       # To export
```

### Chrome Driver Issues

```bash
pip install --upgrade webdriver-manager
```

### Permission Errors

```bash
chmod +x run.py
```

### Database Connection Issues

```bash
# Check MongoDB is running
brew services list | grep mongodb

# Start MongoDB
brew services start mongodb-community
```

### Virtual Environment Not Activated

```bash
# Always activate before running
source venv/bin/activate

# You should see (venv) in your prompt
(venv) user@mac backend %
```

### Port Already in Use (8000)

```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Or change port in .env
echo "API_PORT=8001" >> .env
```

## License

MIT License

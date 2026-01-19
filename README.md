# Job Scraper System

Production-ready job scraping system for Amazon, Accenture, and JLL career pages using Python, Selenium, and SQLite.

## Features

- ✅ Scrapes jobs from 3 different career page structures (Amazon, Accenture, JLL/Workday)
- ✅ Selenium with Chrome headless browser
- ✅ SQLite database with stable external_id tracking
- ✅ XML export following Scoutit's opportunity schema
- ✅ REST API for data access
- ✅ Scraping run history and logging
- ✅ Zero-job detection and error handling

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
├── data/                       # SQLite database (auto-created)
├── logs/                       # Log files (auto-created)
├── output/                     # XML exports (auto-created)
├── run.py                      # Main runner script
└── requirements.txt            # Python dependencies

```

## Setup

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Verify Installation

```bash
python -c "from selenium import webdriver; print('Selenium installed successfully')"
```

## Usage

### Scrape All Companies

```bash
python run.py scrape
```

### Scrape Specific Company

```bash
python run.py scrape --company Amazon
python run.py scrape --company Accenture
python run.py scrape --company JLL
```

### Export to XML

```bash
# Export all jobs
python run.py export

# Export specific company
python run.py export --company Amazon
```

### Start API Server

```bash
python run.py api
```

API will be available at `http://localhost:5000`

## API Endpoints (Test with Postman)

### 1. Get All Jobs

```
GET http://localhost:5000/api/jobs
```

### 2. Get Jobs by Company

```
GET http://localhost:5000/api/jobs/Amazon
GET http://localhost:5000/api/jobs/Accenture
GET http://localhost:5000/api/jobs/JLL
```

### 3. Get Statistics

```
GET http://localhost:5000/api/stats
```

### 4. Export XML (All Jobs)

```
GET http://localhost:5000/api/export/xml
```

### 5. Export XML (By Company)

```
GET http://localhost:5000/api/export/xml/Amazon
```

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

## Database Location

SQLite database: `data/jobs.db`

You can view it directly using:

- DB Browser for SQLite
- sqlite3 CLI: `sqlite3 data/jobs.db`
- Any SQLite client

## Features Implemented

✅ **Two Scraping Runs**: Run `python run.py scrape` multiple times  
✅ **XML Output**: Exports in Scoutit schema format  
✅ **Stable external_id**: MD5 hash based on company + job ID  
✅ **Valid apply URLs**: Direct links to job applications  
✅ **No Fabricated Data**: Empty fields left blank  
✅ **Zero-Job Detection**: Logs when no jobs found  
✅ **Error Handling**: Logs failures with error messages  
✅ **API for Validation**: View job counts and data via REST API

## Testing with Postman

1. Start the API: `python run.py api`
2. Import these endpoints into Postman:
   - `GET http://localhost:5000/api/jobs`
   - `GET http://localhost:5000/api/stats`
   - `GET http://localhost:5000/api/jobs/Amazon`
   - `GET http://localhost:5000/api/export/xml`

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

### Chrome Driver Issues

```bash
pip install --upgrade webdriver-manager
```

### Permission Errors

```bash
chmod +x run.py
```

### Database Locked

Close any DB browser connections before running scrapers

## License

MIT License

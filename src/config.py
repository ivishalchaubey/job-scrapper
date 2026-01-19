import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
LOGS_DIR = BASE_DIR / 'logs'
OUTPUT_DIR = BASE_DIR / 'output'

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Database
DATABASE_PATH = DATA_DIR / 'jobs.db'

# Scraper settings
SCRAPE_TIMEOUT = 30
HEADLESS_MODE = True
MAX_PAGES_TO_SCRAPE = 1  # Maximum pages to scrape per company
FETCH_FULL_JOB_DETAILS = True  # Set to True to click into each job for full details (slower)

# Company URLs
COMPANIES = {
    'Amazon': {
        'url': 'https://www.amazon.jobs/en/search?base_query=&loc_query=India&type=area&longitude=77.21676&latitude=28.63141&country=IND',
        'scraper': 'amazon'
    },
    'Accenture': {
        'url': 'https://www.accenture.com/in-en/careers/jobsearch?ct=Ahmedabad%7CBengaluru%7CBhubaneswar%7CChennai%7CCoimbatore%7CGandhinagar%7CGurugram%7CHyderabad%7CIndore%7CJaipur%7CKochi%7CKolkata%7CMumbai%7CNagpur%7CNavi%20Mumbai%7CNew%20Delhi%7CNoida%7CPune%7CThiruvananthapuram',
        'scraper': 'accenture'
    },
    'JLL': {
        'url': 'https://jll.wd1.myworkdayjobs.com/en-GB/jllcareers',
        'scraper': 'jll'
    }
}

# API settings
API_HOST = '0.0.0.0'
API_PORT = 8000 
DEBUG_MODE = True

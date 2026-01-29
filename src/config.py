import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
LOGS_DIR = BASE_DIR / 'logs'
OUTPUT_DIR = BASE_DIR / 'output'

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Database - PostgreSQL
DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'jobs_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}

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
    'AWS': {
        'url': 'https://www.amazon.jobs/en/search?offset=0&result_limit=10&sort=relevant&business_category%5B%5D=amazon-web-services&distanceType=Mi&radius=24km&latitude=&longitude=&loc_group_id=&loc_query=India&base_query=&city=&country=IND&region=&county=&query_options=&',
        'scraper': 'aws'
    },
    'Accenture': {
        'url': 'https://www.accenture.com/in-en/careers/jobsearch?ct=Ahmedabad%7CBengaluru%7CBhubaneswar%7CChennai%7CCoimbatore%7CGandhinagar%7CGurugram%7CHyderabad%7CIndore%7CJaipur%7CKochi%7CKolkata%7CMumbai%7CNagpur%7CNavi%20Mumbai%7CNew%20Delhi%7CNoida%7CPune%7CThiruvananthapuram',
        'scraper': 'accenture'
    },
    'JLL': {
        'url': 'https://jll.wd1.myworkdayjobs.com/en-GB/jllcareers',
        'scraper': 'jll'
    },
    'Bain': {
        'url': 'https://www.bain.com/careers/find-a-role/?filters=offices(275,276,274)%7C',
        'scraper': 'bain'
    },
    'BCG': {
        'url': 'https://careers.bcg.com/global/en/search-results?rk=page-targeted-jobs-page54-prod-ds-Nusa6pGk&sortBy=Most%20relevant',
        'scraper': 'bcg'
    }
}

# API settings
API_HOST = '0.0.0.0'
API_PORT = 8000 
DEBUG_MODE = True

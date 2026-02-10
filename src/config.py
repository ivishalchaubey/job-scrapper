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

# Database type: 'mongodb' or 'postgres'
DB_TYPE = os.getenv('DB_TYPE', 'mongodb')

# MongoDB
MONGO_CONFIG = {
    'uri': os.getenv('MONGO_URI', 'mongodb://localhost:27017'),
    'db_name': os.getenv('MONGO_DB_NAME', 'jobs_db')
}

# PostgreSQL
DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'jobs_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}

# Scraper settings
SCRAPE_TIMEOUT = 30  # WebDriverWait timeout (seconds). Page load timeout should be set to 120 in each scraper.
HEADLESS_MODE = True
MAX_PAGES_TO_SCRAPE = 15  # Maximum pages to scrape per company (15 pages = ~150 jobs for most sites)
FETCH_FULL_JOB_DETAILS = False  # Set to True to click into each job for full details (slower)

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
    },
    'Infosys': {
        'url': 'https://career.infosys.com/jobs?companyhiringtype=IL&countrycode=IN',
        'scraper': 'infosys'
    },
    "L'Oreal": {
        'url': 'https://careers.loreal.com/en_US/jobs/SearchJobs/?3_110_3=18031',
        'scraper': 'loreal'
    },
    'Mahindra': {
        'url': 'https://jobs.mahindracareers.com/search/?createNewAlert=false&q=&locationsearch=',
        'scraper': 'mahindra'
    },
    'Marico': {
        'url': 'https://marico.sensehq.com/careers',
        'scraper': 'marico'
    },
    'Meta': {
        'url': 'https://www.metacareers.com/jobs?offices[0]=Mumbai%2C%20India&offices[1]=Gurgaon%2C%20India&offices[2]=Bangalore%2C%20India',
        'scraper': 'meta'
    },
    'Microsoft': {
        'url': 'https://jobs.careers.microsoft.com/global/en/search?l=en_us&pg=1&pgSz=20&o=Relevance&flt=true&ref=cms&lc=India',
        'scraper': 'microsoft'
    },
    'Morgan Stanley': {
        'url': 'https://morganstanley.eightfold.ai/careers?query=&location=India&pid=549795398771&sort_by=relevance',
        'scraper': 'morganstanley'
    },
    'Nestle': {
        'url': 'https://www.nestle.in/jobs/search-jobs?keyword=&country=IN',
        'scraper': 'nestle'
    },
    'Nvidia': {
        'url': 'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite?Location_Country=bc33aa3152ec42d4995f4791a106ed09',
        'scraper': 'nvidia'
    },
    'Samsung': {
        'url': 'https://sec.wd3.myworkdayjobs.com/Samsung_Careers?locations=0c974e8c1228010867596ab21b3c3469',
        'scraper': 'samsung'
    },
    'Swiggy': {
        'url': 'https://careers.swiggy.com/#/careers?src=careers',
        'scraper': 'swiggy'
    },
    'TCS': {
        'url': 'https://ibegin.tcs.com/iBegin/jobs/search',
        'scraper': 'tcs'
    },
    'Tata Consumer': {
        'url': 'https://careers.tataconsumer.com/search/?createNewAlert=false&q=&locationsearch=India',
        'scraper': 'tataconsumer'
    },
    'Tech Mahindra': {
        'url': 'https://careers.techmahindra.com/Currentopportunity.aspx#Advance',
        'scraper': 'techmahindra'
    },
    'Varun Beverages': {
        'url': 'https://rjcorphcm-iacbiz.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs?location=India&locationId=300000000489931&locationLevel=country&mode=location',
        'scraper': 'varunbeverages'
    },
    'Wipro': {
        'url': 'https://careers.wipro.com/search/?q=&locationsearch=India&searchResultView=LIST',
        'scraper': 'wipro'
    },
    'PepsiCo': {
        'url': 'https://www.pepsicojobs.com/main/jobs?stretchUnit=MILES&stretch=10&location=India&woe=12&regionCode=IN',
        'scraper': 'pepsico'
    },
    'BookMyShow': {
        'url': 'https://bookmyshow.hire.trakstar.com/',
        'scraper': 'bookmyshow'
    },
    'Abbott': {
        'url': 'https://www.jobs.abbott/us/en/search-results?qcountry=India',
        'scraper': 'abbott'
    }
}

# API settings
API_HOST = '0.0.0.0'
API_PORT = 8000 
DEBUG_MODE = True

#!/usr/bin/env python3
"""
Main runner script for job scraping system
"""
import argparse
from datetime import datetime
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent))

from src.database import get_database
from src.scrapers.amazon_scraper import AmazonScraper
from src.scrapers.aws_scraper import AWSScraper
from src.scrapers.accenture_scraper import AccentureScraper
from src.scrapers.jll_scraper import JLLScraper
from src.scrapers.bain_scraper import BainScraper
from src.scrapers.bcg_scraper import BCGScraper
from src.scrapers.infosys_scraper import InfosysScraper
from src.scrapers.loreal_scraper import LorealScraper
from src.scrapers.mahindra_scraper import MahindraScraper
from src.scrapers.marico_scraper import MaricoScraper
from src.scrapers.meta_scraper import MetaScraper
from src.scrapers.microsoft_scraper import MicrosoftScraper
from src.scrapers.morganstanley_scraper import MorganStanleyScraper
from src.scrapers.nestle_scraper import NestleScraper
from src.scrapers.nvidia_scraper import NvidiaScraper
from src.scrapers.samsung_scraper import SamsungScraper
from src.scrapers.swiggy_scraper import SwiggyScraper
from src.scrapers.tcs_scraper import TCSScraper
from src.scrapers.tataconsumer_scraper import TataConsumerScraper
from src.scrapers.techmahindra_scraper import TechMahindraScraper
from src.scrapers.varunbeverages_scraper import VarunBeveragesScraper
from src.scrapers.wipro_scraper import WiproScraper
from src.scrapers.pepsico_scraper import PepsiCoScraper
from src.scrapers.bookmyshow_scraper import BookMyShowScraper
from src.scrapers.abbott_scraper import AbbottScraper
from src.utils.xml_generator import XMLGenerator
from src.utils.logger import setup_logger
from src.config import LOGS_DIR

# Setup logger
log_file = LOGS_DIR / f'scraper_{datetime.now().strftime("%Y%m%d")}.log'
logger = setup_logger('main', log_file)

# Map of company names to their scraper classes
SCRAPER_MAP = {
    'amazon': AmazonScraper,
    'aws': AWSScraper,
    'accenture': AccentureScraper,
    'jll': JLLScraper,
    'bain': BainScraper,
    'bcg': BCGScraper,
    'infosys': InfosysScraper,
    'loreal': LorealScraper,
    'mahindra': MahindraScraper,
    'marico': MaricoScraper,
    'meta': MetaScraper,
    'microsoft': MicrosoftScraper,
    'morgan stanley': MorganStanleyScraper,
    'nestle': NestleScraper,
    'nvidia': NvidiaScraper,
    'samsung': SamsungScraper,
    'swiggy': SwiggyScraper,
    'tcs': TCSScraper,
    'tata consumer': TataConsumerScraper,
    'tech mahindra': TechMahindraScraper,
    'varun beverages': VarunBeveragesScraper,
    'wipro': WiproScraper,
    'pepsico': PepsiCoScraper,
    'bookmyshow': BookMyShowScraper,
    'abbott': AbbottScraper,
}

ALL_COMPANY_CHOICES = [
    'Amazon', 'AWS', 'Accenture', 'JLL', 'Bain', 'BCG',
    'Infosys', 'Loreal', 'Mahindra', 'Marico', 'Meta', 'Microsoft',
    'Morgan Stanley', 'Nestle', 'Nvidia', 'Samsung', 'Swiggy', 'TCS',
    'Tata Consumer', 'Tech Mahindra', 'Varun Beverages', 'Wipro',
    'PepsiCo', 'BookMyShow', 'Abbott'
]

def scrape_company(company_name):
    """Scrape jobs for a specific company"""
    db = get_database()

    try:
        scraper_class = SCRAPER_MAP.get(company_name.lower())
        if not scraper_class:
            logger.error(f"Unknown company: {company_name}")
            return False

        scraper = scraper_class()
        logger.info(f"Starting scrape for {company_name}")

        # Scrape jobs
        jobs = scraper.scrape()

        if not jobs:
            logger.warning(f"No jobs found for {company_name}")
            db.log_scraping_run(company_name, 0, 'success', 'No jobs found')
            return True

        # Save to database
        for job in jobs:
            db.insert_job(job)

        logger.info(f"Saved {len(jobs)} jobs for {company_name}")
        db.log_scraping_run(company_name, len(jobs), 'success')

        return True

    except Exception as e:
        logger.error(f"Error scraping {company_name}: {str(e)}")
        db.log_scraping_run(company_name, 0, 'failed', str(e))
        return False

def scrape_all():
    """Scrape all companies"""
    results = {}

    logger.info("Starting scrape for all companies")

    for company in ALL_COMPANY_CHOICES:
        success = scrape_company(company)
        results[company] = 'Success' if success else 'Failed'
        logger.info(f"{company}: {results[company]}")

    logger.info("Scraping completed for all companies")
    return results

def export_xml(company=None):
    """Export jobs to XML"""
    xml_gen = XMLGenerator()

    try:
        if company:
            xml_file = xml_gen.generate_company_xml(company)
            logger.info(f"Exported {company} jobs to XML: {xml_file}")
        else:
            xml_file = xml_gen.generate_xml()
            logger.info(f"Exported all jobs to XML: {xml_file}")

        return xml_file
    except Exception as e:
        logger.error(f"Error exporting XML: {str(e)}")
        return None

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Job Scraper System')
    parser.add_argument('action', choices=['scrape', 'export', 'api', 'clean'],
                       help='Action to perform')
    parser.add_argument('--company', choices=ALL_COMPANY_CHOICES,
                       help='Specific company to scrape/export')

    args = parser.parse_args()

    if args.action == 'scrape':
        if args.company:
            scrape_company(args.company)
        else:
            scrape_all()

    elif args.action == 'export':
        export_xml(args.company)

    elif args.action == 'clean':
        db = get_database()
        logger.info("Cleaning database...")
        db.drop_all_tables()
        logger.info("Database cleaned successfully")
        print("Database cleaned and reset successfully!")

    elif args.action == 'api':
        from src.api.app import app
        from src.config import API_HOST, API_PORT, DEBUG_MODE
        logger.info(f"Starting API server on {API_HOST}:{API_PORT}")
        app.run(host=API_HOST, port=API_PORT, debug=DEBUG_MODE)

if __name__ == '__main__':
    main()

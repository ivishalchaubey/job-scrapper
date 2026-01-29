#!/usr/bin/env python3
"""
Main runner script for job scraping system
"""
import argparse
from datetime import datetime
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent))

from src.database.db import JobDatabase
from src.scrapers.amazon_scraper import AmazonScraper
from src.scrapers.aws_scraper import AWSScraper
from src.scrapers.accenture_scraper import AccentureScraper
from src.scrapers.jll_scraper import JLLScraper
from src.scrapers.bain_scraper import BainScraper
from src.scrapers.bcg_scraper import BCGScraper
from src.utils.xml_generator import XMLGenerator
from src.utils.logger import setup_logger
from src.config import LOGS_DIR

# Setup logger
log_file = LOGS_DIR / f'scraper_{datetime.now().strftime("%Y%m%d")}.log'
logger = setup_logger('main', log_file)

def scrape_company(company_name):
    """Scrape jobs for a specific company"""
    db = JobDatabase()
    
    try:
        # Select scraper
        if company_name.lower() == 'amazon':
            scraper = AmazonScraper()
        elif company_name.lower() == 'aws':
            scraper = AWSScraper()
        elif company_name.lower() == 'accenture':
            scraper = AccentureScraper()
        elif company_name.lower() == 'jll':
            scraper = JLLScraper()
        elif company_name.lower() == 'bain':
            scraper = BainScraper()
        elif company_name.lower() == 'bcg':
            scraper = BCGScraper()
        else:
            logger.error(f"Unknown company: {company_name}")
            return False
        
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
    companies = ['Amazon', 'AWS', 'Accenture', 'JLL']
    results = {}
    
    logger.info("Starting scrape for all companies")
    
    for company in companies:
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
    parser.add_argument('--company', choices=['Amazon', 'AWS', 'Accenture', 'JLL', 'Bain', 'BCG'],
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
        db = JobDatabase()
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

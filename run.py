#!/usr/bin/env python3
"""
Main runner script for job scraping system.
Can be used standalone (CLI) or through Django management.
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.append(str(Path(__file__).resolve().parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from scrapers.registry import SCRAPER_MAP, ALL_COMPANY_CHOICES
from apps.data_store import services as job_service
from core.logging import setup_logger
from config.scraper import LOGS_DIR

log_file = LOGS_DIR / f'scraper_{datetime.now().strftime("%Y%m%d")}.log'
logger = setup_logger('main', log_file)


def scrape_company(company_name):
    """Scrape jobs for a specific company"""
    start_time = time.time()

    result = {
        'company': company_name,
        'success': False,
        'jobs_count': 0,
        'error': None,
        'duration': 0
    }

    try:
        scraper_class = SCRAPER_MAP.get(company_name.lower())
        if not scraper_class:
            logger.error(f"Unknown company: {company_name}")
            result['error'] = "Unknown company"
            return result

        scraper = scraper_class()
        logger.info(f"Starting scrape for {company_name}")

        jobs = scraper.scrape()

        if not jobs:
            logger.warning(f"No jobs found for {company_name}")
            job_service.create_scraping_run(
                company_name=company_name, jobs_scraped=0,
                status='success', error_message='No jobs found'
            )
            result['success'] = True
            result['duration'] = time.time() - start_time
            return result

        job_service.delete_company_jobs(company_name)
        for job_data in jobs:
            job_service.upsert_job({
                'external_id': job_data['external_id'],
                'company_name': job_data.get('company_name', company_name),
                'title': job_data.get('title', ''),
                'description': job_data.get('description', ''),
                'location': job_data.get('location', ''),
                'city': job_data.get('city', ''),
                'state': job_data.get('state', ''),
                'country': job_data.get('country', ''),
                'employment_type': job_data.get('employment_type', ''),
                'department': job_data.get('department', ''),
                'apply_url': job_data.get('apply_url', ''),
                'posted_date': job_data.get('posted_date', ''),
                'job_function': job_data.get('job_function', ''),
                'experience_level': job_data.get('experience_level', ''),
                'salary_range': job_data.get('salary_range', ''),
                'remote_type': job_data.get('remote_type', ''),
                'status': job_data.get('status', 'active'),
            })

        logger.info(f"Saved {len(jobs)} jobs for {company_name}")
        job_service.create_scraping_run(
            company_name=company_name, jobs_scraped=len(jobs), status='success'
        )

        result['success'] = True
        result['jobs_count'] = len(jobs)
        result['duration'] = time.time() - start_time
        return result

    except Exception as e:
        logger.error(f"Error scraping {company_name}: {str(e)}")
        job_service.create_scraping_run(
            company_name=company_name, jobs_scraped=0,
            status='failed', error_message=str(e)
        )
        result['error'] = str(e)
        result['duration'] = time.time() - start_time
        return result


def scrape_all_parallel(max_workers=10, per_scraper_timeout=180):
    """Scrape all companies using multithreading for maximum speed."""
    total = len(ALL_COMPANY_CHOICES)
    logger.info(f"Starting parallel scrape for all {total} companies with {max_workers} workers (timeout={per_scraper_timeout}s)")

    start_time = time.time()
    results = []
    print_lock = Lock()
    completed_count = [0]

    def scrape_with_progress(company):
        result = scrape_company(company)
        with print_lock:
            completed_count[0] += 1
            status = "+" if result['success'] else "x"
            elapsed = time.time() - start_time
            print(f"[{completed_count[0]}/{total}] {status} {result['company']}: {result['jobs_count']} jobs ({result['duration']:.1f}s) | elapsed {elapsed:.0f}s")
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_company = {
            executor.submit(scrape_with_progress, company): company
            for company in ALL_COMPANY_CHOICES
        }

        for future in as_completed(future_to_company):
            company = future_to_company[future]
            try:
                result = future.result(timeout=per_scraper_timeout)
                results.append(result)
            except Exception as e:
                error_msg = f"Timeout ({per_scraper_timeout}s)" if 'TimeoutError' in type(e).__name__ else str(e)
                logger.error(f"Exception scraping {company}: {error_msg}")
                with print_lock:
                    completed_count[0] += 1
                    print(f"[{completed_count[0]}/{total}] x {company}: TIMEOUT/ERROR ({error_msg[:80]})")
                results.append({
                    'company': company, 'success': False, 'jobs_count': 0,
                    'error': error_msg, 'duration': per_scraper_timeout
                })

    total_time = time.time() - start_time
    total_jobs = sum(r['jobs_count'] for r in results)
    passed = len([r for r in results if r['success']])

    print(f"\n{'='*60}")
    print(f"COMPLETED: {passed}/{total} companies | {total_jobs:,} total jobs | {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"{'='*60}\n")

    logger.info(f"Scraping completed for all companies in {total_time:.2f} seconds")
    return results


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Job Scraper System - Fast multithreaded scraping with analytics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py scrape                    # Scrape all companies (10 workers)
  python run.py scrape --workers 15       # Scrape all with 15 workers
  python run.py scrape --company Google   # Scrape single company
  python run.py scrape --timeout 120      # Custom per-scraper timeout
  python run.py server                    # Start Django server
        """
    )
    parser.add_argument('action', choices=['scrape', 'server', 'clean'],
                       help='Action to perform')
    parser.add_argument('--company', choices=ALL_COMPANY_CHOICES,
                       help='Specific company to scrape')
    parser.add_argument('--workers', type=int, default=10,
                       help='Number of parallel workers (default: 10)')
    parser.add_argument('--timeout', type=int, default=180,
                       help='Per-scraper timeout in seconds (default: 180)')

    args = parser.parse_args()

    if args.action == 'scrape':
        if args.company:
            result = scrape_company(args.company)
            print(f"\n{'='*60}")
            print(f"Company: {result['company']}")
            print(f"Status: {'+ Success' if result['success'] else 'x Failed'}")
            print(f"Jobs: {result['jobs_count']}")
            print(f"Duration: {result['duration']:.2f}s")
            if result['error']:
                print(f"Error: {result['error']}")
            print(f"{'='*60}\n")
        else:
            print(f"\n{'='*60}")
            print(f"PARALLEL SCRAPING - {len(ALL_COMPANY_CHOICES)} COMPANIES")
            print(f"Workers: {args.workers} | Timeout: {args.timeout}s per scraper")
            print(f"{'='*60}\n")
            scrape_all_parallel(max_workers=args.workers, per_scraper_timeout=args.timeout)

    elif args.action == 'clean':
        job_service.delete_all_jobs()
        logger.info("Database cleaned successfully")
        print("Database cleaned and reset successfully!")

    elif args.action == 'server':
        os.system(f'{sys.executable} manage.py runserver 0.0.0.0:8000')


if __name__ == '__main__':
    main()

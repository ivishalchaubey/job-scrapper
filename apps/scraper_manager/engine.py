import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from apps.data_store import services as job_service
from apps.scraper_manager import services as scraping_service
from core.logging import setup_logger

logger = setup_logger(__name__)

_active_tasks = {}


def run_scrape_task(task_id, companies, max_workers=10, timeout=180):
    scraping_service.update_task(task_id, status='running', total_companies=len(companies))

    executor = ThreadPoolExecutor(max_workers=max_workers)
    _active_tasks[task_id] = executor

    try:
        future_to_company = {
            executor.submit(_scrape_single, company, timeout): company
            for company in companies
        }

        for future in as_completed(future_to_company):
            company = future_to_company[future]
            try:
                result = future.result(timeout=timeout + 30)  # extra buffer beyond internal timeout
            except Exception as e:
                result = {
                    'company': company,
                    'success': False,
                    'jobs_count': 0,
                    'error': str(e),
                }

            task = scraping_service.get_task(task_id)
            if task and task.get('status') == 'cancelled':
                executor.shutdown(wait=False, cancel_futures=True)
                break

            scraping_service.increment_task_progress(
                task_id, result.get('jobs_count', 0), result
            )

        task = scraping_service.get_task(task_id)
        if task and task.get('status') != 'cancelled':
            scraping_service.update_task(
                task_id, status='completed',
                finished_at=datetime.now(timezone.utc),
            )
        else:
            scraping_service.update_task(
                task_id, finished_at=datetime.now(timezone.utc),
            )
    except Exception as e:
        scraping_service.update_task(
            task_id, status='failed',
            error_message=str(e),
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        _active_tasks.pop(task_id, None)
        executor.shutdown(wait=False)


def _scrape_with_timeout(scraper, timeout_seconds):
    """Run scraper.scrape() with a hard timeout using a daemon thread."""
    result_holder = [None]
    error_holder = [None]

    def target():
        try:
            result_holder[0] = scraper.scrape()
        except Exception as e:
            error_holder[0] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)

    if t.is_alive():
        # Try to quit the driver if possible
        try:
            if hasattr(scraper, 'driver') and scraper.driver:
                scraper.driver.quit()
        except Exception:
            pass
        raise TimeoutError(f'Scraper timed out after {timeout_seconds}s')

    if error_holder[0]:
        raise error_holder[0]

    return result_holder[0]


def _scrape_single(company_name, timeout=180):
    from scrapers.registry import SCRAPER_MAP

    start_time = time.time()
    result = {
        'company': company_name,
        'success': False,
        'jobs_count': 0,
        'error': None,
        'duration': 0,
    }

    try:
        scraper_class = SCRAPER_MAP.get(company_name.lower())
        if not scraper_class:
            result['error'] = 'Unknown company'
            return result

        scraper = scraper_class()
        jobs = _scrape_with_timeout(scraper, timeout)

        if jobs:
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

        job_service.create_scraping_run(
            company_name=company_name,
            jobs_scraped=len(jobs) if jobs else 0,
            status='success',
            error_message='No jobs found' if not jobs else None,
        )

        result['success'] = True
        result['jobs_count'] = len(jobs) if jobs else 0
    except TimeoutError as e:
        result['error'] = str(e)
        job_service.create_scraping_run(
            company_name=company_name,
            jobs_scraped=0,
            status='failed',
            error_message=str(e),
        )
    except Exception as e:
        result['error'] = str(e)
        job_service.create_scraping_run(
            company_name=company_name,
            jobs_scraped=0,
            status='failed',
            error_message=str(e),
        )

    result['duration'] = round(time.time() - start_time, 1)
    return result


def start_scrape(companies=None, max_workers=10, timeout=180):
    from scrapers.registry import ALL_COMPANY_CHOICES

    if companies is None:
        companies = ALL_COMPANY_CHOICES

    company_name = companies[0] if len(companies) == 1 else ''
    task = scraping_service.create_task(
        company_name=company_name,
        total_companies=len(companies),
    )

    thread = threading.Thread(
        target=run_scrape_task,
        args=(task['task_id'], companies, max_workers, timeout),
        daemon=True,
    )
    thread.start()

    return task


def cancel_scrape(task_id):
    task = scraping_service.get_task(task_id)
    if task and task.get('status') == 'running':
        scraping_service.update_task(
            task_id, status='cancelled',
            finished_at=datetime.now(timezone.utc),
        )
        executor = _active_tasks.get(task_id)
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)
        return True
    return False

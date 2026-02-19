import threading
import time
from datetime import datetime, timezone
from queue import Queue

from apps.data_store import services as job_service
from apps.scraper_manager import services as scraping_service
from core.logging import setup_logger

logger = setup_logger(__name__)

_active_tasks = {}


def run_scrape_task(task_id, companies, max_workers=10, max_pages=1):
    scraping_service.update_task(task_id, status='running', total_companies=len(companies))

    cancel_event = threading.Event()
    _active_tasks[task_id] = cancel_event

    result_queue = Queue()
    semaphore = threading.Semaphore(max_workers)

    def worker(company):
        try:
            if cancel_event.is_set():
                result_queue.put({
                    'company': company, 'success': False,
                    'jobs_count': 0, 'error': 'Cancelled', 'duration': 0,
                })
                return
            result = _scrape_single(company, max_pages)
            result_queue.put(result)
        except Exception as e:
            result_queue.put({
                'company': company, 'success': False,
                'jobs_count': 0, 'error': str(e), 'duration': 0,
            })
        finally:
            semaphore.release()

    try:
        threads = []
        for company in companies:
            if cancel_event.is_set():
                break
            semaphore.acquire()
            t = threading.Thread(target=worker, args=(company,), daemon=True)
            t.start()
            threads.append(t)

        completed = 0
        total = len(threads)
        while completed < total:
            result = result_queue.get()
            completed += 1

            task = scraping_service.get_task(task_id)
            if task and task.get('status') == 'cancelled':
                cancel_event.set()
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


def _scrape_single(company_name, max_pages=1):
    from scrapers.registry import SCRAPER_MAP

    effective_pages = 999 if max_pages == 0 else max_pages
    logger.info(f"_scrape_single: {company_name} max_pages={max_pages} effective={effective_pages}")
    start_time = time.time()
    result = {
        'company': company_name,
        'success': False,
        'jobs_count': 0,
        'max_pages': effective_pages,
        'error': None,
        'duration': 0,
    }

    try:
        scraper_class = SCRAPER_MAP.get(company_name.lower())
        if not scraper_class:
            result['error'] = 'Unknown company'
            return result

        scraper = scraper_class()
        jobs = scraper.scrape(max_pages=effective_pages)

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


def start_scrape(companies=None, max_workers=10, max_pages=1, **kwargs):
    from scrapers.registry import ALL_COMPANY_CHOICES

    if companies is None:
        companies = ALL_COMPANY_CHOICES

    logger.info(f"start_scrape: {len(companies)} companies, max_workers={max_workers}, max_pages={max_pages}")

    company_name = companies[0] if len(companies) == 1 else ''
    task = scraping_service.create_task(
        company_name=company_name,
        total_companies=len(companies),
        max_pages=max_pages,
    )

    thread = threading.Thread(
        target=run_scrape_task,
        args=(task['task_id'], companies, max_workers, max_pages),
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
        cancel_event = _active_tasks.get(task_id)
        if cancel_event:
            cancel_event.set()
        return True
    return False

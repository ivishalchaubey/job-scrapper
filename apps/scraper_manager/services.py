import uuid
from datetime import datetime, timezone
from core.db import get_collection

SCRAPE_TASKS = 'scrape_tasks'


def create_task(company_name='', total_companies=0, max_pages=1):
    coll = get_collection(SCRAPE_TASKS)
    task_id = str(uuid.uuid4())
    doc = {
        'task_id': task_id,
        'company_name': company_name,
        'status': 'pending',
        'total_companies': total_companies,
        'completed_companies': 0,
        'total_jobs_found': 0,
        'max_pages': max_pages,
        'started_at': datetime.now(timezone.utc),
        'finished_at': None,
        'results': {},
        'error_message': '',
    }
    coll.insert_one(doc)
    doc['id'] = str(doc.pop('_id'))
    doc['progress_percent'] = 0
    return doc


def get_task(task_id):
    coll = get_collection(SCRAPE_TASKS)
    doc = coll.find_one({'task_id': task_id})
    if doc:
        doc['id'] = str(doc.pop('_id'))
        total = doc.get('total_companies', 0)
        completed = doc.get('completed_companies', 0)
        doc['progress_percent'] = round((completed / total) * 100, 1) if total > 0 else 0
    return doc


def update_task(task_id, **updates):
    coll = get_collection(SCRAPE_TASKS)
    coll.update_one({'task_id': task_id}, {'$set': updates})


def increment_task_progress(task_id, jobs_count, company_result):
    coll = get_collection(SCRAPE_TASKS)
    company_name = company_result.get('company', 'unknown')
    coll.update_one(
        {'task_id': task_id},
        {
            '$inc': {
                'completed_companies': 1,
                'total_jobs_found': jobs_count,
            },
            '$set': {
                f'results.{company_name}': company_result
            }
        }
    )


def list_tasks(limit=50):
    coll = get_collection(SCRAPE_TASKS)
    tasks = list(coll.find().sort('started_at', -1).limit(limit))
    for t in tasks:
        t['id'] = str(t.pop('_id'))
        total = t.get('total_companies', 0)
        completed = t.get('completed_companies', 0)
        t['progress_percent'] = round((completed / total) * 100, 1) if total > 0 else 0
    return tasks


def cleanup_stale_tasks(max_age_minutes=30):
    """Mark any running/pending tasks older than max_age_minutes as failed."""
    from datetime import timedelta
    coll = get_collection(SCRAPE_TASKS)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    result = coll.update_many(
        {
            'status': {'$in': ['running', 'pending']},
            'started_at': {'$lt': cutoff},
        },
        {'$set': {
            'status': 'failed',
            'error_message': f'Timed out (stale after {max_age_minutes}m)',
            'finished_at': datetime.now(timezone.utc),
        }}
    )
    return result.modified_count

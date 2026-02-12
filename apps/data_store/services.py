from datetime import datetime, timezone
from core.db import get_collection

JOBS = 'jobs'
SCRAPING_RUNS = 'scraping_runs'


def upsert_job(job_data):
    coll = get_collection(JOBS)
    now = datetime.now(timezone.utc)
    job_data['updated_at'] = now
    return coll.update_one(
        {'external_id': job_data['external_id']},
        {'$set': job_data, '$setOnInsert': {'created_at': now}},
        upsert=True
    )


def get_jobs(filters=None, search=None, ordering='-updated_at', page=1, page_size=50):
    coll = get_collection(JOBS)
    query = {'status': 'active'}

    if filters:
        for key, value in filters.items():
            if value:
                if key == 'company_name':
                    query[key] = {'$regex': f'^{value}$', '$options': 'i'}
                else:
                    query[key] = {'$regex': value, '$options': 'i'}

    if search:
        query['$or'] = [
            {'title': {'$regex': search, '$options': 'i'}},
            {'company_name': {'$regex': search, '$options': 'i'}},
            {'city': {'$regex': search, '$options': 'i'}},
            {'department': {'$regex': search, '$options': 'i'}},
        ]

    sort_field = ordering.lstrip('-')
    sort_dir = -1 if ordering.startswith('-') else 1

    total = coll.count_documents(query)
    skip = (page - 1) * page_size
    cursor = coll.find(query).sort(sort_field, sort_dir).skip(skip).limit(page_size)

    jobs = []
    for doc in cursor:
        doc['id'] = str(doc.pop('_id'))
        jobs.append(doc)

    return jobs, total


def get_job_by_id(job_id):
    from bson import ObjectId
    coll = get_collection(JOBS)
    doc = coll.find_one({'_id': ObjectId(job_id)})
    if doc:
        doc['id'] = str(doc.pop('_id'))
    return doc


def get_dashboard_stats():
    jobs_coll = get_collection(JOBS)
    runs_coll = get_collection(SCRAPING_RUNS)

    total_jobs = jobs_coll.count_documents({'status': 'active'})

    pipeline = [
        {'$match': {'status': 'active'}},
        {'$group': {'_id': '$company_name'}},
        {'$count': 'count'}
    ]
    result = list(jobs_coll.aggregate(pipeline))
    active_companies = result[0]['count'] if result else 0

    recent_runs = list(runs_coll.find().sort('run_date', -1).limit(100))
    total_runs = len(recent_runs)
    successful = sum(1 for r in recent_runs if r.get('status') == 'success')
    success_rate = round((successful / total_runs * 100), 1) if total_runs > 0 else 0

    last_run = runs_coll.find_one(sort=[('run_date', -1)])
    last_scrape = last_run['run_date'] if last_run else None

    return {
        'total_jobs': total_jobs,
        'active_companies': active_companies,
        'total_scrapers': 275,
        'success_rate': success_rate,
        'last_scrape': last_scrape,
    }


def get_company_stats():
    coll = get_collection(JOBS)
    pipeline = [
        {'$match': {'status': 'active'}},
        {'$group': {
            '_id': '$company_name',
            'count': {'$sum': 1},
            'last_scraped': {'$max': '$updated_at'},
        }},
        {'$sort': {'count': -1}},
        {'$project': {
            '_id': 0,
            'company_name': '$_id',
            'count': 1,
            'last_scraped': 1,
        }}
    ]
    return list(coll.aggregate(pipeline))


def create_scraping_run(company_name, jobs_scraped, status, error_message=None):
    coll = get_collection(SCRAPING_RUNS)
    doc = {
        'company_name': company_name,
        'run_date': datetime.now(timezone.utc),
        'jobs_scraped': jobs_scraped,
        'status': status,
        'error_message': error_message,
    }
    coll.update_one(
        {'company_name': company_name},
        {'$set': doc},
        upsert=True,
    )
    return doc


def get_scraping_history(limit=50):
    coll = get_collection(SCRAPING_RUNS)
    runs = list(coll.find().sort('run_date', -1).limit(limit))
    for r in runs:
        r['id'] = str(r.pop('_id'))
    return runs


def delete_jobs_by_ids(job_ids):
    """Delete jobs by a list of ObjectId strings."""
    from bson import ObjectId
    coll = get_collection(JOBS)
    object_ids = [ObjectId(jid) for jid in job_ids]
    result = coll.delete_many({'_id': {'$in': object_ids}})
    return result.deleted_count


def delete_company_jobs(company_name):
    """Delete all jobs for a specific company before re-scraping."""
    result = get_collection(JOBS).delete_many({'company_name': company_name})
    return result.deleted_count


def delete_all_jobs():
    get_collection(JOBS).delete_many({})
    get_collection(SCRAPING_RUNS).delete_many({})

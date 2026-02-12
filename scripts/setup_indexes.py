from pymongo import ASCENDING, DESCENDING, TEXT
from core.db import get_db


def create_indexes():
    db = get_db()

    jobs = db['jobs']
    jobs.create_index('external_id', unique=True)
    jobs.create_index('company_name')
    jobs.create_index('status')
    jobs.create_index([('title', TEXT), ('company_name', TEXT)])
    jobs.create_index([('updated_at', DESCENDING)])

    runs = db['scraping_runs']
    runs.create_index([('company_name', ASCENDING)])
    runs.create_index([('run_date', DESCENDING)])

    tasks = db['scrape_tasks']
    tasks.create_index('task_id', unique=True)
    tasks.create_index('status')
    tasks.create_index([('started_at', DESCENDING)])

    print("MongoDB indexes created successfully.")


if __name__ == '__main__':
    create_indexes()

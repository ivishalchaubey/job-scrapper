from datetime import datetime
from pymongo import MongoClient, DESCENDING

from src.database.base import BaseJobDatabase
from src.config import MONGO_CONFIG
from src.utils.logger import setup_logger

logger = setup_logger('mongo_database')


class MongoJobDatabase(BaseJobDatabase):
    def __init__(self):
        self.client = MongoClient(MONGO_CONFIG['uri'])
        self.db = self.client[MONGO_CONFIG['db_name']]
        self.jobs = self.db['jobs']
        self.scraping_runs = self.db['scraping_runs']
        self.init_database()

    def init_database(self):
        """Create indexes for the jobs and scraping_runs collections."""
        try:
            self.jobs.create_index('external_id', unique=True)
            self.jobs.create_index('company_name')
            logger.info("MongoDB indexes initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing MongoDB indexes: {str(e)}")
            raise

    def insert_job(self, job_data):
        """Upsert a job by external_id."""
        try:
            doc = {
                'external_id': job_data['external_id'],
                'company_name': job_data['company_name'],
                'title': job_data.get('title'),
                'description': job_data.get('description'),
                'location': job_data.get('location'),
                'city': job_data.get('city'),
                'state': job_data.get('state'),
                'country': job_data.get('country'),
                'employment_type': job_data.get('employment_type'),
                'department': job_data.get('department'),
                'apply_url': job_data.get('apply_url'),
                'posted_date': job_data.get('posted_date'),
                'job_function': job_data.get('job_function'),
                'experience_level': job_data.get('experience_level'),
                'salary_range': job_data.get('salary_range'),
                'remote_type': job_data.get('remote_type'),
                'status': job_data.get('status', 'active'),
                'updated_at': datetime.now(),
            }

            result = self.jobs.update_one(
                {'external_id': job_data['external_id']},
                {'$set': doc, '$setOnInsert': {'created_at': datetime.now()}},
                upsert=True,
            )

            if result.upserted_id:
                logger.info(f"Inserted new job: {job_data['external_id']}")
            else:
                logger.info(f"Updated job: {job_data['external_id']}")
        except Exception as e:
            logger.error(f"Error inserting job {job_data.get('external_id')}: {str(e)}")
            raise

    def log_scraping_run(self, company_name, jobs_scraped, status='success', error_message=None):
        """Insert a scraping run log entry."""
        self.scraping_runs.insert_one({
            'company_name': company_name,
            'run_date': datetime.now(),
            'jobs_scraped': jobs_scraped,
            'status': status,
            'error_message': error_message,
        })
        logger.info(f"Logged scraping run for {company_name}: {jobs_scraped} jobs, status: {status}")

    def get_all_jobs(self):
        """Get all active jobs."""
        return list(self.jobs.find({'status': 'active'}, {'_id': 0}))

    def get_jobs_by_company(self, company_name):
        """Get active jobs for a specific company."""
        return list(self.jobs.find(
            {'company_name': company_name, 'status': 'active'},
            {'_id': 0},
        ))

    def get_job_counts_by_company(self):
        """Get job counts grouped by company using aggregation."""
        pipeline = [
            {'$match': {'status': 'active'}},
            {'$group': {'_id': '$company_name', 'count': {'$sum': 1}}},
        ]
        results = list(self.jobs.aggregate(pipeline))
        return [{'company_name': r['_id'], 'count': r['count']} for r in results]

    def get_scraping_history(self):
        """Get the 20 most recent scraping runs."""
        return list(
            self.scraping_runs.find({}, {'_id': 0})
            .sort('run_date', DESCENDING)
            .limit(20)
        )

    def drop_all_tables(self):
        """Drop both collections and reinitialize indexes."""
        self.jobs.drop()
        self.scraping_runs.drop()
        logger.info("All collections dropped successfully")
        # Re-assign collection references after drop
        self.jobs = self.db['jobs']
        self.scraping_runs = self.db['scraping_runs']
        self.init_database()

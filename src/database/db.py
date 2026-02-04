import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.database.base import BaseJobDatabase
from src.config import DATABASE_CONFIG
from src.utils.logger import setup_logger

logger = setup_logger('database')

class PostgresJobDatabase(BaseJobDatabase):
    def __init__(self, db_config=None):
        self.db_config = db_config or DATABASE_CONFIG
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        return psycopg.connect(
            host=self.db_config['host'],
            port=self.db_config['port'],
            dbname=self.db_config['database'],
            user=self.db_config['user'],
            password=self.db_config['password']
        )
    
    def init_database(self):
        """Initialize database with schema"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    
                    # Create jobs table following Scoutit's opportunity schema
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS jobs (
                            id SERIAL PRIMARY KEY,
                            external_id TEXT UNIQUE NOT NULL,
                            company_name TEXT NOT NULL,
                            title TEXT NOT NULL,
                            description TEXT,
                            location TEXT,
                            city TEXT,
                            state TEXT,
                            country TEXT,
                            employment_type TEXT,
                            department TEXT,
                            apply_url TEXT NOT NULL,
                            posted_date TEXT,
                            job_function TEXT,
                            experience_level TEXT,
                            salary_range TEXT,
                            remote_type TEXT,
                            status TEXT DEFAULT 'active',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    # Create scraping runs log table
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS scraping_runs (
                            id SERIAL PRIMARY KEY,
                            company_name TEXT NOT NULL,
                            run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            jobs_scraped INTEGER DEFAULT 0,
                            status TEXT,
                            error_message TEXT
                        )
                    ''')
                    
                    # Create index on external_id for faster lookups
                    cursor.execute('''
                        CREATE INDEX IF NOT EXISTS idx_external_id 
                        ON jobs(external_id)
                    ''')
                    
                    # Create index on company_name
                    cursor.execute('''
                        CREATE INDEX IF NOT EXISTS idx_company_name 
                        ON jobs(company_name)
                    ''')
                    
                    conn.commit()
                    logger.info(f"Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            raise
    
    def drop_all_tables(self):
        """Drop all tables - use with caution!"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                
                cursor.execute('DROP TABLE IF EXISTS jobs CASCADE')
                cursor.execute('DROP TABLE IF EXISTS scraping_runs CASCADE')
                
                conn.commit()
                logger.info("All tables dropped successfully")
                
                # Recreate tables
                self.init_database()
    
    def insert_job(self, job_data):
        """Insert or update a job"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                
                # Check if job exists
                cursor.execute('SELECT id FROM jobs WHERE external_id = %s', (job_data['external_id'],))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing job
                    cursor.execute('''
                        UPDATE jobs SET
                            title = %s, description = %s, location = %s, city = %s,
                            state = %s, country = %s, employment_type = %s, department = %s,
                            apply_url = %s, posted_date = %s, job_function = %s,
                            experience_level = %s, salary_range = %s, remote_type = %s,
                            status = %s, updated_at = %s
                        WHERE external_id = %s
                    ''', (
                        job_data.get('title'), job_data.get('description'), 
                        job_data.get('location'), job_data.get('city'),
                        job_data.get('state'), job_data.get('country'),
                        job_data.get('employment_type'), job_data.get('department'),
                        job_data.get('apply_url'), job_data.get('posted_date'),
                        job_data.get('job_function'), job_data.get('experience_level'),
                        job_data.get('salary_range'), job_data.get('remote_type'),
                        job_data.get('status', 'active'), datetime.now(),
                        job_data['external_id']
                    ))
                    logger.info(f"Updated job: {job_data['external_id']}")
                else:
                    # Insert new job
                    cursor.execute('''
                        INSERT INTO jobs (
                            external_id, company_name, title, description, location, city,
                            state, country, employment_type, department, apply_url,
                            posted_date, job_function, experience_level, salary_range,
                            remote_type, status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        job_data['external_id'], job_data['company_name'],
                        job_data.get('title'), job_data.get('description'),
                        job_data.get('location'), job_data.get('city'),
                        job_data.get('state'), job_data.get('country'),
                        job_data.get('employment_type'), job_data.get('department'),
                        job_data.get('apply_url'), job_data.get('posted_date'),
                        job_data.get('job_function'), job_data.get('experience_level'),
                        job_data.get('salary_range'), job_data.get('remote_type'),
                        job_data.get('status', 'active')
                    ))
                    logger.info(f"Inserted new job: {job_data['external_id']}")
                
                conn.commit()
    
    def log_scraping_run(self, company_name, jobs_scraped, status='success', error_message=None):
        """Log scraping run"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO scraping_runs (company_name, jobs_scraped, status, error_message)
                    VALUES (%s, %s, %s, %s)
                ''', (company_name, jobs_scraped, status, error_message))
                conn.commit()
                logger.info(f"Logged scraping run for {company_name}: {jobs_scraped} jobs, status: {status}")
    
    def get_all_jobs(self):
        """Get all jobs"""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute('SELECT * FROM jobs WHERE status = %s', ('active',))
                return cursor.fetchall()
    
    def get_jobs_by_company(self, company_name):
        """Get jobs by company"""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute('SELECT * FROM jobs WHERE company_name = %s AND status = %s', (company_name, 'active'))
                return cursor.fetchall()
    
    def get_job_counts_by_company(self):
        """Get job counts grouped by company"""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute('''
                    SELECT company_name, COUNT(*) as count 
                    FROM jobs 
                    WHERE status = %s
                    GROUP BY company_name
                ''', ('active',))
                return cursor.fetchall()
    
    def get_scraping_history(self):
        """Get scraping run history"""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute('SELECT * FROM scraping_runs ORDER BY run_date DESC LIMIT 20')
                return cursor.fetchall()


# Backward compatibility alias
JobDatabase = PostgresJobDatabase

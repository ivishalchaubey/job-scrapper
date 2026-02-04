from abc import ABC, abstractmethod


class BaseJobDatabase(ABC):
    """Abstract base class for job database implementations."""

    @abstractmethod
    def init_database(self):
        """Initialize database schema/indexes."""
        pass

    @abstractmethod
    def insert_job(self, job_data):
        """Insert or update a job."""
        pass

    @abstractmethod
    def log_scraping_run(self, company_name, jobs_scraped, status='success', error_message=None):
        """Log a scraping run."""
        pass

    @abstractmethod
    def get_all_jobs(self):
        """Get all active jobs."""
        pass

    @abstractmethod
    def get_jobs_by_company(self, company_name):
        """Get active jobs for a specific company."""
        pass

    @abstractmethod
    def get_job_counts_by_company(self):
        """Get job counts grouped by company."""
        pass

    @abstractmethod
    def get_scraping_history(self):
        """Get recent scraping run history."""
        pass

    @abstractmethod
    def drop_all_tables(self):
        """Drop all data and reinitialize."""
        pass

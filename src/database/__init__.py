from src.config import DB_TYPE


def get_database():
    """Factory function that returns the appropriate database implementation."""
    if DB_TYPE == 'mongodb':
        from src.database.mongo_db import MongoJobDatabase
        return MongoJobDatabase()
    else:
        from src.database.db import PostgresJobDatabase
        return PostgresJobDatabase()

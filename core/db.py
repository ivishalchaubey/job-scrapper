import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

_client = None
_db = None


def get_client():
    global _client
    if _client is None:
        uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            _client.admin.command('ping')
        except ConnectionFailure:
            _client = None
            raise
    return _client


def get_db():
    global _db
    if _db is None:
        client = get_client()
        db_name = os.getenv('MONGO_DB_NAME', 'jobs_db')
        _db = client[db_name]
    return _db


def get_collection(name):
    return get_db()[name]


def close_connection():
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None

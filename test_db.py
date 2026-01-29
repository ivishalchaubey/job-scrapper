#!/usr/bin/env python3
"""Test PostgreSQL connection"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent))

from src.database.db import JobDatabase

def test_connection():
    """Test database connection and table creation"""
    try:
        print("Testing PostgreSQL connection...")
        db = JobDatabase()
        print("✓ Database connection successful!")
        print("✓ Tables created/verified!")
        
        # Test a simple query
        print("\nTesting query execution...")
        counts = db.get_job_counts_by_company()
        print(f"✓ Query successful! Found {len(counts)} companies with jobs")
        
        return True
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        print("\nMake sure PostgreSQL is running and credentials in .env are correct")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)

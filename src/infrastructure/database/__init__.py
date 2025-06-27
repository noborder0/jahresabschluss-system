# init_db.py
"""
Initialize the database for Phase 1
"""

import os
import sys

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
os.environ['PYTHONPATH'] = project_root
sys.path.insert(0, project_root)

from src.infrastructure.database.connection import init_db, engine
from src.infrastructure.database.models import Base

if __name__ == "__main__":
    print("Initializing database...")

    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created successfully")

        # You could also run the SQL script here if needed
        # with engine.connect() as conn:
        #     with open('migrations/schema/001_create_tables.sql', 'r') as f:
        #         conn.execute(f.read())

    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        sys.exit(1)
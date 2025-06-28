#!/usr/bin/env python3
"""
Initialize the database for Phase 1
Place this in the project root directory
"""

import os
import sys
import time

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
os.environ['PYTHONPATH'] = project_root
sys.path.insert(0, project_root)

# Import after setting PYTHONPATH
try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("Installing psycopg2-binary...")
    os.system(f"{sys.executable} -m pip install psycopg2-binary")
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from src.infrastructure.database.connection import engine, Base
from src.core.config import settings


def create_database_if_not_exists():
    """Create the database if it doesn't exist"""
    # Parse database URL
    db_url = settings.database_url
    # Extract database name
    db_name = db_url.split('/')[-1]
    # Create connection URL without database
    server_url = '/'.join(db_url.split('/')[:-1]) + '/postgres'

    try:
        # Connect to PostgreSQL server
        conn = psycopg2.connect(server_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
        exists = cursor.fetchone()

        if not exists:
            cursor.execute(f'CREATE DATABASE "{db_name}"')
            print(f"✓ Database '{db_name}' created successfully")
        else:
            print(f"✓ Database '{db_name}' already exists")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Note: Could not create database automatically: {e}")
        print("Please create the database manually if needed")


def update_existing_constraints():
    """Update existing constraints to include new source types"""
    print("\nUpdating database constraints...")

    try:
        with engine.connect() as conn:
            # First, check if we need to update the constraint
            result = conn.exec_driver_sql("""
                SELECT conname 
                FROM pg_constraint 
                WHERE conrelid = 'import_batches'::regclass 
                AND contype = 'c' 
                AND conname LIKE '%source_type%'
            """)

            constraint_exists = result.fetchone()

            if constraint_exists:
                constraint_name = constraint_exists[0]
                print(f"Found constraint: {constraint_name}")

                # Drop the old constraint
                conn.exec_driver_sql(f"ALTER TABLE import_batches DROP CONSTRAINT IF EXISTS {constraint_name}")

                # Add the new constraint with all source types
                conn.exec_driver_sql("""
                    ALTER TABLE import_batches 
                    ADD CONSTRAINT import_batches_source_type_check 
                    CHECK (source_type IN ('BANK_CSV', 'DATEV', 'PDF', 'PAYPAL', 'STRIPE', 'MOLLIE'))
                """)

                print("✓ Constraint updated to include PayPal, Stripe and Mollie")
            else:
                # Add the constraint if it doesn't exist
                conn.exec_driver_sql("""
                    ALTER TABLE import_batches 
                    ADD CONSTRAINT import_batches_source_type_check 
                    CHECK (source_type IN ('BANK_CSV', 'DATEV', 'PDF', 'PAYPAL', 'STRIPE', 'MOLLIE'))
                """)
                print("✓ Constraint added with all source types")

            conn.commit()

    except Exception as e:
        print(f"Note: Could not update constraints: {e}")
        print("This is normal for a fresh installation")


def init_database():
    """Initialize all database tables"""
    print("=== Database Initialization ===")

    # Try to create database first
    create_database_if_not_exists()

    print("\nCreating tables...")

    try:
        # Import all models to ensure they're registered
        from src.infrastructure.database import models

        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✓ All tables created successfully")

        # Update constraints for existing installations
        update_existing_constraints()

        # Run SQL initialization script if exists
        sql_file = os.path.join(project_root, 'migrations/schema/001_create_tables.sql')
        if os.path.exists(sql_file):
            print("\nRunning SQL initialization script...")
            with engine.connect() as conn:
                with open(sql_file, 'r') as f:
                    sql_content = f.read()

                    # Split into individual statements (simple approach)
                    statements = sql_content.split(';')

                    for statement in statements:
                        statement = statement.strip()
                        if statement and not statement.startswith('--'):
                            try:
                                conn.exec_driver_sql(statement + ';')
                            except Exception as e:
                                # Ignore errors for existing objects
                                if 'already exists' not in str(e):
                                    print(f"Warning: {e}")

                    conn.commit()
            print("✓ SQL initialization completed")

    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        raise


if __name__ == "__main__":
    try:
        init_database()
        print("\n✓ Database initialization completed successfully!")
        print("You can now run the application with: python run.py")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
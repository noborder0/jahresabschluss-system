#!/usr/bin/env python3
"""
Initialize the database for Phase 1 & 2
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

                print("✓ Constraint updated to include all payment providers")
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


def run_migrations():
    """Run SQL migration files in order"""
    migrations_dir = os.path.join(project_root, 'migrations', 'schema')

    if not os.path.exists(migrations_dir):
        print(f"Warning: Migrations directory not found: {migrations_dir}")
        return

    # Get all SQL files sorted by name
    sql_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith('.sql')])

    if not sql_files:
        print("No migration files found")
        return

    print(f"\nRunning {len(sql_files)} migration files...")

    with engine.connect() as conn:
        for sql_file in sql_files:
            print(f"  Running {sql_file}...")
            file_path = os.path.join(migrations_dir, sql_file)

            try:
                with open(file_path, 'r') as f:
                    sql_content = f.read()

                    # Split into individual statements
                    statements = sql_content.split(';')

                    for statement in statements:
                        statement = statement.strip()
                        if statement and not statement.startswith('--'):
                            try:
                                conn.exec_driver_sql(statement + ';')
                            except Exception as e:
                                # Ignore errors for existing objects
                                if 'already exists' not in str(e) and 'duplicate key' not in str(e):
                                    print(f"    Warning in {sql_file}: {e}")

                print(f"    ✓ {sql_file} completed")
                conn.commit()

            except Exception as e:
                print(f"    ✗ Error in {sql_file}: {e}")
                raise


def check_ai_services():
    """Check if AI services are properly configured"""
    print("\n=== AI Services Configuration ===")

    # Check Azure
    if settings.azure_form_recognizer_endpoint and settings.azure_form_recognizer_key:
        print("✓ Azure Document Intelligence configured")
        print(f"  Endpoint: {settings.azure_form_recognizer_endpoint}")
        print(f"  Using prebuilt model: {settings.azure_use_prebuilt_model}")
    else:
        print("✗ Azure Document Intelligence not configured")
        print("  Set AZURE_FORM_RECOGNIZER_ENDPOINT and AZURE_FORM_RECOGNIZER_KEY in .env")

    # Check Claude
    if settings.anthropic_api_key:
        print("✓ Claude API configured")
        print(f"  Model: {settings.claude_model}")
        print(f"  Max tokens: {settings.claude_max_tokens}")
    else:
        print("✗ Claude API not configured")
        print("  Set ANTHROPIC_API_KEY in .env")

    # Check Redis
    redis_url = os.getenv('REDIS_URL')
    if redis_url:
        print("✓ Redis configured for caching")
        print(f"  URL: {redis_url}")
    else:
        print("ℹ Redis not configured (optional)")
        print("  Set REDIS_URL in .env for better performance")


def init_database():
    """Initialize all database tables and run migrations"""
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

        # Run migration files
        run_migrations()

    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        raise


if __name__ == "__main__":
    try:
        print("=== Jahresabschluss-System Phase 1 & 2 ===")

        # Initialize database
        init_database()

        # Check AI services
        check_ai_services()

        print("\n✓ Initialization completed successfully!")
        print("\nYou can now run the application with: python run.py")
        print("Or with Docker: docker-compose up")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
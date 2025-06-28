#!/usr/bin/env python3
"""
Fixed startup script for Phase 1 of the Jahresabschluss-System
"""

import os
import sys
import subprocess
from pathlib import Path


# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


def print_colored(message, color=Colors.GREEN):
    """Print colored message"""
    print(f"{color}{message}{Colors.END}")


def setup_environment():
    """Set up Python path and environment variables"""
    project_root = Path(__file__).parent.absolute()

    # Set PYTHONPATH
    os.environ['PYTHONPATH'] = str(project_root)

    # Add to sys.path
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Change to project directory
    os.chdir(project_root)

    return project_root


def check_database_connection():
    """Check if database is accessible"""
    try:
        from src.core.config import settings
        from src.infrastructure.database.connection import engine
        from sqlalchemy import text

        # Use text() for raw SQL
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()

        print_colored("✓ Database connection successful", Colors.GREEN)
        return True
    except Exception as e:
        print_colored(f"✗ Database connection failed: {e}", Colors.RED)
        return False


def initialize_database_if_needed():
    """Initialize database if tables don't exist"""
    try:
        from src.infrastructure.database.connection import engine
        from src.infrastructure.database.models import Base
        from sqlalchemy import inspect

        # Check if tables exist
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        if not tables or 'import_batches' not in tables:
            print_colored("Initializing database tables...", Colors.BLUE)
            Base.metadata.create_all(bind=engine)
            print_colored("✓ Database tables created", Colors.GREEN)
        else:
            print_colored("✓ Database tables already exist", Colors.GREEN)

        return True
    except Exception as e:
        print_colored(f"✗ Database initialization failed: {e}", Colors.RED)
        return False


def start_server():
    """Start the FastAPI server"""
    print_colored("\n=== Starting Jahresabschluss-System Phase 1 ===", Colors.BLUE)
    print(f"Web Interface: {Colors.GREEN}http://localhost:8000{Colors.END}")
    print(f"API Documentation: {Colors.GREEN}http://localhost:8000/docs{Colors.END}")
    print(f"\nPress {Colors.YELLOW}CTRL+C{Colors.END} to stop the server\n")

    try:
        # Run uvicorn
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "src.api.main:app",
            "--reload",
            "--host", "0.0.0.0",
            "--port", "8000"
        ])
    except KeyboardInterrupt:
        print_colored("\n\nServer stopped.", Colors.YELLOW)
    except Exception as e:
        print_colored(f"\nError starting server: {e}", Colors.RED)


def main():
    """Main entry point"""
    # Setup environment
    project_root = setup_environment()

    print_colored("=== Jahresabschluss-System Startup ===", Colors.BLUE)

    # Check database connection
    if not check_database_connection():
        print_colored("\nDatabase not accessible. Trying to initialize...", Colors.YELLOW)

        # Try to initialize database
        if not initialize_database_if_needed():
            print_colored("\nPlease check your .env file and ensure PostgreSQL is running", Colors.RED)
            print("\nYour .env should contain:")
            print("DATABASE_URL=postgresql://noborder@localhost/jahresabschluss")
            sys.exit(1)
    else:
        # Database accessible, ensure tables exist
        initialize_database_if_needed()

    # Start server
    start_server()


if __name__ == "__main__":
    main()
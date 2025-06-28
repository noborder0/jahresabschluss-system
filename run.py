#!/usr/bin/env python3
"""
Startup script for Jahresabschluss-System Phase 1 & 2
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
    CYAN = '\033[96m'
    END = '\033[0m'


def print_colored(message, color=Colors.GREEN):
    """Print colored message"""
    print(f"{color}{message}{Colors.END}")


def print_banner():
    """Print application banner"""
    print_colored("""
    ╔═══════════════════════════════════════════╗
    ║   Jahresabschluss-System mit AI          ║
    ║   Phase 1 & 2 - Import + AI Processing   ║
    ╚═══════════════════════════════════════════╝
    """, Colors.CYAN)


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


def check_redis_connection():
    """Check if Redis is available"""
    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        print_colored("ℹ Redis not configured (optional)", Colors.YELLOW)
        return False

    try:
        import redis
        r = redis.from_url(redis_url)
        r.ping()
        print_colored("✓ Redis connection successful", Colors.GREEN)
        return True
    except ImportError:
        print_colored("ℹ Redis package not installed", Colors.YELLOW)
        return False
    except Exception as e:
        print_colored(f"ℹ Redis connection failed (optional): {e}", Colors.YELLOW)
        return False


def check_ai_services():
    """Check AI services availability"""
    from src.core.config import settings

    ai_status = {
        'azure': False,
        'claude': False
    }

    # Check Azure
    if settings.azure_form_recognizer_endpoint and settings.azure_form_recognizer_key:
        ai_status['azure'] = True
        print_colored("✓ Azure Document Intelligence configured", Colors.GREEN)
    else:
        print_colored("ℹ Azure Document Intelligence not configured", Colors.YELLOW)

    # Check Claude
    if settings.anthropic_api_key:
        ai_status['claude'] = True
        print_colored("✓ Claude API configured", Colors.GREEN)
    else:
        print_colored("ℹ Claude API not configured", Colors.YELLOW)

    if not ai_status['azure'] and not ai_status['claude']:
        print_colored("\n⚠️  No AI services configured. System will run without AI features.", Colors.YELLOW)
        print_colored("   Add API keys to .env to enable AI processing.", Colors.YELLOW)

    return ai_status


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


def print_startup_info(ai_status):
    """Print startup information"""
    print_colored("\n=== Server Starting ===", Colors.BLUE)
    print(f"\n{Colors.GREEN}Web Interface:{Colors.END} http://localhost:8000")
    print(f"{Colors.GREEN}API Documentation:{Colors.END} http://localhost:8000/docs")

    if ai_status['azure'] or ai_status['claude']:
        print(f"{Colors.GREEN}AI Processing:{Colors.END} http://localhost:8000/api/ai/stats")

    print(f"\n{Colors.YELLOW}Press CTRL+C to stop the server{Colors.END}\n")


def start_server():
    """Start the FastAPI server"""
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
    # Print banner
    print_banner()

    # Setup environment
    project_root = setup_environment()

    print_colored("Starting system checks...", Colors.BLUE)

    # Check database connection
    if not check_database_connection():
        print_colored("\nDatabase not accessible. Trying to initialize...", Colors.YELLOW)

        # Try to initialize database
        if not initialize_database_if_needed():
            print_colored("\nPlease check your .env file and ensure PostgreSQL is running", Colors.RED)
            print("\nYour .env should contain:")
            print("DATABASE_URL=postgresql://user:pass@localhost/jahresabschluss")
            sys.exit(1)
    else:
        # Database accessible, ensure tables exist
        initialize_database_if_needed()

    # Check Redis (optional)
    check_redis_connection()

    # Check AI services
    ai_status = check_ai_services()

    # Print startup info
    print_startup_info(ai_status)

    # Start server
    start_server()


if __name__ == "__main__":
    main()
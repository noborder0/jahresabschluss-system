# start_phase1.py
"""
Startup script for Phase 1 of the Jahresabschluss-System
Run this to initialize the database and start the server
"""

import os
import sys

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Now we can import from src
from src.infrastructure.database.connection import init_db

if __name__ == "__main__":
    print("=== Jahresabschluss-System Phase 1 ===")
    print("Initializing database...")

    try:
        init_db()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        sys.exit(1)

    print("\nStarting FastAPI server...")
    print("Access the application at: http://localhost:8000")
    print("API documentation at: http://localhost:8000/docs")
    print("\nPress CTRL+C to stop the server")

    # Start uvicorn
    os.system("uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000")
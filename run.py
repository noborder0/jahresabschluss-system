# run.py
"""
Alternative run script that handles imports correctly
Place this in the project root directory
"""

import os
import sys
import subprocess

# Set PYTHONPATH to include current directory
os.environ['PYTHONPATH'] = os.path.dirname(os.path.abspath(__file__))

# Change to project directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=== Jahresabschluss-System Phase 1 ===")
print("Starting FastAPI server...")
print("Access the application at: http://localhost:8000")
print("API documentation at: http://localhost:8000/docs")
print("\nPress CTRL+C to stop the server\n")

# Run uvicorn with proper module path
subprocess.run([
    sys.executable, "-m", "uvicorn",
    "src.api.main:app",
    "--reload",
    "--host", "0.0.0.0",
    "--port", "8000"
])
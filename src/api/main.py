# src/api/main.py

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from src.api.routers import imports
import os
from pathlib import Path

app = FastAPI(title="Jahresabschluss-System mit AI")

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "src" / "presentation" / "templates"

print(f"Project root: {PROJECT_ROOT}")
print(f"Templates directory: {TEMPLATES_DIR}")
print(f"Templates exists: {TEMPLATES_DIR.exists()}")

# Routers
app.include_router(imports.router, prefix="/api/imports", tags=["imports"])


# Serve index.html at root
@app.get("/")
async def read_index():
    index_path = TEMPLATES_DIR / "index.html"
    print(f"Looking for index.html at: {index_path}")
    print(f"File exists: {index_path.exists()}")

    if not index_path.exists():
        # If file doesn't exist, return a simple HTML response for testing
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Jahresabschluss-System</title>
        </head>
        <body>
            <h1>Jahresabschluss-System</h1>
            <p>Die index.html Datei wurde nicht gefunden.</p>
            <p>Erwarteter Pfad: {}</p>
            <p>Bitte stellen Sie sicher, dass die Datei existiert.</p>
            <h2>API Status</h2>
            <p>Die API läuft korrekt. Testen Sie:</p>
            <ul>
                <li><a href="/docs">API Dokumentation</a></li>
                <li><a href="/health">Health Check</a></li>
            </ul>
        </body>
        </html>
        """.format(index_path))

    return FileResponse(index_path)


# Serve transactions.html
@app.get("/transactions.html")
async def read_transactions():
    transactions_path = TEMPLATES_DIR / "transactions.html"
    print(f"Looking for transactions.html at: {transactions_path}")
    print(f"File exists: {transactions_path.exists()}")

    if not transactions_path.exists():
        raise HTTPException(status_code=404, detail="transactions.html not found")

    return FileResponse(transactions_path)


# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "phase": "1",
        "templates_dir": str(TEMPLATES_DIR),
        "templates_exist": {
            "index.html": (TEMPLATES_DIR / "index.html").exists(),
            "transactions.html": (TEMPLATES_DIR / "transactions.html").exists()
        }
    }
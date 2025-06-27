# src/api/main.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.api.routers import imports

app = FastAPI(title="Jahresabschluss-System mit AI")

# Routers
app.include_router(imports.router, prefix="/api/imports", tags=["imports"])

# Serve index.html at root
@app.get("/")
async def read_index():
    return FileResponse('src/presentation/templates/index.html')

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "phase": "1"}
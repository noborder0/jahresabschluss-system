# src/api/routers/imports.py

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import Dict, Any
import os
import uuid
from src.core.config import settings
from src.infrastructure.importers.factory import ImporterFactory
from src.infrastructure.database.connection import get_db
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/file")
async def import_file(
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Import a file (XML, CSV, or PDF)
    """
    # Validate file size
    if file.size > settings.max_upload_size:
        raise HTTPException(400, f"File too large. Max size: {settings.max_upload_size} bytes")

    # Save file temporarily
    os.makedirs(settings.upload_path, exist_ok=True)
    temp_filename = f"{uuid.uuid4()}_{file.filename}"
    temp_path = os.path.join(settings.upload_path, temp_filename)

    try:
        # Write file
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Get appropriate importer
        factory = ImporterFactory()
        importer = factory.get_importer(file.filename)

        if not importer:
            raise HTTPException(400, f"Unsupported file type: {file.filename}")

        # Process import
        result = await importer.import_file(temp_path, db)

        return {
            "status": "success",
            "filename": file.filename,
            "import_id": result.get("import_id"),
            "transaction_count": result.get("transaction_count", 0),
            "source_type": result.get("source_type")
        }

    except Exception as e:
        raise HTTPException(500, f"Import failed: {str(e)}")
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.get("/status/{import_id}")
async def get_import_status(
        import_id: str,
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get status of an import batch
    """
    # This would query the database for import status
    # For Phase 1, return mock data
    return {
        "import_id": import_id,
        "status": "completed",
        "total_transactions": 10,
        "processed": 10,
        "errors": 0
    }
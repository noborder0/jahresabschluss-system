# src/api/routers/imports.py

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import Dict, Any
import os
import uuid
import traceback
import shutil
from src.core.config import settings
from src.infrastructure.importers.factory import ImporterFactory
from src.infrastructure.database.connection import get_db
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/bank")
async def import_bank_files(
        xml_file: UploadFile = File(...),
        csv_file: UploadFile = File(...),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Import bank files (XML and CSV together)
    """
    # Validate files
    if not xml_file.filename.lower().endswith('.xml'):
        raise HTTPException(400, "First file must be XML")
    if not csv_file.filename.lower().endswith('.csv'):
        raise HTTPException(400, "Second file must be CSV")

    # Create temporary directory for this import
    import_id = str(uuid.uuid4())
    import_dir = os.path.join(settings.upload_path, import_id)
    os.makedirs(import_dir, exist_ok=True)

    try:
        # Save both files to the same directory
        xml_path = os.path.join(import_dir, xml_file.filename)
        csv_path = os.path.join(import_dir, csv_file.filename)

        # Save XML
        xml_contents = await xml_file.read()
        with open(xml_path, "wb") as f:
            f.write(xml_contents)

        # Save CSV
        csv_contents = await csv_file.read()
        with open(csv_path, "wb") as f:
            f.write(csv_contents)

        print(f"Saved bank files to {import_dir}")
        print(f"XML: {xml_path} ({len(xml_contents)} bytes)")
        print(f"CSV: {csv_path} ({len(csv_contents)} bytes)")

        # Import using BankXMLImporter
        from src.infrastructure.importers.bank_xml import BankXMLImporter
        importer = BankXMLImporter()

        result = await importer.import_file(xml_path, db)

        return {
            "status": "success",
            "filename": xml_file.filename,
            "import_id": result.get("import_id"),
            "transaction_count": result.get("transaction_count", 0),
            "source_type": "BANK_XML",
            "bank_info": result.get("bank_info"),
            "preview": result.get("transactions", [])[:3]
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Bank import error: {e}")
        print(traceback.format_exc())
        raise HTTPException(500, f"Bank import failed: {str(e)}")
    finally:
        # Clean up temporary directory
        try:
            import shutil
            if os.path.exists(import_dir):
                shutil.rmtree(import_dir)
        except:
            pass


@router.post("/file")
async def import_file(
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Import a file (XML, CSV, or PDF)
    """
    # Validate file
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    # Validate file size
    contents = await file.read()
    if len(contents) > settings.max_upload_size:
        raise HTTPException(400, f"File too large. Max size: {settings.max_upload_size} bytes")

    # Save file temporarily
    os.makedirs(settings.upload_path, exist_ok=True)
    temp_filename = f"{uuid.uuid4()}_{file.filename}"
    temp_path = os.path.join(settings.upload_path, temp_filename)

    try:
        # Write file - ensure binary mode
        with open(temp_path, "wb") as f:
            f.write(contents)

        # Verify file was written correctly
        if not os.path.exists(temp_path):
            raise HTTPException(500, "Failed to save uploaded file")

        saved_size = os.path.getsize(temp_path)
        print(f"Saved file: {temp_path}, size: {saved_size} bytes (original: {len(contents)} bytes)")

        # Get appropriate importer
        factory = ImporterFactory()
        importer = factory.get_importer(file.filename)

        if not importer:
            raise HTTPException(400, f"Unsupported file type: {file.filename}")

        # Process import
        try:
            result = await importer.import_file(temp_path, db)
        except Exception as e:
            # Log the full error for debugging
            print(f"Import error for {file.filename}:")
            print(traceback.format_exc())

            # Return user-friendly error
            error_msg = str(e)
            if "encoding" in error_msg.lower():
                raise HTTPException(500, "File encoding error. Please ensure the file is in the correct format.")
            elif "parse" in error_msg.lower():
                raise HTTPException(500, "File parsing error. The file format may not be supported.")
            elif "CSV file not found" in error_msg:
                raise HTTPException(400,
                                    "Bank XML import requires the associated CSV file. Please upload both files together.")
            else:
                raise HTTPException(500, f"Import failed: {error_msg}")

        # Log for debugging
        print(f"Import result: {result}")

        return {
            "status": "success",
            "filename": file.filename,
            "import_id": result.get("import_id"),
            "transaction_count": result.get("transaction_count", 0),
            "source_type": result.get("source_type"),
            "format": result.get("format", ""),
            "bank_info": result.get("bank_info"),
            "preview": result.get("transactions", [])[:3] if result.get("transactions") else []
        }

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        print(f"Unexpected error during import:")
        print(traceback.format_exc())
        raise HTTPException(500, f"Unexpected error: {str(e)}")
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass  # Ignore cleanup errors


@router.get("/status/{import_id}")
async def get_import_status(
        import_id: str,
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get status of an import batch
    """
    from src.infrastructure.database.models import ImportBatch, ImportedTransaction
    from sqlalchemy import func

    try:
        # Query the database for actual import status
        batch = db.query(ImportBatch).filter(ImportBatch.id == import_id).first()

        if not batch:
            raise HTTPException(404, f"Import batch {import_id} not found")

        # Count transactions
        transaction_count = db.query(func.count(ImportedTransaction.id)) \
            .filter(ImportedTransaction.batch_id == import_id) \
            .scalar()

        # Count processed transactions
        processed_count = db.query(func.count(ImportedTransaction.id)) \
            .filter(ImportedTransaction.batch_id == import_id) \
            .filter(ImportedTransaction.processed == True) \
            .scalar()

        return {
            "import_id": str(batch.id),
            "status": "completed",
            "source_type": batch.source_type,
            "source_file": batch.source_file,
            "import_date": batch.import_date.isoformat(),
            "total_transactions": transaction_count,
            "processed": processed_count,
            "pending": transaction_count - processed_count,
            "errors": 0,
            "metadata": batch.bank_info
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting import status: {e}")
        raise HTTPException(500, f"Error retrieving import status: {str(e)}")
# src/api/routers/imports.py

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from typing import Dict, Any, Optional
import os
import uuid
import traceback
import shutil
from src.core.config import settings
from src.infrastructure.importers.factory import ImporterFactory
from src.infrastructure.database.connection import get_db
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/file")
async def import_file(
        file: UploadFile = File(...),
        account_name: Optional[str] = Form(None),
        iban: Optional[str] = Form(None),
        bic: Optional[str] = Form(None),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Import a file (CSV, PDF, JPEG, or PNG)
    The system automatically detects the file type:
    - Bank CSV (German bank exports)
    - PayPal CSV exports
    - Stripe CSV exports
    - Mollie CSV exports
    - DATEV CSV exports
    - PDF documents
    - Image files (JPEG, PNG)

    For bank and payment provider imports, optional metadata can be provided:
    - account_name: Friendly name for the account
    - iban: International Bank Account Number (for bank accounts)
    - bic: Bank Identifier Code (for bank accounts)
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

        # Log which importer is being used
        importer_type = type(importer).__name__
        print(f"Using importer: {importer_type} for file: {file.filename}")

        # Process import
        try:
            # For bank/payment imports, pass the metadata
            if importer_type in ['BankCSVImporter', 'PayPalImporter', 'StripeImporter', 'MollieImporter'] and any([account_name, iban, bic]):
                metadata = {
                    'account_name': account_name,
                    'iban': iban,
                    'bic': bic
                }
                print(f"{importer_type} with metadata: {metadata}")
                result = await importer.import_file(temp_path, db, metadata=metadata)
            else:
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
            "file_type": result.get("file_type"),
            "bank_info": result.get("bank_info"),
            "account_info": result.get("account_info"),  # For payment providers
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
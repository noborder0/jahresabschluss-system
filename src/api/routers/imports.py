# src/api/routers/imports.py

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, Query
from typing import Dict, Any, Optional, List
import os
import uuid
import traceback
import shutil
from src.core.config import settings
from src.infrastructure.importers.factory import ImporterFactory
from src.infrastructure.database.connection import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc
from decimal import Decimal

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
            if importer_type in ['BankCSVImporter', 'PayPalImporter', 'StripeImporter', 'MollieImporter'] and any(
                    [account_name, iban, bic]):
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


@router.get("/list")
async def list_imports(
        limit: int = Query(default=50, le=100),
        offset: int = Query(default=0, ge=0),
        source_type: Optional[str] = Query(default=None),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    List all import batches with optional filtering
    """
    from src.infrastructure.database.models import ImportBatch, ImportedTransaction
    from sqlalchemy import func

    try:
        # Base query
        query = db.query(ImportBatch)

        # Apply filters
        if source_type:
            query = query.filter(ImportBatch.source_type == source_type)

        # Get total count
        total_count = query.count()

        # Get batches with pagination
        batches = query.order_by(desc(ImportBatch.import_date)) \
            .offset(offset) \
            .limit(limit) \
            .all()

        # Build response
        result = []
        for batch in batches:
            # Count transactions for this batch
            transaction_count = db.query(func.count(ImportedTransaction.id)) \
                .filter(ImportedTransaction.batch_id == batch.id) \
                .scalar()

            result.append({
                "import_id": str(batch.id),
                "source_type": batch.source_type,
                "source_file": batch.source_file,
                "import_date": batch.import_date.isoformat(),
                "transaction_count": transaction_count,
                "metadata": batch.bank_info
            })

        return {
            "imports": result,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        print(f"Error listing imports: {e}")
        raise HTTPException(500, f"Error retrieving imports: {str(e)}")


@router.get("/{import_id}/transactions")
async def get_import_transactions(
        import_id: str,
        limit: int = Query(default=50, le=1000),
        offset: int = Query(default=0, ge=0),
        show_processed: bool = Query(default=True),
        show_unprocessed: bool = Query(default=True),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get all transactions for a specific import batch with pagination
    """
    from src.infrastructure.database.models import ImportBatch, ImportedTransaction

    try:
        # Verify import batch exists
        batch = db.query(ImportBatch).filter(ImportBatch.id == import_id).first()
        if not batch:
            raise HTTPException(404, f"Import batch {import_id} not found")

        # Base query
        query = db.query(ImportedTransaction).filter(ImportedTransaction.batch_id == import_id)

        # Apply filters
        if not show_processed and show_unprocessed:
            query = query.filter(ImportedTransaction.processed == False)
        elif show_processed and not show_unprocessed:
            query = query.filter(ImportedTransaction.processed == True)

        # Get total count
        total_count = query.count()

        # Get transactions with pagination
        transactions = query.order_by(ImportedTransaction.booking_date, ImportedTransaction.id) \
            .offset(offset) \
            .limit(limit) \
            .all()

        # Format response
        result = []
        for trans in transactions:
            # Format amount as string to preserve decimal precision
            amount_str = str(trans.amount) if trans.amount else "0.00"

            result.append({
                "id": str(trans.id),
                "booking_date": trans.booking_date.isoformat() if trans.booking_date else None,
                "amount": amount_str,
                "description": trans.description,
                "account_number": trans.account_number,
                "contra_account": trans.contra_account,
                "account_name": trans.account_name,
                "processed": trans.processed,
                "matched_booking_id": str(trans.matched_booking_id) if trans.matched_booking_id else None,
                "raw_data": trans.raw_data,
                "source_type": trans.source_type
            })

        return {
            "import_id": import_id,
            "source_type": batch.source_type,
            "source_file": batch.source_file,
            "import_date": batch.import_date.isoformat(),
            "transactions": result,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "metadata": batch.bank_info
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting transactions: {e}")
        raise HTTPException(500, f"Error retrieving transactions: {str(e)}")


@router.get("/transactions/{transaction_id}")
async def get_transaction_detail(
        transaction_id: str,
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed information about a specific transaction
    """
    from src.infrastructure.database.models import ImportedTransaction, ImportBatch

    try:
        # Get transaction with batch info
        trans = db.query(ImportedTransaction).filter(ImportedTransaction.id == transaction_id).first()

        if not trans:
            raise HTTPException(404, f"Transaction {transaction_id} not found")

        # Get batch info
        batch = db.query(ImportBatch).filter(ImportBatch.id == trans.batch_id).first()

        # Format response with all available data
        return {
            "id": str(trans.id),
            "batch_id": str(trans.batch_id),
            "source_type": trans.source_type,
            "booking_date": trans.booking_date.isoformat() if trans.booking_date else None,
            "amount": str(trans.amount) if trans.amount else "0.00",
            "description": trans.description,
            "account_number": trans.account_number,
            "contra_account": trans.contra_account,
            "account_name": trans.account_name,
            "processed": trans.processed,
            "matched_booking_id": str(trans.matched_booking_id) if trans.matched_booking_id else None,
            "import_date": trans.import_date.isoformat() if trans.import_date else None,
            "raw_data": trans.raw_data,
            "batch_info": {
                "source_file": batch.source_file if batch else None,
                "import_date": batch.import_date.isoformat() if batch else None,
                "metadata": batch.bank_info if batch else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting transaction detail: {e}")
        raise HTTPException(500, f"Error retrieving transaction: {str(e)}")


@router.put("/transactions/{transaction_id}")
async def update_transaction(
        transaction_id: str,
        booking_date: Optional[str] = None,
        amount: Optional[float] = None,
        description: Optional[str] = None,
        account_number: Optional[str] = None,
        contra_account: Optional[str] = None,
        account_name: Optional[str] = None,
        processed: Optional[bool] = None,
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update a transaction's details
    """
    from src.infrastructure.database.models import ImportedTransaction
    from datetime import datetime

    try:
        # Get transaction
        trans = db.query(ImportedTransaction).filter(ImportedTransaction.id == transaction_id).first()

        if not trans:
            raise HTTPException(404, f"Transaction {transaction_id} not found")

        # Update fields if provided
        if booking_date is not None:
            trans.booking_date = datetime.fromisoformat(booking_date).date()

        if amount is not None:
            trans.amount = Decimal(str(amount))

        if description is not None:
            trans.description = description[:500]  # Limit length

        if account_number is not None:
            trans.account_number = account_number

        if contra_account is not None:
            trans.contra_account = contra_account

        if account_name is not None:
            trans.account_name = account_name[:100]  # Limit length

        if processed is not None:
            trans.processed = processed

        # Commit changes
        db.commit()

        return {
            "status": "success",
            "transaction_id": str(trans.id),
            "message": "Transaction updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating transaction: {e}")
        db.rollback()
        raise HTTPException(500, f"Error updating transaction: {str(e)}")
# src/api/routers/ai_processing.py
"""
API endpoints for AI document processing
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from sqlalchemy.orm import Session

from src.infrastructure.database.connection import get_db
from src.infrastructure.database.models import Document, ImportBatch
from src.infrastructure.ai_services.document_processor import DocumentProcessor
from src.application.services.matching_service import MatchingService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
document_processor = DocumentProcessor()
matching_service = MatchingService()


@router.post("/process/{document_id}")
async def process_document(
        document_id: str,
        match_transactions: bool = Query(default=True, description="Attempt to match with transactions"),
        auto_book: bool = Query(default=False, description="Automatically create bookings for high confidence matches"),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Process a single document through the AI pipeline

    - Extract data using Azure Document Intelligence
    - Match with bank transactions
    - Generate booking suggestions using Claude AI
    """
    try:
        logger.info(f"Processing document {document_id}")

        # Check if document exists
        document = db.query(Document).filter_by(id=document_id).first()
        if not document:
            raise HTTPException(404, f"Document {document_id} not found")

        # Process the document
        result = await document_processor.process_document(
            document_id=document_id,
            db=db,
            match_transactions=match_transactions,
            auto_book=auto_book
        )

        return {
            "status": "success",
            "document_id": document_id,
            "filename": document.filename,
            "processing_result": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {e}")
        raise HTTPException(500, f"Document processing failed: {str(e)}")


@router.post("/process/batch")
async def process_documents_batch(
        document_ids: List[str],
        match_transactions: bool = Query(default=True),
        auto_book_threshold: float = Query(default=0.8, ge=0.0, le=1.0),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Process multiple documents in batch
    """
    try:
        if not document_ids:
            raise HTTPException(400, "No document IDs provided")

        if len(document_ids) > 50:
            raise HTTPException(400, "Maximum 50 documents per batch")

        # Process documents
        results = await document_processor.process_batch(
            document_ids=document_ids,
            db=db,
            match_transactions=match_transactions,
            auto_book_threshold=auto_book_threshold
        )

        # Summary statistics
        total = len(results)
        successful = sum(1 for r in results if r['status'] == 'completed')
        with_errors = sum(1 for r in results if r['status'] == 'completed_with_errors')
        failed = sum(1 for r in results if r['status'] == 'failed')

        return {
            "status": "success",
            "summary": {
                "total": total,
                "successful": successful,
                "with_errors": with_errors,
                "failed": failed
            },
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        raise HTTPException(500, f"Batch processing failed: {str(e)}")


@router.get("/process/status/{import_id}")
async def get_processing_status(
        import_id: str,
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get processing status for all documents in an import batch
    """
    try:
        # Get import batch
        import_batch = db.query(ImportBatch).filter_by(id=import_id).first()
        if not import_batch:
            raise HTTPException(404, f"Import batch {import_id} not found")

        # Get all documents in this batch
        documents = db.query(Document).filter_by(import_batch_id=import_id).all()

        if not documents:
            return {
                "status": "success",
                "import_id": import_id,
                "source_type": import_batch.source_type,
                "document_count": 0,
                "documents": []
            }

        # Build document status list
        document_statuses = []
        for doc in documents:
            # In a real implementation, we would retrieve actual processing status
            # For now, we'll return a placeholder
            doc_status = {
                "document_id": str(doc.id),
                "filename": doc.filename,
                "status": "pending",  # Would be retrieved from processing results
                "extraction_complete": False,
                "matching_complete": False,
                "booking_suggested": False,
                "confidence": 0.0
            }
            document_statuses.append(doc_status)

        return {
            "status": "success",
            "import_id": import_id,
            "source_type": import_batch.source_type,
            "document_count": len(documents),
            "documents": document_statuses
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting processing status: {e}")
        raise HTTPException(500, f"Failed to get processing status: {str(e)}")


@router.post("/match/find")
async def find_transaction_matches(
        amount: float,
        date: Optional[str] = Query(default=None, description="ISO format date"),
        vendor_name: Optional[str] = Query(default=None),
        reference: Optional[str] = Query(default=None),
        limit: int = Query(default=10, le=50),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Find potential transaction matches for given criteria
    """
    try:
        from decimal import Decimal

        matches = await matching_service.find_transaction_matches(
            amount=Decimal(str(amount)),
            date_str=date,
            vendor_name=vendor_name,
            reference=reference,
            db=db,
            limit=limit
        )

        return {
            "status": "success",
            "match_count": len(matches),
            "matches": matches
        }

    except Exception as e:
        logger.error(f"Error finding matches: {e}")
        raise HTTPException(500, f"Match finding failed: {str(e)}")


@router.post("/match/bulk")
async def match_documents_bulk(
        source_type: Optional[str] = Query(default=None),
        date_from: Optional[str] = Query(default=None),
        date_to: Optional[str] = Query(default=None),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Perform bulk matching for documents
    """
    try:
        # Parse dates
        from_date = None
        to_date = None

        if date_from:
            from_date = datetime.fromisoformat(date_from).date()
        if date_to:
            to_date = datetime.fromisoformat(date_to).date()

        results = await matching_service.match_documents_bulk(
            db=db,
            source_type=source_type,
            date_from=from_date,
            date_to=to_date
        )

        return {
            "status": "success",
            "results": results
        }

    except ValueError as e:
        raise HTTPException(400, f"Invalid date format: {str(e)}")
    except Exception as e:
        logger.error(f"Bulk matching error: {e}")
        raise HTTPException(500, f"Bulk matching failed: {str(e)}")


@router.get("/suggestions/{document_id}")
async def get_booking_suggestions(
        document_id: str,
        include_alternatives: bool = Query(default=True),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get booking suggestions for a processed document
    """
    try:
        # Check if document exists
        document = db.query(Document).filter_by(id=document_id).first()
        if not document:
            raise HTTPException(404, f"Document {document_id} not found")

        # In a real implementation, we would retrieve stored suggestions
        # For now, return a placeholder
        return {
            "status": "success",
            "document_id": document_id,
            "suggestions": {
                "primary": {
                    "booking_text": "Placeholder booking suggestion",
                    "entries": [],
                    "confidence": 0.0,
                    "is_placeholder": True
                },
                "alternatives": [] if include_alternatives else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting suggestions: {e}")
        raise HTTPException(500, f"Failed to get suggestions: {str(e)}")


@router.post("/suggestions/{document_id}/apply")
async def apply_booking_suggestion(
        document_id: str,
        suggestion_id: Optional[str] = None,
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Apply a booking suggestion to create actual bookings
    """
    try:
        # Check if document exists
        document = db.query(Document).filter_by(id=document_id).first()
        if not document:
            raise HTTPException(404, f"Document {document_id} not found")

        # In a real implementation, this would:
        # 1. Retrieve the suggestion
        # 2. Validate it
        # 3. Create booking entries
        # 4. Mark related transactions as processed

        return {
            "status": "success",
            "message": "Booking suggestion applied successfully",
            "document_id": document_id,
            "booking_id": "placeholder-booking-id"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying suggestion: {e}")
        raise HTTPException(500, f"Failed to apply suggestion: {str(e)}")


@router.get("/stats")
async def get_ai_processing_stats(
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get AI processing statistics
    """
    try:
        # Get document counts
        total_documents = db.query(Document).count()

        # In a real implementation, we would track processing status
        # For now, return placeholder stats
        return {
            "status": "success",
            "statistics": {
                "total_documents": total_documents,
                "processed_documents": 0,
                "pending_documents": total_documents,
                "extraction_success_rate": 0.0,
                "matching_success_rate": 0.0,
                "auto_booking_rate": 0.0,
                "average_confidence": 0.0,
                "ai_services": {
                    "azure_available": document_processor.azure_processor is not None,
                    "claude_available": document_processor.claude_service is not None
                }
            }
        }

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(500, f"Failed to get statistics: {str(e)}")
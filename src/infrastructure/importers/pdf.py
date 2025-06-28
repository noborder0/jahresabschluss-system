# src/infrastructure/importers/pdf.py

import os
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from .base import BaseImporter
from src.infrastructure.database.models import Document, ImportBatch


class PDFImporter(BaseImporter):
    """
    Importer for PDF documents and images (invoices, receipts, etc.)
    Supports PDF, JPEG, and PNG formats
    """

    def can_handle(self, filename: str) -> bool:
        """Check if this is a supported document file"""
        supported_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        return any(filename.lower().endswith(ext) for ext in supported_extensions)

    async def import_file(self, file_path: str, db: Session, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Import document file - stores as document for later processing
        Note: metadata parameter is included for interface compatibility but not used for document imports
        """
        # Determine file type
        filename_lower = file_path.lower()
        if filename_lower.endswith('.pdf'):
            file_type = 'PDF'
        elif filename_lower.endswith(('.jpg', '.jpeg')):
            file_type = 'JPEG'
        elif filename_lower.endswith('.png'):
            file_type = 'PNG'
        else:
            file_type = 'UNKNOWN'

        # Read file
        with open(file_path, 'rb') as f:
            file_data = f.read()

        # Create import batch
        batch = ImportBatch(
            source_type='PDF',  # Keep as PDF for backward compatibility
            source_file=os.path.basename(file_path),
            bank_info={'file_type': file_type}  # Store actual file type in metadata
        )
        db.add(batch)
        db.flush()

        # Store document
        document = Document(
            filename=os.path.basename(file_path),
            file_data=file_data,
            import_batch_id=batch.id
        )
        db.add(document)
        db.commit()

        return {
            "import_id": str(batch.id),
            "document_id": str(document.id),
            "transaction_count": 1,  # Document is treated as single transaction
            "source_type": "PDF",  # Keep for compatibility
            "file_type": file_type,  # Actual file type
            "filename": document.filename,
            "file_size": len(file_data),
            "status": "pending_processing"  # Will be processed by AI in later phases
        }
# src/infrastructure/importers/pdf.py

import os
from typing import Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from .base import BaseImporter
from src.infrastructure.database.models import Document, ImportBatch


class PDFImporter(BaseImporter):
    """
    Importer for PDF documents (invoices, receipts, etc.)
    """

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith('.pdf')

    async def import_file(self, file_path: str, db: Session) -> Dict[str, Any]:
        """
        Import PDF file - stores as document for later processing
        """
        # Read PDF file
        with open(file_path, 'rb') as f:
            pdf_data = f.read()

        # Create import batch
        batch = ImportBatch(
            source_type='PDF',
            source_file=os.path.basename(file_path)
        )
        db.add(batch)
        db.flush()

        # Store document
        document = Document(
            filename=os.path.basename(file_path),
            file_data=pdf_data,
            import_batch_id=batch.id
        )
        db.add(document)
        db.commit()

        return {
            "import_id": str(batch.id),
            "document_id": str(document.id),
            "transaction_count": 1,  # PDF is treated as single transaction
            "source_type": "PDF",
            "filename": document.filename,
            "file_size": len(pdf_data),
            "status": "pending_processing"  # Will be processed by AI in later phases
        }
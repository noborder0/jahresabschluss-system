# src/infrastructure/database/models.py

import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, DateTime, Boolean, DECIMAL, Date, LargeBinary, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .connection import Base


class ImportBatch(Base):
    """Import batch metadata"""
    __tablename__ = "import_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String(20), nullable=False)  # BANK_CSV, DATEV, PDF, PAYPAL, STRIPE, MOLLIE
    source_file = Column(String(255), nullable=False)
    bank_info = Column(JSON, nullable=True)  # Additional metadata for imports
    import_date = Column(DateTime, default=datetime.utcnow)

    # Relationships
    transactions = relationship("ImportedTransaction", back_populates="batch")
    documents = relationship("Document", back_populates="import_batch")


class ImportedTransaction(Base):
    """Imported transactions from any source"""
    __tablename__ = "imported_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("import_batches.id"))
    source_type = Column(String(20), nullable=False)

    # Common fields
    booking_date = Column(Date, nullable=True)
    amount = Column(DECIMAL(15, 2), nullable=False)
    description = Column(String, nullable=True)
    account_number = Column(String(20), nullable=True)
    contra_account = Column(String(20), nullable=True)
    account_name = Column(String(100), nullable=True)  # Name of account holder/partner

    # Original data for traceability
    raw_data = Column(JSON, nullable=False)

    # Status
    processed = Column(Boolean, default=False)
    matched_booking_id = Column(UUID(as_uuid=True), nullable=True)

    # Metadata
    import_date = Column(DateTime, default=datetime.utcnow)

    # Relationships
    batch = relationship("ImportBatch", back_populates="transactions")


class Document(Base):
    """Stored documents (PDFs, images, etc.)"""
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    file_data = Column(LargeBinary, nullable=False)
    upload_date = Column(DateTime, default=datetime.utcnow)
    import_batch_id = Column(UUID(as_uuid=True), ForeignKey("import_batches.id"), nullable=True)
    linked_booking_id = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    import_batch = relationship("ImportBatch", back_populates="documents")


class Booking(Base):
    """Final bookings"""
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_date = Column(Date, nullable=False)
    amount = Column(DECIMAL(15, 2), nullable=False)
    debit_account = Column(String(10), nullable=False)  # SKR04 account number
    credit_account = Column(String(10), nullable=False)  # SKR04 account number
    description = Column(String, nullable=True)
    tax_key = Column(String(5), nullable=True)

    # Reference to import
    import_id = Column(UUID(as_uuid=True), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(50), nullable=True)
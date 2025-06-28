# src/infrastructure/ai_services/document_processor.py
"""
Combined document processing service using Azure and Claude
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from .azure_document import AzureDocumentProcessor
from .claude_booking import ClaudeBookingService
from src.infrastructure.database.models import Document, ImportBatch, ImportedTransaction, Booking
from src.application.services.matching_service import MatchingService

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Orchestrates document processing through Azure and Claude AI services
    """

    def __init__(self):
        """Initialize the document processor with AI services"""
        self.azure_processor = None
        self.claude_service = None
        self.matching_service = MatchingService()

        # Initialize services if credentials are available
        self._initialize_services()

    def _initialize_services(self):
        """Initialize AI services with error handling"""
        # Try to initialize Azure
        try:
            from src.core.config import settings
            if settings.azure_form_recognizer_endpoint and settings.azure_form_recognizer_key:
                self.azure_processor = AzureDocumentProcessor()
                logger.info("Azure Document Intelligence initialized successfully")
            else:
                logger.warning("Azure Document Intelligence credentials not configured")
        except Exception as e:
            logger.error(f"Failed to initialize Azure Document Intelligence: {e}")

        # Try to initialize Claude
        try:
            from src.core.config import settings
            if settings.anthropic_api_key:
                self.claude_service = ClaudeBookingService()
                logger.info("Claude API initialized successfully")
            else:
                logger.warning("Claude API key not configured")
        except Exception as e:
            logger.error(f"Failed to initialize Claude API: {e}")

    async def process_document(
            self,
            document_id: str,
            db: Session,
            match_transactions: bool = True,
            auto_book: bool = False
    ) -> Dict[str, Any]:
        """
        Process a document through the full AI pipeline

        Args:
            document_id: ID of the document to process
            db: Database session
            match_transactions: Whether to attempt transaction matching
            auto_book: Whether to automatically create bookings above confidence threshold

        Returns:
            Processing results including extraction, matching, and booking suggestions
        """
        result = {
            'document_id': document_id,
            'status': 'pending',
            'extraction': None,
            'matching': None,
            'booking_suggestion': None,
            'errors': []
        }

        try:
            # Load document from database
            document = db.query(Document).filter_by(id=document_id).first()
            if not document:
                raise ValueError(f"Document {document_id} not found")

            logger.info(f"Processing document: {document.filename}")

            # Step 1: Extract data using Azure
            if self.azure_processor:
                try:
                    extraction_result = await self.azure_processor.analyze_document(
                        document.file_data,
                        document.filename
                    )
                    result['extraction'] = extraction_result

                    # Extract German tax information
                    tax_info = self.azure_processor.extract_german_tax_info(extraction_result)
                    result['extraction']['tax_info'] = tax_info

                    logger.info(
                        f"Document extraction completed with confidence: {extraction_result.get('confidence', 0)}")

                except Exception as e:
                    logger.error(f"Azure extraction failed: {e}")
                    result['errors'].append(f"Extraction error: {str(e)}")
                    result['extraction'] = self._create_manual_extraction_template()
            else:
                result['extraction'] = self._create_manual_extraction_template()
                result['errors'].append("Azure Document Intelligence not available")

            # Step 2: Match with transactions if requested
            if match_transactions and result['extraction']:
                matching_result = await self._match_transactions(
                    document,
                    result['extraction'],
                    db
                )
                result['matching'] = matching_result

            # Step 3: Generate booking suggestion using Claude
            if self.claude_service and result['extraction']:
                try:
                    # Get matched transaction data if available
                    transaction_data = None
                    if result['matching'] and result['matching'].get('matched_transactions'):
                        # Use the best match
                        best_match = result['matching']['matched_transactions'][0]
                        transaction = db.query(ImportedTransaction).filter_by(
                            id=best_match['transaction_id']
                        ).first()
                        if transaction:
                            transaction_data = {
                                'booking_date': transaction.booking_date,
                                'amount': float(transaction.amount),
                                'description': transaction.description,
                                'account_number': transaction.account_number
                            }

                    # Get vendor history for context
                    vendor_history = await self._get_vendor_history(
                        result['extraction'],
                        db
                    )

                    # Generate initial suggestion
                    booking_suggestion = await self.claude_service.suggest_booking(
                        result['extraction'],
                        transaction_data
                    )

                    # Enhance with historical context if available
                    if vendor_history:
                        historical_bookings = await self._get_similar_bookings(
                            result['extraction'],
                            db
                        )

                        booking_suggestion = await self.claude_service.enhance_with_context(
                            booking_suggestion,
                            historical_bookings,
                            vendor_history
                        )

                    result['booking_suggestion'] = booking_suggestion

                    logger.info(
                        f"Booking suggestion generated with confidence: {booking_suggestion.get('confidence', 0)}")

                    # Auto-book if confidence is high enough
                    if auto_book and booking_suggestion.get('confidence', 0) >= 0.8:
                        if booking_suggestion.get('is_balanced', False):
                            booking_id = await self._create_booking(
                                booking_suggestion,
                                document,
                                transaction_data,
                                db
                            )
                            result['booking_suggestion']['auto_booked'] = True
                            result['booking_suggestion']['booking_id'] = booking_id
                            logger.info(f"Auto-booking created with ID: {booking_id}")

                except Exception as e:
                    logger.error(f"Claude booking suggestion failed: {e}")
                    result['errors'].append(f"Booking suggestion error: {str(e)}")
                    result['booking_suggestion'] = self._create_manual_booking_template()
            else:
                result['booking_suggestion'] = self._create_manual_booking_template()
                if not self.claude_service:
                    result['errors'].append("Claude API not available")

            # Update document status
            result['status'] = 'completed' if not result['errors'] else 'completed_with_errors'

            # Store processing results in database
            await self._store_processing_results(document, result, db)

        except Exception as e:
            logger.error(f"Document processing failed: {e}")
            result['status'] = 'failed'
            result['errors'].append(f"Processing error: {str(e)}")

        return result

    async def _match_transactions(
            self,
            document: Document,
            extraction_data: Dict[str, Any],
            db: Session
    ) -> Dict[str, Any]:
        """Match document with potential transactions"""
        matching_result = {
            'matched_transactions': [],
            'suggested_matches': [],
            'match_criteria': {}
        }

        try:
            # Extract key matching criteria
            total_amount = extraction_data.get('amounts', {}).get('total', 0)
            invoice_date = extraction_data.get('dates', {}).get('invoice_date')
            vendor_name = extraction_data.get('vendor_info', {}).get('name', '')
            invoice_id = extraction_data.get('invoice_info', {}).get('invoice_id', '')

            if not total_amount:
                return matching_result

            matching_result['match_criteria'] = {
                'amount': total_amount,
                'date': invoice_date,
                'vendor': vendor_name,
                'reference': invoice_id
            }

            # Find potential matches
            matches = await self.matching_service.find_transaction_matches(
                amount=Decimal(str(total_amount)),
                date_str=invoice_date,
                vendor_name=vendor_name,
                reference=invoice_id,
                db=db
            )

            # Sort matches by score
            for match in matches:
                if match['score'] >= 0.8:  # High confidence match
                    matching_result['matched_transactions'].append(match)
                else:  # Suggestion
                    matching_result['suggested_matches'].append(match)

            # Limit results
            matching_result['matched_transactions'] = matching_result['matched_transactions'][:3]
            matching_result['suggested_matches'] = matching_result['suggested_matches'][:5]

        except Exception as e:
            logger.error(f"Transaction matching failed: {e}")

        return matching_result

    async def _get_vendor_history(
            self,
            extraction_data: Dict[str, Any],
            db: Session
    ) -> Optional[Dict[str, Any]]:
        """Get historical data for vendor"""
        vendor_name = extraction_data.get('vendor_info', {}).get('name')
        if not vendor_name:
            return None

        # This would query historical bookings for the vendor
        # For now, return None as placeholder
        return None

    async def _get_similar_bookings(
            self,
            extraction_data: Dict[str, Any],
            db: Session,
            limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get similar historical bookings"""
        # This would query similar bookings based on vendor, amount range, etc.
        # For now, return empty list as placeholder
        return []

    async def _create_booking(
            self,
            booking_suggestion: Dict[str, Any],
            document: Document,
            transaction_data: Optional[Dict[str, Any]],
            db: Session
    ) -> str:
        """Create booking entries in database"""
        # This would create actual booking entries
        # For now, return a dummy ID
        import uuid
        return str(uuid.uuid4())

    async def _store_processing_results(
            self,
            document: Document,
            result: Dict[str, Any],
            db: Session
    ):
        """Store processing results for later retrieval"""
        # Store as JSON in a processing results table or document metadata
        # For now, we'll add it to the document's linked_booking_id field as a placeholder
        pass

    def _create_manual_extraction_template(self) -> Dict[str, Any]:
        """Create template for manual data entry"""
        return {
            'document_type': 'MANUAL',
            'confidence': 0.0,
            'vendor_info': {
                'name': '',
                'address': '',
                'tax_id': ''
            },
            'invoice_info': {
                'invoice_id': '',
                'invoice_date': ''
            },
            'amounts': {
                'subtotal': 0.0,
                'tax': 0.0,
                'total': 0.0
            },
            'manual_entry_required': True
        }

    def _create_manual_booking_template(self) -> Dict[str, Any]:
        """Create template for manual booking entry"""
        return {
            'booking_text': '',
            'entries': [
                {
                    'account': '',
                    'account_name': '',
                    'debit': None,
                    'credit': None,
                    'tax_key': ''
                }
            ],
            'confidence': 0.0,
            'reasoning': 'Manual entry required',
            'manual_entry_required': True
        }

    async def process_batch(
            self,
            document_ids: List[str],
            db: Session,
            match_transactions: bool = True,
            auto_book_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Process multiple documents in batch

        Args:
            document_ids: List of document IDs to process
            db: Database session
            match_transactions: Whether to match with transactions
            auto_book_threshold: Confidence threshold for auto-booking

        Returns:
            List of processing results
        """
        results = []

        for doc_id in document_ids:
            try:
                result = await self.process_document(
                    doc_id,
                    db,
                    match_transactions=match_transactions,
                    auto_book=auto_book_threshold > 0
                )
                results.append(result)

            except Exception as e:
                logger.error(f"Failed to process document {doc_id}: {e}")
                results.append({
                    'document_id': doc_id,
                    'status': 'failed',
                    'errors': [str(e)]
                })

        return results
# src/application/services/matching_service.py
"""
Service for matching documents with transactions
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from src.infrastructure.database.models import ImportedTransaction, Document, ImportBatch

logger = logging.getLogger(__name__)


class MatchingService:
    """
    Intelligent matching service for connecting documents with bank transactions
    """

    def __init__(self):
        """Initialize the matching service"""
        self.amount_tolerance = Decimal('0.01')  # 1 cent tolerance
        self.date_tolerance_days = 30  # Look within 30 days

    async def find_transaction_matches(
            self,
            amount: Decimal,
            date_str: Optional[str],
            vendor_name: Optional[str],
            reference: Optional[str],
            db: Session,
            limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find potential transaction matches for a document

        Args:
            amount: Document amount
            date_str: Document date (ISO format)
            vendor_name: Vendor/partner name
            reference: Invoice number or reference
            db: Database session
            limit: Maximum number of matches to return

        Returns:
            List of potential matches with confidence scores
        """
        matches = []

        # Parse date if provided
        document_date = None
        if date_str:
            try:
                document_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
            except:
                try:
                    document_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except:
                    logger.warning(f"Could not parse date: {date_str}")

        # Build base query
        query = db.query(ImportedTransaction).filter(
            ImportedTransaction.processed == False  # Only unprocessed transactions
        )

        # Amount filter with tolerance
        amount_min = amount - self.amount_tolerance
        amount_max = amount + self.amount_tolerance

        # For outgoing payments (negative amounts in bank)
        query_outgoing = query.filter(
            and_(
                ImportedTransaction.amount >= -amount_max,
                ImportedTransaction.amount <= -amount_min
            )
        )

        # For incoming payments (positive amounts)
        query_incoming = query.filter(
            and_(
                ImportedTransaction.amount >= amount_min,
                ImportedTransaction.amount <= amount_max
            )
        )

        # Date filter if date is available
        if document_date:
            date_min = document_date - timedelta(days=self.date_tolerance_days)
            date_max = document_date + timedelta(days=self.date_tolerance_days)

            query_outgoing = query_outgoing.filter(
                and_(
                    ImportedTransaction.booking_date >= date_min,
                    ImportedTransaction.booking_date <= date_max
                )
            )

            query_incoming = query_incoming.filter(
                and_(
                    ImportedTransaction.booking_date >= date_min,
                    ImportedTransaction.booking_date <= date_max
                )
            )

        # Get potential matches
        outgoing_transactions = query_outgoing.limit(limit * 2).all()
        incoming_transactions = query_incoming.limit(limit * 2).all()

        # Score each match
        all_transactions = outgoing_transactions + incoming_transactions

        for transaction in all_transactions:
            score, match_details = self._calculate_match_score(
                transaction,
                amount,
                document_date,
                vendor_name,
                reference
            )

            if score > 0.3:  # Minimum threshold
                matches.append({
                    'transaction_id': str(transaction.id),
                    'score': score,
                    'confidence_level': self._get_confidence_level(score),
                    'match_details': match_details,
                    'transaction': {
                        'date': transaction.booking_date.isoformat() if transaction.booking_date else None,
                        'amount': float(transaction.amount),
                        'description': transaction.description,
                        'account_name': transaction.account_name,
                        'account_number': transaction.account_number,
                        'source_type': transaction.source_type
                    }
                })

        # Sort by score descending
        matches.sort(key=lambda x: x['score'], reverse=True)

        return matches[:limit]

    def _calculate_match_score(
            self,
            transaction: ImportedTransaction,
            amount: Decimal,
            document_date: Optional[datetime.date],
            vendor_name: Optional[str],
            reference: Optional[str]
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate match score between transaction and document

        Returns:
            Tuple of (score, match_details)
        """
        score = 0.0
        match_details = {
            'amount_match': False,
            'date_match': False,
            'vendor_match': False,
            'reference_match': False,
            'criteria': {}
        }

        # 1. Amount matching (40% weight)
        amount_score = self._calculate_amount_score(transaction.amount, amount)
        score += amount_score * 0.4
        match_details['amount_match'] = amount_score > 0.9
        match_details['criteria']['amount'] = {
            'score': amount_score,
            'transaction_amount': float(transaction.amount),
            'document_amount': float(amount),
            'difference': float(abs(transaction.amount) - amount)
        }

        # 2. Date matching (20% weight)
        if document_date and transaction.booking_date:
            date_score = self._calculate_date_score(transaction.booking_date, document_date)
            score += date_score * 0.2
            match_details['date_match'] = date_score > 0.8
            match_details['criteria']['date'] = {
                'score': date_score,
                'transaction_date': transaction.booking_date.isoformat(),
                'document_date': document_date.isoformat(),
                'days_difference': abs((transaction.booking_date - document_date).days)
            }
        else:
            # No date to match, neutral score
            score += 0.1

        # 3. Vendor name matching (25% weight)
        if vendor_name:
            vendor_score = self._calculate_text_similarity(
                transaction.account_name or '',
                vendor_name
            )

            # Also check description
            desc_vendor_score = self._calculate_text_similarity(
                transaction.description or '',
                vendor_name
            )

            # Use the better score
            best_vendor_score = max(vendor_score, desc_vendor_score)
            score += best_vendor_score * 0.25
            match_details['vendor_match'] = best_vendor_score > 0.7
            match_details['criteria']['vendor'] = {
                'score': best_vendor_score,
                'transaction_vendor': transaction.account_name,
                'document_vendor': vendor_name,
                'matched_in': 'account_name' if vendor_score > desc_vendor_score else 'description'
            }

        # 4. Reference matching (15% weight)
        if reference:
            ref_score = self._find_reference_in_text(
                transaction.description or '',
                reference
            )
            score += ref_score * 0.15
            match_details['reference_match'] = ref_score > 0.8
            match_details['criteria']['reference'] = {
                'score': ref_score,
                'reference': reference,
                'found_in_description': ref_score > 0
            }

        # Additional matching for specific payment providers
        if transaction.source_type in ['PAYPAL', 'STRIPE', 'MOLLIE']:
            # Check if vendor name appears in transaction metadata
            raw_data = transaction.raw_data or {}

            # PayPal specific
            if transaction.source_type == 'PAYPAL' and vendor_name:
                paypal_partner = raw_data.get('partner_name', '')
                if paypal_partner:
                    paypal_score = self._calculate_text_similarity(paypal_partner, vendor_name)
                    if paypal_score > match_details['criteria'].get('vendor', {}).get('score', 0):
                        score = score - (match_details['criteria'].get('vendor', {}).get('score', 0) * 0.25)
                        score += paypal_score * 0.25
                        match_details['vendor_match'] = paypal_score > 0.7
                        match_details['criteria']['vendor'] = {
                            'score': paypal_score,
                            'transaction_vendor': paypal_partner,
                            'document_vendor': vendor_name,
                            'matched_in': 'paypal_partner_name'
                        }

        return score, match_details

    def _calculate_amount_score(self, transaction_amount: Decimal, document_amount: Decimal) -> float:
        """Calculate similarity score for amounts"""
        # Handle sign (transaction amounts are often negative for payments)
        trans_abs = abs(transaction_amount)
        doc_abs = abs(document_amount)

        if doc_abs == 0:
            return 0.0

        # Exact match
        if trans_abs == doc_abs:
            return 1.0

        # Calculate percentage difference
        diff = abs(trans_abs - doc_abs)
        percentage_diff = diff / doc_abs

        # Score based on percentage difference
        if percentage_diff < 0.001:  # Less than 0.1%
            return 0.99
        elif percentage_diff < 0.01:  # Less than 1%
            return 0.95
        elif percentage_diff < 0.02:  # Less than 2%
            return 0.85
        elif percentage_diff < 0.05:  # Less than 5%
            return 0.7
        elif percentage_diff < 0.1:  # Less than 10%
            return 0.5
        else:
            return max(0, 1 - percentage_diff)

    def _calculate_date_score(self, transaction_date: datetime.date, document_date: datetime.date) -> float:
        """Calculate similarity score for dates"""
        days_diff = abs((transaction_date - document_date).days)

        if days_diff == 0:
            return 1.0
        elif days_diff <= 1:
            return 0.95
        elif days_diff <= 3:
            return 0.9
        elif days_diff <= 7:
            return 0.8
        elif days_diff <= 14:
            return 0.6
        elif days_diff <= 30:
            return 0.4
        else:
            return max(0, 1 - (days_diff / 365))  # Decay over a year

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings"""
        if not text1 or not text2:
            return 0.0

        # Normalize texts
        text1_norm = self._normalize_text(text1)
        text2_norm = self._normalize_text(text2)

        # Exact match
        if text1_norm == text2_norm:
            return 1.0

        # Check if one contains the other
        if text1_norm in text2_norm or text2_norm in text1_norm:
            return 0.9

        # Use sequence matcher for fuzzy matching
        return SequenceMatcher(None, text1_norm, text2_norm).ratio()

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ''

        # Convert to lowercase
        text = text.lower()

        # Remove common business suffixes
        suffixes = ['gmbh', 'ag', 'kg', 'ohg', 'ug', 'e.k.', 'e.v.', 'inc', 'ltd', 'llc', 'corp']
        for suffix in suffixes:
            text = text.replace(f' {suffix}', '').replace(f'{suffix}', '')

        # Remove special characters
        text = re.sub(r'[^\w\s]', ' ', text)

        # Remove extra whitespace
        text = ' '.join(text.split())

        return text.strip()

    def _find_reference_in_text(self, text: str, reference: str) -> float:
        """Find reference number in text"""
        if not text or not reference:
            return 0.0

        text_lower = text.lower()
        ref_lower = reference.lower()

        # Exact match
        if ref_lower in text_lower:
            return 1.0

        # Remove common prefixes from reference
        ref_cleaned = re.sub(r'^(inv|invoice|re|ref|nr|no)[\s\-\.:#]*', '', ref_lower, flags=re.IGNORECASE)

        if ref_cleaned in text_lower:
            return 0.95

        # Try to find numeric part only
        ref_numbers = re.findall(r'\d+', reference)
        if ref_numbers:
            for num in ref_numbers:
                if len(num) >= 4 and num in text:  # At least 4 digits
                    return 0.8

        return 0.0

    def _get_confidence_level(self, score: float) -> str:
        """Convert numeric score to confidence level"""
        if score >= 0.9:
            return 'very_high'
        elif score >= 0.8:
            return 'high'
        elif score >= 0.7:
            return 'medium'
        elif score >= 0.5:
            return 'low'
        else:
            return 'very_low'

    async def match_documents_bulk(
            self,
            db: Session,
            source_type: Optional[str] = None,
            date_from: Optional[datetime.date] = None,
            date_to: Optional[datetime.date] = None
    ) -> Dict[str, Any]:
        """
        Perform bulk matching for all unmatched documents

        Args:
            db: Database session
            source_type: Filter by transaction source type
            date_from: Start date filter
            date_to: End date filter

        Returns:
            Summary of matching results
        """
        results = {
            'total_documents': 0,
            'matched_documents': 0,
            'high_confidence_matches': 0,
            'low_confidence_matches': 0,
            'no_matches': 0,
            'errors': 0
        }

        # Query unprocessed documents
        query = db.query(Document).filter(
            Document.linked_booking_id.is_(None)
        )

        documents = query.all()
        results['total_documents'] = len(documents)

        for document in documents:
            try:
                # This would process each document through the matching pipeline
                # For now, we'll just count it
                # In real implementation, this would call document processor
                pass

            except Exception as e:
                logger.error(f"Error matching document {document.id}: {e}")
                results['errors'] += 1

        return results
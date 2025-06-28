# src/infrastructure/importers/stripe.py

import os
import csv
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from .base import BaseImporter
from src.infrastructure.database.models import ImportedTransaction, ImportBatch


class StripeImporter(BaseImporter):
    """
    Importer for Stripe CSV exports
    Supports Stripe unified payments export format
    """

    def can_handle(self, filename: str) -> bool:
        """Check if this is a Stripe CSV file"""
        if not filename.lower().endswith('.csv'):
            return False

        filename_lower = filename.lower()
        # Also check for variations with hyphen
        return ('stripe' in filename_lower or
                'unified_payments' in filename_lower or
                'unified-payments' in filename_lower or
                'payments' in filename_lower)

    async def import_file(self, file_path: str, db: Session, metadata: Optional[Dict[str, Any]] = None) -> Dict[
        str, Any]:
        """Import Stripe CSV file"""
        print(f"Stripe Import: Processing {file_path}")

        try:
            # Parse CSV file
            transactions = self._parse_stripe_csv(file_path)

            if not transactions:
                raise Exception("No transactions found in Stripe CSV file")

            print(f"Parsed {len(transactions)} Stripe transactions")

            # Extract account info
            account_info = {
                'payment_provider': 'Stripe',
                'account_type': 'payment_processor',
                'filename': os.path.basename(file_path)
            }

            # Add user-provided metadata if available
            if metadata:
                if metadata.get('account_name'):
                    account_info['account_name'] = metadata['account_name']

            # Save to database
            import_id = self._save_to_database(db, account_info, transactions, file_path)

            return {
                "import_id": import_id,
                "transaction_count": len(transactions),
                "source_type": "STRIPE",
                "account_info": account_info,
                "transactions": transactions[:5]  # Preview first 5
            }

        except Exception as e:
            print(f"Stripe Import Error: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _parse_stripe_csv(self, csv_path: str) -> List[Dict[str, Any]]:
        """Parse Stripe CSV file"""
        transactions = []

        # Stripe exports are typically UTF-8
        encodings = ['utf-8', 'utf-8-sig', 'cp1252']

        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding, newline='') as f:
                    # Read first few lines to detect delimiter
                    sample = f.read(1024)
                    f.seek(0)

                    # Count delimiters to detect which one is used
                    comma_count = sample.count(',')
                    semicolon_count = sample.count(';')

                    # Choose delimiter based on count
                    delimiter = ';' if semicolon_count > comma_count else ','

                    print(f"Detected delimiter: '{delimiter}' (commas: {comma_count}, semicolons: {semicolon_count})")

                    reader = csv.DictReader(f, delimiter=delimiter)

                    # Debug: Print field names
                    if reader.fieldnames:
                        print(f"CSV columns found: {reader.fieldnames[:5]}...")  # First 5 columns

                    for row in reader:
                        transaction = self._parse_transaction_row(row)
                        if transaction:
                            transactions.append(transaction)

                print(
                    f"Successfully parsed {len(transactions)} transactions using {encoding} with delimiter '{delimiter}'")
                return transactions

            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"Error with {encoding}: {e}")
                continue

        return transactions

    def _parse_transaction_row(self, row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Parse a single Stripe transaction row"""
        try:
            # Parse amounts - handle both German and English formats
            amount = self._parse_stripe_amount(row.get('Amount', '0'))
            amount_refunded = self._parse_stripe_amount(row.get('Amount Refunded', '0'))
            fee = self._parse_stripe_amount(row.get('Fee', '0'))

            # Debug output for first few transactions
            if hasattr(self, '_debug_count'):
                self._debug_count += 1
            else:
                self._debug_count = 1

            if self._debug_count <= 3:
                print(f"Debug transaction {self._debug_count}:")
                print(f"  Raw Amount: {row.get('Amount', '0')}")
                print(f"  Parsed Amount: {amount}")
                print(f"  Fee: {fee}")
                print(f"  Status: {row.get('Status', '')}")

            # Skip if no amount AND it's not a valid zero transaction
            # But keep transactions with status information even if amount is 0
            status = row.get('Status', '').strip()
            if amount == 0 and not status:
                return None

            # Parse date
            created_date = self._parse_stripe_date(row.get('Created date (UTC)', ''))
            refunded_date = self._parse_stripe_date(row.get('Refunded date (UTC)', ''))

            # Get status
            status = row.get('Status', '').strip()

            # Calculate net amount
            net_amount = amount - fee - amount_refunded

            # Extract metadata
            metadata_fields = {}
            for key, value in row.items():
                if '(metadata)' in key and value:
                    clean_key = key.replace(' (metadata)', '')
                    metadata_fields[clean_key] = value

            return {
                'stripe_id': row.get('id', '').strip(),
                'booking_date': created_date,
                'refunded_date': refunded_date,
                'amount': amount,
                'amount_refunded': amount_refunded,
                'fee': fee,
                'net_amount': net_amount,
                'currency': row.get('Currency', 'EUR').strip(),
                'status': status,
                'captured': row.get('Captured', '').lower() == 'true',
                'description': row.get('Description', '').strip(),
                'customer_email': row.get('Customer Email', '').strip(),
                'customer_id': row.get('Customer ID', '').strip(),
                'card_id': row.get('Card ID', '').strip(),
                'invoice_id': row.get('Invoice ID', '').strip(),
                'decline_reason': row.get('Decline Reason', '').strip(),
                'statement_descriptor': row.get('Statement Descriptor', '').strip(),
                'metadata': metadata_fields,
                'is_refund': amount_refunded > 0,
                'is_successful': status.lower() in ['succeeded', 'paid'],
                'raw_data': {k: v for k, v in row.items() if v and '(metadata)' not in k}
            }

        except Exception as e:
            print(f"Error parsing Stripe transaction row: {e}")
            return None

    def _parse_stripe_amount(self, amount_str: str) -> Decimal:
        """Parse Stripe amount - handles both German (comma) and English (dot) format"""
        if not amount_str or not amount_str.strip():
            return Decimal('0')

        amount_str = amount_str.strip()

        try:
            # First, determine if it's German format (comma as decimal separator)
            if ',' in amount_str and '.' not in amount_str:
                # German format: replace comma with dot
                amount_str = amount_str.replace(',', '.')
            elif ',' in amount_str and '.' in amount_str:
                # Could be either format, check position
                dot_pos = amount_str.rfind('.')
                comma_pos = amount_str.rfind(',')

                if comma_pos > dot_pos:
                    # German format: 1.234,56
                    amount_str = amount_str.replace('.', '').replace(',', '.')
                else:
                    # English format: 1,234.56
                    amount_str = amount_str.replace(',', '')

            # Now parse the normalized amount
            if '.' in amount_str:
                # Already in decimal format (euros/dollars)
                return Decimal(amount_str)
            else:
                # Integer - could be cents or whole currency
                # If the value is large (>999), assume it's in cents
                value = int(amount_str)
                if value > 999:
                    return Decimal(value) / 100
                else:
                    # Small values - assume already in euros/dollars
                    return Decimal(value)

        except Exception as e:
            print(f"Could not parse Stripe amount: {amount_str} - Error: {e}")
            return Decimal('0')

    def _parse_stripe_date(self, date_str: str) -> Optional[datetime]:
        """Parse Stripe date format"""
        if not date_str or not date_str.strip():
            return None

        date_str = date_str.strip()

        # Stripe date formats
        formats = [
            '%Y-%m-%d %H:%M:%S',  # Standard format
            '%Y-%m-%d %H:%M:%S.%f',  # With microseconds
            '%Y-%m-%dT%H:%M:%SZ',  # ISO format with Z
            '%Y-%m-%dT%H:%M:%S',  # ISO format without Z
            '%Y-%m-%d',  # Date only
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except:
                continue

        print(f"Could not parse Stripe date: {date_str}")
        return None

    def _save_to_database(self, db: Session, account_info: Dict, transactions: List[Dict], file_path: str) -> str:
        """Save Stripe import to database"""
        try:
            # Create import batch
            batch = ImportBatch(
                source_type='STRIPE',
                source_file=os.path.basename(file_path),
                bank_info=account_info
            )
            db.add(batch)
            db.flush()

            print(f"Created Stripe import batch {batch.id}")

            # Save transactions
            saved_count = 0

            for i, trans in enumerate(transactions):
                try:
                    # Include all transactions, even failed ones, for audit purposes
                    # But mark them appropriately
                    is_successful = trans.get('is_successful', False)

                    # Use net amount as the transaction amount
                    amount = trans.get('net_amount', Decimal('0'))

                    # For failed transactions, use 0 as amount
                    if not is_successful:
                        amount = Decimal('0')

                    description = self._build_description(trans)
                    if not is_successful:
                        description = f"[FAILED] {description}"

                    imported_trans = ImportedTransaction(
                        batch_id=batch.id,
                        source_type='STRIPE',
                        booking_date=trans.get('booking_date'),
                        amount=amount,
                        description=description,
                        account_number='STRIPE',  # Virtual account number
                        account_name=trans.get('customer_email', ''),
                        raw_data={
                            'stripe_id': trans.get('stripe_id'),
                            'status': trans.get('status'),
                            'currency': trans.get('currency'),
                            'fee': str(trans.get('fee', '0')),
                            'gross_amount': str(trans.get('amount', '0')),
                            'is_successful': is_successful
                        }
                    )
                    db.add(imported_trans)
                    saved_count += 1

                    if (i + 1) % 100 == 0:
                        db.flush()
                        print(f"  Saved {i + 1} transactions...")

                except Exception as e:
                    print(f"Error saving transaction {i + 1}: {e}")
                    continue

            db.commit()
            print(f"Successfully saved {saved_count} Stripe transactions")

            return str(batch.id)

        except Exception as e:
            print(f"Database save error: {e}")
            db.rollback()
            raise

    def _build_description(self, trans: Dict) -> str:
        """Build transaction description"""
        parts = []

        # Add main description
        if trans.get('description'):
            parts.append(trans['description'])

        # Add statement descriptor
        if trans.get('statement_descriptor'):
            parts.append(f"Statement: {trans['statement_descriptor']}")

        # Add customer info
        if trans.get('customer_email'):
            parts.append(f"Customer: {trans['customer_email']}")

        # Add Stripe ID for reference
        if trans.get('stripe_id'):
            parts.append(f"Stripe ID: {trans['stripe_id']}")

        # Add product info from metadata if available
        products = []
        for key, value in trans.get('metadata', {}).items():
            if key.startswith('product_') and value:
                products.append(value)

        if products:
            parts.append(f"Products: {', '.join(products[:3])}")  # Limit to 3 products

        return ' | '.join(parts)[:500]  # Limit length
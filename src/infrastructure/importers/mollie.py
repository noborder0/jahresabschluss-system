# src/infrastructure/importers/mollie.py

import os
import csv
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from .base import BaseImporter
from src.infrastructure.database.models import ImportedTransaction, ImportBatch


class MollieImporter(BaseImporter):
    """
    Importer for Mollie settlement CSV exports
    Supports Mollie payment processor settlement reports
    """

    def can_handle(self, filename: str) -> bool:
        """Check if this is a Mollie CSV file"""
        if not filename.lower().endswith('.csv'):
            return False

        filename_lower = filename.lower()
        # Mollie files contain "mollie" and usually "settlement" in the name
        return 'mollie' in filename_lower

    async def import_file(self, file_path: str, db: Session, metadata: Optional[Dict[str, Any]] = None) -> Dict[
        str, Any]:
        """Import Mollie CSV file"""
        print(f"Mollie Import: Processing {file_path}")

        try:
            # Parse CSV file
            transactions = self._parse_mollie_csv(file_path)

            if not transactions:
                raise Exception("No transactions found in Mollie CSV file")

            print(f"Parsed {len(transactions)} Mollie transactions")

            # Extract account info
            account_info = {
                'payment_provider': 'Mollie',
                'account_type': 'payment_processor',
                'filename': os.path.basename(file_path)
            }

            # Extract settlement reference from filename if possible
            filename = os.path.basename(file_path)
            if 'settlement' in filename.lower():
                # Try to extract settlement ID
                parts = filename.lower().split('settlement')
                if len(parts) > 1:
                    settlement_id = parts[1].split('.')[0]
                    account_info['settlement_id'] = settlement_id

            # Add user-provided metadata if available
            if metadata:
                if metadata.get('account_name'):
                    account_info['account_name'] = metadata['account_name']

            # Save to database
            import_id = self._save_to_database(db, account_info, transactions, file_path)

            return {
                "import_id": import_id,
                "transaction_count": len(transactions),
                "source_type": "MOLLIE",
                "account_info": account_info,
                "transactions": transactions[:5]  # Preview first 5
            }

        except Exception as e:
            print(f"Mollie Import Error: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _parse_mollie_csv(self, csv_path: str) -> List[Dict[str, Any]]:
        """Parse Mollie CSV file"""
        transactions = []

        # Mollie exports are typically UTF-8
        encodings = ['utf-8', 'utf-8-sig', 'cp1252']

        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding, newline='') as f:
                    # Detect delimiter
                    sample = f.read(1024)
                    f.seek(0)

                    # Mollie typically uses comma as delimiter
                    delimiter = ','
                    if ';' in sample and ',' not in sample:
                        delimiter = ';'

                    reader = csv.DictReader(f, delimiter=delimiter)

                    # Debug: Print field names
                    if reader.fieldnames:
                        print(f"Mollie CSV columns: {reader.fieldnames}")

                    for row in reader:
                        transaction = self._parse_transaction_row(row)
                        if transaction:
                            transactions.append(transaction)

                print(f"Successfully parsed {len(transactions)} transactions using {encoding}")
                return transactions

            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"Error with {encoding}: {e}")
                continue

        return transactions

    def _parse_transaction_row(self, row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Parse a single Mollie transaction row"""
        try:
            # Parse amounts
            amount = self._parse_amount(row.get('Amount', '0'))
            settlement_amount = self._parse_amount(row.get('Settlement amount', '0'))
            amount_refunded = self._parse_amount(row.get('Amount refunded', '0'))

            # Skip if no amount
            if amount == 0 and settlement_amount == 0:
                return None

            # Parse date
            date_str = row.get('Date', '')
            transaction_date = self._parse_date(date_str)

            # Get status
            status = row.get('Status', '').strip()

            # Calculate net amount (settlement amount is usually the net after fees)
            # If no settlement amount, use the gross amount
            net_amount = settlement_amount if settlement_amount != 0 else amount

            # Infer fee from difference between amount and settlement amount
            fee = amount - settlement_amount if settlement_amount != 0 else Decimal('0')

            return {
                'mollie_id': row.get('ID', '').strip(),
                'booking_date': transaction_date,
                'amount': amount,
                'settlement_amount': settlement_amount,
                'amount_refunded': amount_refunded,
                'fee': fee,
                'net_amount': net_amount,
                'currency': row.get('Currency', 'EUR').strip(),
                'settlement_currency': row.get('Settlement currency', 'EUR').strip(),
                'status': status,
                'payment_method': row.get('Payment method', '').strip(),
                'description': row.get('Description', '').strip(),
                'consumer_name': row.get('Consumer name', '').strip(),
                'consumer_account': row.get('Consumer bank account', '').strip(),
                'consumer_bic': row.get('Consumer BIC', '').strip(),
                'settlement_reference': row.get('Settlement reference', '').strip(),
                'is_refund': amount_refunded > 0,
                'is_successful': status.lower() in ['paid', 'settled', 'authorized'],
                'raw_data': {k: v for k, v in row.items() if v}
            }

        except Exception as e:
            print(f"Error parsing Mollie transaction row: {e}")
            return None

    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse amount - handles various number formats"""
        if not amount_str or not amount_str.strip():
            return Decimal('0')

        amount_str = amount_str.strip()

        # Remove currency symbols if present
        amount_str = amount_str.replace('€', '').replace('EUR', '').strip()

        try:
            # First, determine format
            if ',' in amount_str and '.' not in amount_str:
                # German format: use comma as decimal separator
                amount_str = amount_str.replace(',', '.')
            elif ',' in amount_str and '.' in amount_str:
                # Check which is the decimal separator
                dot_pos = amount_str.rfind('.')
                comma_pos = amount_str.rfind(',')

                if comma_pos > dot_pos:
                    # German format: 1.234,56
                    amount_str = amount_str.replace('.', '').replace(',', '.')
                else:
                    # English format: 1,234.56
                    amount_str = amount_str.replace(',', '')

            # Handle negative amounts
            is_negative = amount_str.startswith('-') or amount_str.startswith('(') or amount_str.endswith('-')
            amount_str = amount_str.replace('-', '').replace('(', '').replace(')', '').strip()

            value = Decimal(amount_str)
            return -value if is_negative else value

        except Exception as e:
            print(f"Could not parse Mollie amount: {amount_str} - Error: {e}")
            return Decimal('0')

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse Mollie date format"""
        if not date_str or not date_str.strip():
            return None

        date_str = date_str.strip()

        # Mollie date formats - they often use ISO format
        formats = [
            '%Y-%m-%d %H:%M:%S',  # ISO with time
            '%Y-%m-%d',  # ISO date only
            '%d-%m-%Y %H:%M:%S',  # European with time
            '%d-%m-%Y',  # European date only
            '%d/%m/%Y %H:%M:%S',  # Alternative European with time
            '%d/%m/%Y',  # Alternative European date only
            '%Y/%m/%d',  # Alternative ISO
            '%m/%d/%Y',  # US format
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except:
                continue

        print(f"Could not parse Mollie date: {date_str}")
        return None

    def _save_to_database(self, db: Session, account_info: Dict, transactions: List[Dict], file_path: str) -> str:
        """Save Mollie import to database"""
        try:
            # Create import batch
            batch = ImportBatch(
                source_type='MOLLIE',
                source_file=os.path.basename(file_path),
                bank_info=account_info
            )
            db.add(batch)
            db.flush()

            print(f"Created Mollie import batch {batch.id}")

            # Save transactions
            saved_count = 0

            for i, trans in enumerate(transactions):
                try:
                    # Use net amount (settlement amount) as the transaction amount
                    amount = trans.get('net_amount', Decimal('0'))

                    # For refunds, make the amount negative
                    if trans.get('is_refund', False) and amount > 0:
                        amount = -amount

                    imported_trans = ImportedTransaction(
                        batch_id=batch.id,
                        source_type='MOLLIE',
                        booking_date=trans.get('booking_date'),
                        amount=amount,
                        description=self._build_description(trans),
                        account_number='MOLLIE',  # Virtual account number
                        account_name=trans.get('consumer_name', ''),
                        raw_data={
                            'mollie_id': trans.get('mollie_id'),
                            'status': trans.get('status'),
                            'currency': trans.get('currency'),
                            'settlement_currency': trans.get('settlement_currency'),
                            'fee': str(trans.get('fee', '0')),
                            'gross_amount': str(trans.get('amount', '0')),
                            'settlement_amount': str(trans.get('settlement_amount', '0')),
                            'payment_method': trans.get('payment_method'),
                            'settlement_reference': trans.get('settlement_reference')
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
            print(f"Successfully saved {saved_count} Mollie transactions")

            return str(batch.id)

        except Exception as e:
            print(f"Database save error: {e}")
            db.rollback()
            raise

    def _build_description(self, trans: Dict) -> str:
        """Build transaction description"""
        parts = []

        # Add payment method
        if trans.get('payment_method'):
            parts.append(f"Method: {trans['payment_method']}")

        # Add main description
        if trans.get('description'):
            parts.append(trans['description'])

        # Add consumer info if available
        if trans.get('consumer_name'):
            parts.append(f"From: {trans['consumer_name']}")

        # Add Mollie ID for reference
        if trans.get('mollie_id'):
            parts.append(f"Mollie ID: {trans['mollie_id']}")

        # Add settlement reference
        if trans.get('settlement_reference'):
            parts.append(f"Settlement: {trans['settlement_reference']}")

        # Add status if not standard
        if trans.get('status') and trans['status'].lower() not in ['paid', 'settled']:
            parts.append(f"Status: {trans['status']}")

        return ' | '.join(parts)[:500]  # Limit length
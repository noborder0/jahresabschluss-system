# src/infrastructure/importers/paypal.py

import os
import csv
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from .base import BaseImporter
from src.infrastructure.database.models import ImportedTransaction, ImportBatch


class PayPalImporter(BaseImporter):
    """
    Importer for PayPal CSV exports
    Supports German PayPal CSV format
    """

    def can_handle(self, filename: str) -> bool:
        """Check if this is a PayPal CSV file"""
        if not filename.lower().endswith('.csv'):
            return False

        # PayPal files often have generic names like "Download.CSV"
        filename_lower = filename.lower()
        return 'paypal' in filename_lower or 'download.csv' == filename_lower

    async def import_file(self, file_path: str, db: Session, metadata: Optional[Dict[str, Any]] = None) -> Dict[
        str, Any]:
        """Import PayPal CSV file"""
        print(f"PayPal Import: Processing {file_path}")

        try:
            # Parse CSV file
            transactions = self._parse_paypal_csv(file_path)

            if not transactions:
                raise Exception("No transactions found in PayPal CSV file")

            print(f"Parsed {len(transactions)} PayPal transactions")

            # Extract account info
            account_info = {
                'payment_provider': 'PayPal',
                'account_type': 'payment_provider',
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
                "source_type": "PAYPAL",
                "account_info": account_info,
                "transactions": transactions[:5]  # Preview first 5
            }

        except Exception as e:
            print(f"PayPal Import Error: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _parse_paypal_csv(self, csv_path: str) -> List[Dict[str, Any]]:
        """Parse PayPal CSV file"""
        transactions = []

        # PayPal exports are typically UTF-8
        encodings = ['utf-8', 'utf-8-sig', 'cp1252', 'iso-8859-1']

        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding, newline='') as f:
                    # Detect delimiter
                    sample = f.read(1024)
                    f.seek(0)

                    # PayPal uses comma as delimiter
                    delimiter = ','
                    if ';' in sample and ',' not in sample:
                        delimiter = ';'

                    reader = csv.DictReader(f, delimiter=delimiter)

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
        """Parse a single PayPal transaction row"""
        try:
            # Get the transaction type
            transaction_type = row.get('Typ', '').strip()

            # Skip certain transaction types (like currency conversions)
            if transaction_type in ['Allgemeine Währungsumrechnung', 'Währungsumrechnung']:
                return None

            # Parse amount (German format)
            brutto = self._parse_german_decimal(row.get('Brutto', '0'))
            gebuehr = self._parse_german_decimal(row.get('Gebühr', '0'))
            netto = self._parse_german_decimal(row.get('Netto', '0'))

            # Skip if all amounts are zero
            if brutto == 0 and netto == 0:
                return None

            # Parse date and time
            date_str = row.get('Datum', '').strip()
            time_str = row.get('Uhrzeit', '').strip()
            booking_date = self._parse_paypal_datetime(date_str, time_str)

            # Determine transaction direction
            is_income = brutto > 0

            return {
                'transaction_id': row.get('Transaktionscode', '').strip(),
                'related_transaction_id': row.get('Zugehöriger Transaktionscode', '').strip(),
                'booking_date': booking_date,
                'transaction_type': transaction_type,
                'status': row.get('Status', '').strip(),
                'currency': row.get('Währung', 'EUR').strip(),
                'gross_amount': brutto,
                'fee': gebuehr,
                'net_amount': netto,
                'partner_name': row.get('Name', '').strip(),
                'partner_email': row.get('Absender E-Mail-Adresse', '') or row.get('Empfänger E-Mail-Adresse', ''),
                'description': row.get('Betreff', '').strip(),
                'invoice_number': row.get('Empfangsnummer', '').strip(),
                'is_income': is_income,
                'raw_data': {k: v for k, v in row.items() if v}
            }

        except Exception as e:
            print(f"Error parsing PayPal transaction row: {e}")
            return None

    def _parse_paypal_datetime(self, date_str: str, time_str: str) -> Optional[datetime]:
        """Parse PayPal date and time format"""
        if not date_str:
            return None

        try:
            # Combine date and time
            datetime_str = f"{date_str} {time_str}" if time_str else date_str

            # Try different date formats
            formats = [
                '%d.%m.%Y %H:%M:%S',  # German format with time
                '%d.%m.%Y',  # German format without time
                '%Y-%m-%d %H:%M:%S',  # ISO format with time
                '%Y-%m-%d',  # ISO format without time
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(datetime_str.strip(), fmt).date()
                except:
                    continue

            print(f"Could not parse PayPal date: {datetime_str}")
            return None

        except Exception as e:
            print(f"Error parsing PayPal datetime: {e}")
            return None

    def _parse_german_decimal(self, value_str: str) -> Decimal:
        """Parse German decimal format (1.234,56)"""
        if not value_str or not value_str.strip():
            return Decimal('0')

        # Remove any currency symbols and whitespace
        value_str = value_str.strip()
        value_str = value_str.replace('€', '').replace('EUR', '').strip()

        # Handle negative numbers
        is_negative = value_str.startswith('-')
        if is_negative:
            value_str = value_str[1:]

        # Replace thousand separator and decimal separator
        value_str = value_str.replace('.', '').replace(',', '.')

        try:
            value = Decimal(value_str)
            return -value if is_negative else value
        except:
            print(f"Could not parse amount: {value_str}")
            return Decimal('0')

    def _save_to_database(self, db: Session, account_info: Dict, transactions: List[Dict], file_path: str) -> str:
        """Save PayPal import to database"""
        try:
            # Create import batch
            batch = ImportBatch(
                source_type='PAYPAL',
                source_file=os.path.basename(file_path),
                bank_info=account_info
            )
            db.add(batch)
            db.flush()

            print(f"Created PayPal import batch {batch.id}")

            # Save transactions
            saved_count = 0
            for i, trans in enumerate(transactions):
                try:
                    # Use net amount as the transaction amount
                    amount = trans.get('net_amount', Decimal('0'))

                    imported_trans = ImportedTransaction(
                        batch_id=batch.id,
                        source_type='PAYPAL',
                        booking_date=trans.get('booking_date'),
                        amount=amount,
                        description=self._build_description(trans),
                        account_number='PAYPAL',  # Virtual account number
                        account_name=trans.get('partner_name', ''),
                        raw_data=trans.get('raw_data', {})
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
            print(f"Successfully saved {saved_count} PayPal transactions")

            return str(batch.id)

        except Exception as e:
            print(f"Database save error: {e}")
            db.rollback()
            raise

    def _build_description(self, trans: Dict) -> str:
        """Build transaction description"""
        parts = []

        # Add transaction type
        if trans.get('transaction_type'):
            parts.append(trans['transaction_type'])

        # Add description/subject
        if trans.get('description'):
            parts.append(trans['description'])

        # Add partner info
        if trans.get('partner_name'):
            parts.append(f"Partner: {trans['partner_name']}")

        # Add transaction ID for reference
        if trans.get('transaction_id'):
            parts.append(f"ID: {trans['transaction_id']}")

        return ' | '.join(parts)[:500]  # Limit length
# src/infrastructure/importers/bank_csv.py

import os
import csv
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from pathlib import Path
from sqlalchemy.orm import Session
from .base import BaseImporter
from src.infrastructure.database.models import ImportedTransaction, ImportBatch


class BankCSVImporter(BaseImporter):
    """
    Importer for bank statements in CSV format
    Supports standard German bank export format with semicolon delimiter
    """

    def can_handle(self, filename: str) -> bool:
        """Check if this is a bank CSV file"""
        # Bank CSV files typically have "Konto" in the name or follow a specific pattern
        filename_lower = filename.lower()

        # Check for typical bank export patterns
        if 'konto' in filename_lower:
            return True

        # Check for pattern like "Konto_XXXXXX_DDMMYY_HHMMSS.csv"
        if re.match(r'.*\d{6,}_\d{6}_\d{6}\.csv', filename_lower):
            return True

        # Don't handle generic CSV files (leave those for DATEV)
        return False

    async def import_file(self, file_path: str, db: Session, metadata: Optional[Dict[str, Any]] = None) -> Dict[
        str, Any]:
        """Import bank CSV file with optional metadata"""
        print(f"Bank CSV Import: Processing {file_path}")
        if metadata:
            print(f"With metadata: {metadata}")

        try:
            # Extract metadata from filename
            bank_info = self._extract_bank_info_from_filename(file_path)

            # Merge with provided metadata
            if metadata:
                # Add user-provided metadata
                if metadata.get('account_name'):
                    bank_info['account_name'] = metadata['account_name']
                if metadata.get('iban'):
                    bank_info['iban'] = metadata['iban']
                if metadata.get('bic'):
                    bank_info['bic'] = metadata['bic']

            # Parse CSV file
            transactions = self._parse_bank_csv(file_path)

            if not transactions:
                raise Exception("No transactions found in CSV file")

            print(f"Parsed {len(transactions)} transactions")

            # Save to database
            import_id = self._save_to_database(db, bank_info, transactions, file_path)

            return {
                "import_id": import_id,
                "transaction_count": len(transactions),
                "source_type": "BANK_CSV",
                "bank_info": bank_info,
                "transactions": transactions[:5]  # Preview first 5
            }

        except Exception as e:
            print(f"Bank CSV Import Error: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _extract_bank_info_from_filename(self, file_path: str) -> Dict[str, str]:
        """Extract bank information from filename"""
        filename = os.path.basename(file_path)
        info = {}

        # Try to match pattern: Konto_XXXXXX_DDMMYY_HHMMSS.csv
        match = re.match(r'Konto_(\d+)_(\d{6})_(\d{6})', filename)
        if match:
            info['account_number'] = match.group(1)

            # Parse date
            date_str = match.group(2)
            try:
                # Assume DDMMYY format
                day = int(date_str[0:2])
                month = int(date_str[2:4])
                year = 2000 + int(date_str[4:6])
                info['export_date'] = f"{day:02d}.{month:02d}.{year}"
            except:
                info['export_date'] = date_str

            info['export_time'] = match.group(3)

        info['filename'] = filename
        return info

    def _parse_bank_csv(self, csv_path: str) -> List[Dict[str, Any]]:
        """Parse bank CSV file"""
        transactions = []

        # Bank exports are typically in cp1252 or iso-8859-1
        encodings = ['cp1252', 'iso-8859-1', 'utf-8', 'utf-8-sig']

        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding, newline='') as f:
                    # Read all content to check format
                    content = f.read()

                # Reset to beginning
                with open(csv_path, 'r', encoding=encoding, newline='') as f:
                    reader = csv.reader(f, delimiter=';', quotechar='"')

                    row_count = 0
                    for row in reader:
                        row_count += 1

                        # Skip empty rows
                        if not row or len(row) < 8:
                            continue

                        # Skip if essential fields are empty
                        if not row[0] or not row[1] or not row[2]:
                            continue

                        try:
                            transaction = self._parse_transaction_row(row)
                            if transaction:
                                transactions.append(transaction)

                                # Debug first transaction
                                if len(transactions) == 1:
                                    print(f"First transaction parsed:")
                                    print(f"  - Reference: {transaction.get('reference')}")
                                    print(f"  - Date: {transaction.get('booking_date')}")
                                    print(f"  - Amount: {transaction.get('amount')}")
                                    print(f"  - Partner: {transaction.get('partner_name')}")

                        except Exception as e:
                            print(f"Error parsing row {row_count}: {e}")
                            continue

                print(f"Successfully parsed {len(transactions)} transactions using {encoding}")
                return transactions

            except UnicodeDecodeError:
                print(f"Failed with {encoding} encoding, trying next...")
                continue
            except Exception as e:
                print(f"Error with {encoding}: {e}")
                continue

        print("Warning: Could not parse CSV file with any encoding")
        return transactions

    def _parse_transaction_row(self, row: List[str]) -> Dict[str, Any]:
        """
        Parse a single transaction row
        Expected format:
        0: Reference number
        1: Booking date
        2: Amount
        3: Value date
        4: Empty/Reserved
        5: Partner name
        6: Purpose/Description
        7: Account number
        """
        try:
            # Parse amount
            amount = self._parse_german_decimal(row[2])

            # Skip zero amounts
            if amount == 0:
                return None

            # Parse dates
            booking_date = self._parse_german_date(row[1])
            value_date = self._parse_german_date(row[3])

            # Extract additional info from purpose text
            purpose_info = self._parse_purpose_text(row[6])

            return {
                'reference': row[0].strip(),
                'booking_date': booking_date,
                'amount': amount,
                'value_date': value_date,
                'partner_name': row[5].strip(),
                'purpose': row[6].strip(),
                'account_number': row[7].strip() if len(row) > 7 else '',

                # Extracted from purpose
                'eref': purpose_info.get('eref'),
                'mref': purpose_info.get('mref'),
                'iban': purpose_info.get('iban'),
                'bic': purpose_info.get('bic'),
                'creditor_id': purpose_info.get('cred'),

                # Raw data for reference
                'raw_data': {
                    'reference': row[0],
                    'value_date': str(value_date) if value_date else None,
                    'purpose_full': row[6]
                }
            }

        except Exception as e:
            print(f"Error parsing transaction row: {e}")
            return None

    def _parse_purpose_text(self, purpose: str) -> Dict[str, str]:
        """Extract structured data from purpose text"""
        info = {}

        # Extract EREF (End-to-end reference)
        eref_match = re.search(r'EREF:\s*([^\s]+)', purpose)
        if eref_match:
            info['eref'] = eref_match.group(1)

        # Extract MREF (Mandate reference)
        mref_match = re.search(r'MREF:\s*([^\s]+)', purpose)
        if mref_match:
            info['mref'] = mref_match.group(1)

        # Extract IBAN
        iban_match = re.search(r'IBAN:\s*([A-Z]{2}\d{2}[A-Z0-9]+)', purpose)
        if iban_match:
            info['iban'] = iban_match.group(1)

        # Extract BIC
        bic_match = re.search(r'BIC:\s*([A-Z]{6}[A-Z0-9]{2,5})', purpose)
        if bic_match:
            info['bic'] = bic_match.group(1)

        # Extract CRED (Creditor ID)
        cred_match = re.search(r'CRED:\s*([^\s]+)', purpose)
        if cred_match:
            info['cred'] = cred_match.group(1)

        return info

    def _parse_german_date(self, date_str: str) -> datetime:
        """Parse German date format DD.MM.YYYY"""
        if not date_str or not date_str.strip():
            return None

        date_str = date_str.strip()

        try:
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except:
            # Try other formats
            for fmt in ['%d.%m.%y', '%Y-%m-%d', '%d-%m-%Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except:
                    continue

            print(f"Warning: Could not parse date: '{date_str}'")
            return None

    def _parse_german_decimal(self, amount_str: str) -> Decimal:
        """Parse German decimal format"""
        if not amount_str or not amount_str.strip():
            return Decimal('0')

        amount_str = amount_str.strip()

        # Handle negative values
        is_negative = amount_str.startswith('-')
        if is_negative:
            amount_str = amount_str[1:]

        # Replace comma with dot for decimal
        amount_str = amount_str.replace('.', '').replace(',', '.')

        try:
            value = Decimal(amount_str)
            return -value if is_negative else value
        except:
            print(f"Could not parse amount: {amount_str}")
            return Decimal('0')

    def _save_to_database(self, db: Session, bank_info: Dict, transactions: List[Dict], file_path: str) -> str:
        """Save import batch and transactions to database"""
        try:
            # Create import batch with enhanced bank info
            batch = ImportBatch(
                source_type='BANK_CSV',
                source_file=os.path.basename(file_path),
                bank_info=bank_info  # This now includes user-provided metadata
            )
            db.add(batch)
            db.flush()

            print(f"Created import batch {batch.id} with bank info: {bank_info}")

            # Save transactions
            saved_count = 0
            for i, trans in enumerate(transactions):
                try:
                    # Determine if it's a debit or credit based on amount
                    amount = trans.get('amount', Decimal('0'))

                    imported_trans = ImportedTransaction(
                        batch_id=batch.id,
                        source_type='BANK_CSV',
                        booking_date=trans.get('booking_date'),
                        amount=amount,
                        description=(trans.get('purpose', ''))[:500],  # Limit length
                        account_number=trans.get('account_number', ''),
                        account_name=(trans.get('partner_name', ''))[:100],  # Limit length
                        raw_data=trans.get('raw_data', {})
                    )
                    db.add(imported_trans)
                    saved_count += 1

                    # Commit in batches
                    if (i + 1) % 100 == 0:
                        db.flush()
                        print(f"  Saved {i + 1} transactions...")

                except Exception as e:
                    print(f"Error saving transaction {i + 1}: {e}")
                    continue

            db.commit()
            print(f"Successfully saved {saved_count} transactions")

            return str(batch.id)

        except Exception as e:
            print(f"Database save error: {e}")
            db.rollback()
            raise
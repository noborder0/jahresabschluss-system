# src/infrastructure/importers/datev.py

import csv
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from pathlib import Path
from sqlalchemy.orm import Session
from .base import BaseImporter
from src.infrastructure.database.models import ImportedTransaction, ImportBatch


class DATEVImporter(BaseImporter):
    """
    Importer for DATEV CSV files - supports both classic DATEV and document export formats
    """

    def can_handle(self, filename: str) -> bool:
        # Accept any CSV file - we'll detect the format later
        return filename.lower().endswith('.csv')

    async def import_file(self, file_path: str, db: Session) -> Dict[str, Any]:
        """
        Import DATEV CSV file - auto-detects format
        """
        try:
            # Detect CSV format
            csv_format = self._detect_csv_format(file_path)
            print(f"DATEV Import: Detected format: {csv_format}")

            transactions = []

            if csv_format == 'DATEV_CLASSIC':
                transactions = self._parse_datev_classic(file_path)
            elif csv_format == 'DATEV_DOCUMENT_EXPORT':
                transactions = self._parse_datev_document_export(file_path)
            else:
                # Try generic CSV parsing as fallback
                transactions = self._parse_generic_csv(file_path)

            # Debug logging
            print(f"DATEV Import: Parsed {len(transactions)} transactions")

            if not transactions:
                print("WARNING: No transactions parsed from file!")
                # Return with 0 transactions instead of failing
                return {
                    "import_id": None,
                    "transaction_count": 0,
                    "source_type": "DATEV",
                    "format": csv_format,
                    "transactions": []
                }

            # Save to database
            import_id = self._save_to_database(db, transactions, file_path, csv_format)

            return {
                "import_id": import_id,
                "transaction_count": len(transactions),
                "source_type": "DATEV",
                "format": csv_format,
                "transactions": transactions[:5]  # Preview
            }

        except Exception as e:
            print(f"DATEV Import Error: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _detect_csv_format(self, csv_path: str) -> str:
        """Detect which DATEV format the CSV uses"""
        try:
            # Try UTF-8-sig first (handles BOM)
            encodings = ['utf-8-sig', 'utf-8', 'cp1252', 'iso-8859-1']

            for encoding in encodings:
                try:
                    with open(csv_path, 'r', encoding=encoding) as f:
                        first_line = f.readline()

                        # Remove quotes and check for document export format
                        cleaned_line = first_line.strip().replace('"', '')

                        if 'Belegart' in cleaned_line and 'Geschäftspartner' in cleaned_line:
                            return 'DATEV_DOCUMENT_EXPORT'

                        # Check for classic DATEV format markers
                        if 'EXTF' in first_line or 'Umsatz' in first_line:
                            return 'DATEV_CLASSIC'

                except UnicodeDecodeError:
                    continue

        except Exception as e:
            print(f"Format detection error: {e}")

        return 'UNKNOWN'

    def _parse_datev_document_export(self, csv_path: str) -> List[Dict[str, Any]]:
        """Parse DATEV document export format (Belegexport)"""
        transactions = []

        print(f"Parsing DATEV document export: {csv_path}")

        try:
            # Read file with UTF-8-sig to handle BOM
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()

            if not lines:
                print("File is empty")
                return []

            # Process with standard CSV parser
            print("Using standard CSV parsing with BOM handling...")

            with open(csv_path, 'r', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile, delimiter=';', quotechar='"')

                # Clean up field names (remove quotes and whitespace)
                if reader.fieldnames:
                    cleaned_fieldnames = []
                    for field in reader.fieldnames:
                        # Remove quotes and whitespace
                        clean_field = field.strip().strip('"').strip()
                        cleaned_fieldnames.append(clean_field)
                    reader.fieldnames = cleaned_fieldnames
                    print(f"Cleaned field names: {reader.fieldnames[:5]}...")

                row_count = 0
                skipped_count = 0

                for row_num, row in enumerate(reader, 1):
                    row_count += 1

                    try:
                        # Create a new dict with cleaned keys
                        cleaned_row = {}
                        for key, value in row.items():
                            clean_key = key.strip().strip('"').strip() if key else key
                            cleaned_row[clean_key] = value

                        # Debug first row
                        if row_num == 1:
                            print(f"First row keys after cleaning: {list(cleaned_row.keys())[:5]}")
                            print(f"Belegart value: '{cleaned_row.get('Belegart', 'NOT FOUND')}'")

                        # Skip empty rows - check if Belegart exists and is not empty
                        belegart = cleaned_row.get('Belegart', '').strip()
                        if not belegart:
                            skipped_count += 1
                            continue

                        # Parse the transaction using cleaned row
                        transaction = self._parse_transaction_row(cleaned_row)
                        if transaction:
                            transactions.append(transaction)

                            # Debug first successful transaction
                            if len(transactions) == 1:
                                print(f"First transaction parsed successfully:")
                                print(f"  - Type: {transaction.get('document_type')}")
                                print(f"  - Partner: {transaction.get('partner_name')}")
                                print(f"  - Amount: {transaction.get('amount')}")

                    except Exception as e:
                        print(f"Error parsing row {row_num}: {e}")
                        if row_num == 1:
                            import traceback
                            traceback.print_exc()
                        continue

            print(
                f"Parsing complete: {row_count} rows read, {skipped_count} skipped, {len(transactions)} transactions parsed")

        except Exception as e:
            print(f"Error in _parse_datev_document_export: {e}")
            import traceback
            traceback.print_exc()

        return transactions

    def _parse_transaction_row(self, row: Dict[str, str]) -> Dict[str, Any]:
        """Parse a single transaction row"""
        try:
            # Skip if no Belegart
            if not row.get('Belegart', '').strip():
                return None

            # Parse amount - handle German decimal format
            amount_str = row.get('Rechnungsbetrag', '0').strip()
            amount = self._parse_german_decimal(amount_str) if amount_str else Decimal('0')

            # Skip transactions with zero amount
            if amount == 0:
                return None

            # Parse date
            date_str = row.get('Rechnungsdatum') or row.get('Eingangsdatum')
            booking_date = self._parse_german_date(date_str) if date_str else None

            # Determine if it's income or expense based on Belegart
            belegart = row.get('Belegart', '').strip()
            is_expense = belegart in ['R', 'K']  # R=Rechnung, K=Kreditkarte
            is_income = belegart in ['G', 'E']  # G=Gutschrift, E=Einnahme

            # Make negative amounts for income (Gutschrift)
            if is_income and amount > 0:
                amount = -amount

            return {
                'document_type': belegart,
                'partner_name': row.get('Geschäftspartner-Name', '').strip(),
                'partner_account': row.get('Geschäftspartner-Konto', '').strip(),
                'amount': amount,
                'currency': row.get('WKZ', 'EUR').strip(),
                'invoice_number': row.get('Rechnungs-Nr.', '').strip(),
                'booking_date': booking_date,
                'account': row.get('Konto', '').strip(),
                'account_description': row.get('Konto-Bezeichnung', '').strip(),
                'description': (row.get('Ware/Leistung', '') or row.get('Buchungstext', '')).strip(),
                'tax_rate': self._parse_tax_rate(row.get('Steuer in %', '')),
                'vat_id': row.get('USt-IdNr.', '').strip(),
                'iban': row.get('IBAN', '').strip(),
                'document_id': row.get('Beleg-ID', '').strip(),
                'document_path': row.get('Herkunft', '').strip(),
                'paid': row.get('Bezahlt', '').strip().lower() == 'ja',
                'paid_date': self._parse_german_date(row.get('BezahltAm', '')),
                'raw_data': {k: v for k, v in row.items() if v}  # Only non-empty values
            }
        except Exception as e:
            print(f"Error parsing transaction row: {e}")
            return None

    def _parse_datev_classic(self, csv_path: str) -> List[Dict[str, Any]]:
        """Parse classic DATEV format"""
        transactions = []

        with open(csv_path, 'r', encoding='cp1252') as f:  # DATEV uses Windows-1252
            # Skip header rows (DATEV has metadata rows)
            for _ in range(2):
                next(f)

            reader = csv.reader(f, delimiter=';')

            for row in reader:
                if len(row) < 10:  # Minimum expected columns
                    continue

                transaction = {
                    'amount': self._parse_german_decimal(row[0]),
                    'debit_credit': row[1],  # S or H
                    'account': row[2],
                    'contra_account': row[3],
                    'booking_date': self._parse_datev_date(row[4]),
                    'document_ref': row[5] if len(row) > 5 else '',
                    'description': row[7] if len(row) > 7 else '',
                    'tax_key': row[8] if len(row) > 8 else None,
                    'raw_data': row
                }

                transactions.append(transaction)

        return transactions

    def _parse_generic_csv(self, csv_path: str) -> List[Dict[str, Any]]:
        """Generic CSV parser as fallback"""
        transactions = []

        # Try to parse as generic CSV
        for encoding in ['utf-8', 'cp1252', 'iso-8859-1']:
            try:
                with open(csv_path, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)

                    for row in reader:
                        # Try to identify common fields
                        transaction = {
                            'description': '',
                            'amount': Decimal('0'),
                            'booking_date': None,
                            'raw_data': row
                        }

                        # Look for amount fields
                        for field in ['amount', 'betrag', 'Betrag', 'Amount', 'Rechnungsbetrag']:
                            if field in row and row[field]:
                                transaction['amount'] = self._parse_german_decimal(row[field])
                                break

                        # Look for date fields
                        for field in ['date', 'datum', 'Datum', 'Date', 'Rechnungsdatum', 'Buchungsdatum']:
                            if field in row and row[field]:
                                transaction['booking_date'] = self._parse_flexible_date(row[field])
                                break

                        # Look for description fields
                        for field in ['description', 'beschreibung', 'Beschreibung', 'Description', 'Verwendungszweck']:
                            if field in row and row[field]:
                                transaction['description'] = row[field]
                                break

                        transactions.append(transaction)

                return transactions

            except Exception:
                continue

        return transactions

    def _parse_german_decimal(self, value_str: str) -> Decimal:
        """Parse German decimal format (1.234,56)"""
        if not value_str or not value_str.strip():
            return Decimal('0')

        # Remove any whitespace
        value_str = value_str.strip()

        # Handle negative numbers with minus
        is_negative = False
        if value_str.startswith('-'):
            is_negative = True
            value_str = value_str[1:]

        # Remove thousand separators (dots) and replace comma with dot
        value_str = value_str.replace('.', '').replace(',', '.')

        try:
            value = Decimal(value_str)
            return -value if is_negative else value
        except:
            print(f"Warning: Could not parse decimal value: '{value_str}'")
            return Decimal('0')

    def _parse_german_date(self, date_str: str) -> datetime:
        """Parse German date format DD.MM.YYYY"""
        if not date_str or not date_str.strip():
            return None

        date_str = date_str.strip()

        try:
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except:
            # Try other formats
            for fmt in ['%d.%m.%y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except:
                    continue

            print(f"Warning: Could not parse date: '{date_str}'")
            return None

    def _parse_datev_date(self, date_str: str) -> datetime:
        """Parse DATEV date format (DDMM or DDMMYYYY)"""
        if not date_str:
            return None

        if len(date_str) == 4:  # DDMM format
            day = int(date_str[:2])
            month = int(date_str[2:4])
            year = datetime.now().year
            return datetime(year, month, day).date()
        elif len(date_str) == 8:  # DDMMYYYY format
            day = int(date_str[:2])
            month = int(date_str[2:4])
            year = int(date_str[4:8])
            return datetime(year, month, day).date()

        return None

    def _parse_flexible_date(self, date_str: str) -> datetime:
        """Try multiple date formats"""
        if not date_str:
            return None

        formats = [
            '%d.%m.%Y',  # German
            '%Y-%m-%d',  # ISO
            '%d/%m/%Y',  # European
            '%m/%d/%Y',  # US
            '%d-%m-%Y',  # Alternative
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except:
                continue

        return None

    def _parse_tax_rate(self, tax_str: str) -> Decimal:
        """Parse tax rate string"""
        if not tax_str:
            return None

        # Remove % sign and parse
        tax_str = tax_str.replace('%', '').strip()
        return self._parse_german_decimal(tax_str)

    def _save_to_database(self, db: Session, transactions: List[Dict], file_path: str, csv_format: str) -> str:
        """Save import to database with format info"""
        print(f"Saving {len(transactions)} transactions to database...")

        try:
            # Create import batch
            batch = ImportBatch(
                source_type='DATEV',
                source_file=os.path.basename(file_path),  # Only store filename, not full path
                bank_info={'format': csv_format, 'transaction_count': len(transactions)}
            )
            db.add(batch)
            db.flush()  # Get the batch ID

            print(f"Created import batch with ID: {batch.id}")

            saved_count = 0
            errors = []

            # Save transactions based on format
            if csv_format == 'DATEV_DOCUMENT_EXPORT':
                for i, trans in enumerate(transactions):
                    try:
                        # Create a simplified raw_data without the full row
                        simplified_raw = {
                            'document_type': trans.get('document_type'),
                            'invoice_number': trans.get('invoice_number'),
                            'document_id': trans.get('document_id'),
                            'partner_name': trans.get('partner_name')
                        }

                        imported_trans = ImportedTransaction(
                            batch_id=batch.id,
                            source_type='DATEV',
                            booking_date=trans.get('booking_date'),
                            amount=trans.get('amount', Decimal('0')),
                            description=(trans.get('description', '') or trans.get('partner_name', ''))[:500],
                            # Limit length
                            account_number=trans.get('account', ''),
                            contra_account=trans.get('partner_account', ''),
                            account_name=(trans.get('partner_name', ''))[:100],  # Limit length
                            raw_data=simplified_raw  # Store simplified data
                        )
                        db.add(imported_trans)
                        saved_count += 1

                        # Commit in batches to avoid memory issues
                        if (i + 1) % 100 == 0:
                            db.flush()
                            print(f"  Saved {i + 1} transactions...")

                    except Exception as e:
                        errors.append(f"Row {i + 1}: {str(e)}")
                        print(f"  Error saving transaction {i + 1}: {e}")

            else:
                # Classic format or generic
                for i, trans in enumerate(transactions):
                    try:
                        # Determine debit/credit accounts for classic format
                        if trans.get('debit_credit') == 'S':
                            debit_account = trans.get('account', '')
                            credit_account = trans.get('contra_account', '')
                        else:
                            debit_account = trans.get('contra_account', '')
                            credit_account = trans.get('account', '')

                        imported_trans = ImportedTransaction(
                            batch_id=batch.id,
                            source_type='DATEV',
                            booking_date=trans.get('booking_date'),
                            amount=trans.get('amount', Decimal('0')),
                            description=(trans.get('description', ''))[:500],  # Limit length
                            account_number=debit_account or trans.get('account', ''),
                            contra_account=credit_account or trans.get('contra_account', ''),
                            raw_data={'row_number': i}  # Minimal raw data
                        )
                        db.add(imported_trans)
                        saved_count += 1

                        # Commit in batches
                        if (i + 1) % 100 == 0:
                            db.flush()

                    except Exception as e:
                        errors.append(f"Row {i + 1}: {str(e)}")
                        print(f"  Error saving transaction {i + 1}: {e}")

            # Final commit
            db.commit()
            print(f"Successfully saved {saved_count} out of {len(transactions)} transactions")

            if errors:
                print(f"Errors encountered: {len(errors)}")
                for error in errors[:5]:  # Show first 5 errors
                    print(f"  - {error}")

            return str(batch.id)

        except Exception as e:
            print(f"Database save failed: {e}")
            db.rollback()
            raise
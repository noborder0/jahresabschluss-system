# src/infrastructure/importers/datev.py

import csv
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from .base import BaseImporter
from src.infrastructure.database.models import ImportedTransaction, ImportBatch


class DATEVImporter(BaseImporter):
    """
    Importer for DATEV CSV files
    """

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith('.csv') and 'datev' in filename.lower()

    async def import_file(self, file_path: str, db: Session) -> Dict[str, Any]:
        """
        Import DATEV CSV file
        """
        transactions = self._parse_datev_csv(file_path)
        import_id = self._save_to_database(db, transactions, file_path)

        return {
            "import_id": import_id,
            "transaction_count": len(transactions),
            "source_type": "DATEV",
            "transactions": transactions[:5]  # Preview
        }

    def _parse_datev_csv(self, csv_path: str) -> List[Dict[str, Any]]:
        """Parse DATEV CSV format"""
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
                    'amount': self._parse_amount(row[0]),
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

    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse DATEV amount format"""
        if not amount_str:
            return Decimal('0')
        return Decimal(amount_str.replace(',', '.'))

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

    def _save_to_database(self, db: Session, transactions: List[Dict], file_path: str) -> str:
        """Save DATEV import to database"""
        # Create import batch
        batch = ImportBatch(
            source_type='DATEV',
            source_file=file_path
        )
        db.add(batch)
        db.flush()

        # Save transactions
        for trans in transactions:
            # Determine debit/credit accounts based on S/H flag
            if trans['debit_credit'] == 'S':
                debit_account = trans['account']
                credit_account = trans['contra_account']
            else:
                debit_account = trans['contra_account']
                credit_account = trans['account']

            imported_trans = ImportedTransaction(
                batch_id=batch.id,
                source_type='DATEV',
                booking_date=trans['booking_date'],
                amount=trans['amount'],
                description=trans['description'],
                account_number=debit_account,
                contra_account=credit_account,
                raw_data=trans['raw_data']
            )
            db.add(imported_trans)

        db.commit()
        return str(batch.id)
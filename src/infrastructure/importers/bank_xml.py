# src/infrastructure/importers/bank_xml.py

import xml.etree.ElementTree as ET
import csv
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from pathlib import Path
import json
from sqlalchemy.orm import Session
from .base import BaseImporter
from src.infrastructure.database.models import ImportedTransaction, ImportBatch


class BankXMLImporter(BaseImporter):
    """
    Importer for bank statements in GDPdU XML format
    """

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith('.xml')

    async def import_file(self, file_path: str, db: Session) -> Dict[str, Any]:
        """
        Import bank XML file and associated CSV
        """
        # Parse XML
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Extract metadata
        bank_info = self._extract_bank_info(root)

        # Find CSV file referenced in XML
        csv_filename = root.find('.//Table/URL').text
        csv_path = Path(file_path).parent / csv_filename

        # Extract column schema
        columns = self._extract_column_schema(root)

        # Import CSV data
        transactions = self._parse_csv_file(str(csv_path), columns)

        # Save to database
        import_id = self._save_to_database(db, bank_info, transactions, file_path)

        return {
            "import_id": import_id,
            "transaction_count": len(transactions),
            "source_type": "BANK_XML",
            "bank_info": bank_info,
            "transactions": transactions[:5]  # Return first 5 as preview
        }

    def _extract_bank_info(self, root: ET.Element) -> Dict[str, str]:
        """Extract bank information from XML"""
        data_supplier = root.find('.//DataSupplier')
        return {
            'name': data_supplier.find('Name').text if data_supplier else '',
            'location': data_supplier.find('Location').text.strip('"') if data_supplier else '',
            'comment': data_supplier.find('Comment').text.strip('"') if data_supplier else ''
        }

    def _extract_column_schema(self, root: ET.Element) -> List[Dict[str, str]]:
        """Extract column definitions from XML"""
        columns = []

        for col in root.findall('.//VariableColumn'):
            name = col.find('Name').text
            col_type = 'text'  # Default

            if col.find('.//Numeric') is not None:
                col_type = 'numeric'
            elif col.find('.//Date') is not None:
                col_type = 'date'

            columns.append({
                'name': name,
                'type': col_type
            })

        return columns

    def _parse_csv_file(self, csv_path: str, columns: List[Dict]) -> List[Dict[str, Any]]:
        """Parse CSV file with given schema"""
        transactions = []

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')

            for row in reader:
                transaction = {
                    'booking_id': row.get('Buchungs-ID', ''),
                    'booking_date': self._parse_date(row.get('Buchungstag', '')),
                    'amount': self._parse_amount(row.get('Betrag', '0')),
                    'value_date': self._parse_date(row.get('Valuta', '')),
                    'name': row.get('Name', ''),
                    'description': row.get('Verwendungszweck', ''),
                    'raw_data': row
                }
                transactions.append(transaction)

        return transactions

    def _parse_date(self, date_str: str) -> datetime:
        """Parse German date format DD.MM.YYYY"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except:
            return None

    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse German decimal format"""
        if not amount_str:
            return Decimal('0')
        # Replace comma with dot
        amount_str = amount_str.replace(',', '.')
        return Decimal(amount_str)

    def _save_to_database(self, db: Session, bank_info: Dict, transactions: List[Dict], file_path: str) -> str:
        """Save import batch and transactions to database"""
        # Create import batch
        batch = ImportBatch(
            source_type='BANK_XML',
            source_file=file_path,
            bank_info=bank_info
        )
        db.add(batch)
        db.flush()

        # Save transactions
        for trans in transactions:
            imported_trans = ImportedTransaction(
                batch_id=batch.id,
                source_type='BANK_XML',
                booking_date=trans['booking_date'],
                amount=trans['amount'],
                description=trans['description'],
                account_name=trans['name'],
                raw_data=trans['raw_data']
            )
            db.add(imported_trans)

        db.commit()
        return str(batch.id)
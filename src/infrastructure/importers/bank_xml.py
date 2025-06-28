# src/infrastructure/importers/bank_xml.py

import xml.etree.ElementTree as ET
import csv
import os
import re
import io
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
        print(f"Bank XML Import: Processing {file_path}")

        try:
            # Read the file content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                xml_content = f.read()

            # Clean and fix the XML content
            # Remove BOM if present
            xml_content = xml_content.lstrip('\ufeff')

            # Fix known issues with bank XML files
            # Replace <n> with <Name> (common error in some bank exports)
            xml_content = xml_content.replace('<n>', '<Name>')
            xml_content = xml_content.replace('</n>', '</Name>')

            # Find the end of the XML document and trim everything after it
            dataset_end = xml_content.find('</DataSet>')
            if dataset_end > 0:
                xml_content = xml_content[:dataset_end + len('</DataSet>')]
                print(f"Trimmed XML content to {len(xml_content)} characters")

            # Remove control characters except newlines, carriage returns and tabs
            xml_content = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', xml_content)

            # Parse the cleaned XML
            root = ET.fromstring(xml_content)
            tree = ET.ElementTree(root)
            print("XML parsed successfully")

            # Extract metadata
            bank_info = self._extract_bank_info(root)
            print(f"Bank info: {bank_info}")

            # Find CSV file referenced in XML
            csv_filename = self._find_csv_filename(root)
            if not csv_filename:
                raise Exception("No CSV file reference found in XML")

            csv_path = Path(file_path).parent / csv_filename
            print(f"Looking for CSV at: {csv_path}")

            if not csv_path.exists():
                # Try case-insensitive search
                parent_dir = Path(file_path).parent
                csv_files = list(parent_dir.glob('*.csv')) + list(parent_dir.glob('*.CSV'))

                # Find matching CSV by name (case-insensitive)
                matching_csv = None
                csv_base = Path(csv_filename).stem.lower()
                for csv_file in csv_files:
                    if csv_file.stem.lower() == csv_base:
                        matching_csv = csv_file
                        break

                if matching_csv:
                    csv_path = matching_csv
                    print(f"Found CSV with different case: {csv_path}")
                else:
                    # List available CSV files for debugging
                    print(f"Available CSV files in {parent_dir}:")
                    for csv_file in csv_files:
                        print(f"  - {csv_file.name}")
                    raise Exception(f"CSV file not found: {csv_filename}")

            # Extract column schema from XML
            columns = self._extract_column_schema(root)
            print(f"Found {len(columns)} columns in XML schema")

            if not columns:
                raise Exception("No column schema found in XML")

            # Import CSV data with the schema
            transactions = self._parse_csv_file(str(csv_path), columns)
            print(f"Parsed {len(transactions)} transactions from CSV")

            if not transactions:
                raise Exception("No transactions found in CSV file")

            # Save to database
            import_id = self._save_to_database(db, bank_info, transactions, file_path)

            return {
                "import_id": import_id,
                "transaction_count": len(transactions),
                "source_type": "BANK_XML",
                "bank_info": bank_info,
                "transactions": transactions[:5]  # Return first 5 as preview
            }

        except Exception as e:
            print(f"Bank XML Import Error: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _extract_bank_info(self, root: ET.Element) -> Dict[str, str]:
        """Extract bank information from XML"""
        data_supplier = root.find('.//DataSupplier')
        if data_supplier is not None:
            info = {}

            # Get Name element
            name_elem = data_supplier.find('Name')
            if name_elem is not None and name_elem.text:
                info['name'] = self._get_text(name_elem)
            else:
                # Sometimes the bank name might be in a child element
                for child in data_supplier:
                    if child.tag.lower() == 'name' or child.tag == 'n':
                        info['name'] = self._get_text(child)
                        break

            # Get other elements
            location_elem = data_supplier.find('Location')
            if location_elem is not None:
                info['location'] = self._clean_quoted_text(self._get_text(location_elem))

            comment_elem = data_supplier.find('Comment')
            if comment_elem is not None:
                info['comment'] = self._clean_quoted_text(self._get_text(comment_elem))

            return info
        return {}

    def _find_csv_filename(self, root: ET.Element) -> str:
        """Find CSV filename from XML"""
        url_element = root.find('.//Table/URL')
        if url_element is not None:
            return url_element.text
        return None

    def _get_text(self, element: ET.Element) -> str:
        """Safely get text from XML element"""
        return element.text if element is not None and element.text else ''

    def _clean_quoted_text(self, text: str) -> str:
        """Remove quotes from text"""
        return text.strip('"') if text else ''

    def _extract_column_schema(self, root: ET.Element) -> List[Dict[str, str]]:
        """Extract column definitions from XML"""
        columns = []

        for col in root.findall('.//VariableColumn'):
            name = self._get_text(col.find('Name'))
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

        # Try different encodings
        encodings = ['cp1252', 'iso-8859-1', 'utf-8', 'utf-8-sig']

        for encoding in encodings:
            try:
                print(f"Trying to read CSV with {encoding} encoding...")

                with open(csv_path, 'r', encoding=encoding) as f:
                    # Read all lines
                    lines = f.readlines()

                if not lines:
                    print("CSV file is empty")
                    continue

                # Check if lines are wrapped in quotes
                if lines and lines[0].startswith('"') and lines[0].rstrip().endswith('"'):
                    print("Detected quoted CSV format, cleaning...")
                    # Clean lines - remove outer quotes
                    cleaned_lines = []
                    for line in lines:
                        line = line.strip()
                        if line.startswith('"') and line.endswith('"'):
                            line = line[1:-1]  # Remove outer quotes
                        cleaned_lines.append(line)

                    # Parse cleaned lines
                    import io
                    csv_content = '\n'.join(cleaned_lines)
                    csvfile = io.StringIO(csv_content)
                else:
                    # Read file again for parsing
                    csvfile = open(csv_path, 'r', encoding=encoding)

                try:
                    # Create column names from XML schema
                    fieldnames = [col['name'] for col in columns]

                    # Parse CSV without header (fieldnames from XML)
                    reader = csv.DictReader(csvfile, fieldnames=fieldnames, delimiter=';')

                    row_count = 0
                    for row in reader:
                        row_count += 1

                        try:
                            transaction = self._parse_transaction_row(row, columns)
                            if transaction:
                                transactions.append(transaction)

                                # Debug first transaction
                                if len(transactions) == 1:
                                    print(f"First transaction parsed:")
                                    print(f"  - ID: {transaction.get('booking_id')}")
                                    print(f"  - Date: {transaction.get('booking_date')}")
                                    print(f"  - Amount: {transaction.get('amount')}")
                                    print(f"  - Name: {transaction.get('name')}")

                        except Exception as e:
                            print(f"Error parsing row {row_count}: {e}")
                            continue

                    print(f"Successfully parsed {len(transactions)} from {row_count} rows using {encoding}")
                    return transactions

                finally:
                    if hasattr(csvfile, 'close'):
                        csvfile.close()

            except UnicodeDecodeError:
                print(f"Failed with {encoding} encoding, trying next...")
                continue
            except Exception as e:
                print(f"Error with {encoding}: {e}")
                continue

        print(f"Warning: Could not parse CSV file with any encoding")
        return transactions

    def _parse_transaction_row(self, row: Dict[str, str], columns: List[Dict]) -> Dict[str, Any]:
        """Parse a single transaction row based on column schema"""
        try:
            transaction = {
                'raw_data': dict(row)
            }

            # Map columns based on schema
            for col in columns:
                col_name = col['name']
                col_type = col['type']
                value = row.get(col_name, '')

                if col_name == 'Buchungs-ID':
                    transaction['booking_id'] = value
                elif col_name == 'Buchungstag':
                    transaction['booking_date'] = self._parse_date(value)
                elif col_name == 'Betrag':
                    transaction['amount'] = self._parse_amount(value)
                elif col_name == 'Valuta':
                    transaction['value_date'] = self._parse_date(value)
                elif col_name == 'Name':
                    transaction['name'] = value
                elif col_name == 'Verwendungszweck':
                    transaction['description'] = value
                elif col_name == 'Verdichtungs-ID':
                    transaction['consolidation_id'] = value
                elif col_name == 'Alt-RZBK':
                    transaction['alt_rzbk'] = value

            # Skip transactions without essential fields
            if not transaction.get('amount') or transaction['amount'] == 0:
                return None

            return transaction

        except Exception as e:
            print(f"Error parsing transaction row: {e}")
            return None

    def _parse_date(self, date_str: str) -> datetime:
        """Parse German date format DD.MM.YYYY"""
        if not date_str or not date_str.strip():
            return None

        date_str = date_str.strip()

        try:
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except:
            # Try other formats
            for fmt in ['%d.%m.%y', '%Y-%m-%d']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except:
                    continue
            return None

    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse German decimal format"""
        if not amount_str or not amount_str.strip():
            return Decimal('0')

        amount_str = amount_str.strip()

        # Handle negative values
        is_negative = amount_str.startswith('-')
        if is_negative:
            amount_str = amount_str[1:]

        # Replace comma with dot for decimal
        amount_str = amount_str.replace(',', '.')

        try:
            value = Decimal(amount_str)
            return -value if is_negative else value
        except:
            print(f"Could not parse amount: {amount_str}")
            return Decimal('0')

    def _save_to_database(self, db: Session, bank_info: Dict, transactions: List[Dict], file_path: str) -> str:
        """Save import batch and transactions to database"""
        try:
            # Create import batch
            batch = ImportBatch(
                source_type='BANK_XML',
                source_file=os.path.basename(file_path),
                bank_info=bank_info
            )
            db.add(batch)
            db.flush()

            print(f"Created import batch {batch.id}")

            # Save transactions
            saved_count = 0
            for i, trans in enumerate(transactions):
                try:
                    imported_trans = ImportedTransaction(
                        batch_id=batch.id,
                        source_type='BANK_XML',
                        booking_date=trans.get('booking_date'),
                        amount=trans.get('amount', Decimal('0')),
                        description=(trans.get('description', ''))[:500],  # Limit length
                        account_name=(trans.get('name', ''))[:100],  # Limit length
                        raw_data={
                            'booking_id': trans.get('booking_id'),
                            'value_date': str(trans.get('value_date')) if trans.get('value_date') else None,
                            'consolidation_id': trans.get('consolidation_id')
                        }
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
#!/usr/bin/env python3
"""
Debug script to test CSV import without web interface
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import after setting path
from src.infrastructure.importers.datev import DATEVImporter
from src.infrastructure.database.connection import SessionLocal, init_db
from src.infrastructure.database.models import ImportBatch, ImportedTransaction
from sqlalchemy import func


async def debug_import(csv_file: str):
    """Debug the import process step by step"""
    print("\n=== DEBUG IMPORT PROCESS ===\n")

    # Step 1: Test file reading
    print("1. Testing file access...")
    if not os.path.exists(csv_file):
        print(f"   ❌ File not found: {csv_file}")
        return

    file_size = os.path.getsize(csv_file)
    print(f"   ✓ File exists, size: {file_size:,} bytes")

    # Step 2: Test importer without database
    print("\n2. Testing DATEV importer parsing...")
    importer = DATEVImporter()

    # Test format detection
    format_type = importer._detect_csv_format(csv_file)
    print(f"   - Detected format: {format_type}")

    # Test parsing
    try:
        if format_type == 'DATEV_DOCUMENT_EXPORT':
            transactions = importer._parse_datev_document_export(csv_file)
        elif format_type == 'DATEV_CLASSIC':
            transactions = importer._parse_datev_classic(csv_file)
        else:
            transactions = importer._parse_generic_csv(csv_file)

        print(f"   ✓ Parsed {len(transactions)} transactions")

        if transactions:
            print(f"\n   Sample transaction:")
            trans = transactions[0]
            for key, value in list(trans.items())[:5]:
                print(f"     - {key}: {value}")

    except Exception as e:
        print(f"   ❌ Parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 3: Test database import
    print("\n3. Testing database import...")

    try:
        # Initialize database if needed
        init_db()

        # Create database session
        db = SessionLocal()

        # Run the actual import
        result = await importer.import_file(csv_file, db)

        print(f"   - Import result:")
        print(f"     * import_id: {result.get('import_id')}")
        print(f"     * transaction_count: {result.get('transaction_count')}")
        print(f"     * source_type: {result.get('source_type')}")
        print(f"     * format: {result.get('format')}")

        # Verify in database
        import_id = result.get('import_id')
        if import_id:
            print(f"\n4. Verifying database records...")

            # Check import batch
            batch = db.query(ImportBatch).filter_by(id=import_id).first()
            if batch:
                print(f"   ✓ Import batch found: {batch.source_file}")
            else:
                print(f"   ❌ Import batch NOT found!")

            # Count transactions
            trans_count = db.query(func.count(ImportedTransaction.id)) \
                .filter_by(batch_id=import_id).scalar()
            print(f"   - Transactions in DB: {trans_count}")

            # Show sample transaction
            sample_trans = db.query(ImportedTransaction) \
                .filter_by(batch_id=import_id).first()
            if sample_trans:
                print(f"\n   Sample DB transaction:")
                print(f"     - Amount: {sample_trans.amount}")
                print(f"     - Date: {sample_trans.booking_date}")
                print(f"     - Description: {sample_trans.description}")

        db.close()

    except Exception as e:
        print(f"   ❌ Database import failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n=== END DEBUG ===")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Try to find export 1.csv in current directory
        if os.path.exists("export 1.csv"):
            csv_file = "export 1.csv"
        else:
            print("Usage: python debug_import.py <csv_file>")
            print("   or: python debug_import.py  (will look for 'export 1.csv')")
            sys.exit(1)
    else:
        csv_file = sys.argv[1]

    asyncio.run(debug_import(csv_file))
#!/usr/bin/env python3
"""
Detailed debug script to analyze CSV parsing issues
"""

import csv
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def debug_csv_parsing(csv_file: str):
    """Debug CSV parsing in detail"""
    print("\n=== DETAILED CSV PARSING DEBUG ===\n")

    # Step 1: Read raw file
    print("1. Reading raw file...")
    with open(csv_file, 'rb') as f:
        raw_bytes = f.read(500)
        print(f"   First 500 bytes (raw): {raw_bytes[:100]}...")

    # Step 2: Try to read with different encodings
    print("\n2. Testing encodings...")
    for encoding in ['utf-8', 'cp1252', 'iso-8859-1']:
        try:
            with open(csv_file, 'r', encoding=encoding) as f:
                first_line = f.readline()
                print(f"   {encoding}: First line = {first_line[:100]}...")
                break
        except Exception as e:
            print(f"   {encoding}: Failed - {e}")

    # Step 3: Check for escaped quotes
    print("\n3. Checking for escaped quotes...")
    with open(csv_file, 'r', encoding='utf-8') as f:
        content = f.read(1000)
        has_escaped_quotes = '\\"' in content
        print(f"   Has escaped quotes (\\\"): {has_escaped_quotes}")
        if has_escaped_quotes:
            print("   Sample: ", content[content.find('\\"'):content.find('\\"') + 20])

    # Step 4: Parse with csv.DictReader and debug
    print("\n4. Parsing with csv.DictReader...")
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')

        # Show detected fields
        print(f"   Detected fields ({len(reader.fieldnames)}): ")
        for i, field in enumerate(reader.fieldnames[:5]):
            print(f"     [{i}] '{field}' (length: {len(field)})")

        # Read first few rows
        print("\n   First 3 rows:")
        for i, row in enumerate(reader):
            if i >= 3:
                break
            print(f"\n   Row {i + 1}:")
            # Check key fields
            belegart = row.get('Belegart', 'NOT FOUND')
            print(f"     - Belegart: '{belegart}' (type: {type(belegart)}, len: {len(str(belegart))})")

            # Try different field name variations
            for field_variation in ['Belegart', '"Belegart"', '\\Belegart', '\\"Belegart\\"']:
                if field_variation in row:
                    print(f"     - Found with key: '{field_variation}' = '{row[field_variation]}'")

            # Show all keys
            print(f"     - All keys: {list(row.keys())[:3]}...")

            # Show first non-empty value
            for key, value in row.items():
                if value and value.strip():
                    print(f"     - First non-empty: '{key}' = '{value}'")
                    break

    # Step 5: Try cleaning the file
    print("\n5. Testing file cleaning...")

    # Read and clean
    with open(csv_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"   Total lines: {len(lines)}")

    # Check if wrapped in quotes
    if lines and lines[0].startswith('"') and lines[0].rstrip().endswith('"'):
        print("   File appears to be wrapped in quotes")

        # Clean the lines
        cleaned_lines = []
        for line in lines:
            # Remove outer quotes
            if line.startswith('"') and line.rstrip().endswith('"'):
                line = line[1:-2] + '\n'  # Remove first and last quote, keep newline
            # Unescape inner quotes
            line = line.replace('\\"', '"')
            cleaned_lines.append(line)

        # Parse cleaned content
        print("\n6. Parsing cleaned content...")
        import io
        cleaned_content = ''.join(cleaned_lines)

        # Parse with csv.DictReader
        reader = csv.DictReader(io.StringIO(cleaned_content), delimiter=';')

        print(f"   Cleaned fields: {reader.fieldnames[:5]}...")

        row_count = 0
        transaction_count = 0

        for row in reader:
            row_count += 1
            if row.get('Belegart'):
                transaction_count += 1
                if transaction_count == 1:
                    print(f"\n   First valid transaction:")
                    print(f"     - Belegart: {row.get('Belegart')}")
                    print(f"     - Partner: {row.get('Geschäftspartner-Name')}")
                    print(f"     - Amount: {row.get('Rechnungsbetrag')}")

        print(f"\n   Results after cleaning:")
        print(f"     - Total rows: {row_count}")
        print(f"     - Valid transactions: {transaction_count}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        if os.path.exists("export 1.csv"):
            csv_file = "export 1.csv"
        else:
            print("Usage: python debug_csv_detail.py <csv_file>")
            sys.exit(1)
    else:
        csv_file = sys.argv[1]

    debug_csv_parsing(csv_file)
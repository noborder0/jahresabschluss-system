# src/infrastructure/ai_services/azure_document.py
"""
Azure Document Intelligence integration for PDF and image processing
"""

import os
import base64
from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal
import logging

# Azure SDK imports
try:
    from azure.ai.formrecognizer import DocumentAnalysisClient
    from azure.core.credentials import AzureKeyCredential

    AZURE_SDK_AVAILABLE = True
except ImportError:
    AZURE_SDK_AVAILABLE = False
    print("WARNING: Azure SDK not installed. Install with: pip install azure-ai-formrecognizer")

from src.core.config import settings

logger = logging.getLogger(__name__)


class AzureDocumentProcessor:
    """
    Process documents using Azure Document Intelligence (formerly Form Recognizer)
    """

    def __init__(self):
        if not AZURE_SDK_AVAILABLE:
            raise ImportError("Azure SDK not available. Install azure-ai-formrecognizer")

        if not settings.azure_form_recognizer_endpoint or not settings.azure_form_recognizer_key:
            raise ValueError("Azure Document Intelligence credentials not configured")

        self.client = DocumentAnalysisClient(
            endpoint=settings.azure_form_recognizer_endpoint,
            credential=AzureKeyCredential(settings.azure_form_recognizer_key)
        )

        # Determine which model to use
        self.model_id = "prebuilt-invoice" if settings.azure_use_prebuilt_model else "prebuilt-document"

    async def analyze_document(self, file_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Analyze a document (PDF or image) and extract relevant information

        Args:
            file_data: Binary content of the document
            filename: Original filename for type detection

        Returns:
            Extracted document information
        """
        try:
            # Determine content type
            content_type = self._get_content_type(filename)

            logger.info(f"Analyzing document: {filename} with model: {self.model_id}")

            # Start analysis
            poller = self.client.begin_analyze_document(
                model_id=self.model_id,
                document=file_data,
                content_type=content_type
            )

            # Wait for completion
            result = poller.result()

            # Extract relevant information based on document type
            if self.model_id == "prebuilt-invoice":
                return self._extract_invoice_data(result)
            else:
                return self._extract_general_document_data(result)

        except Exception as e:
            logger.error(f"Error analyzing document {filename}: {e}")
            raise

    def _get_content_type(self, filename: str) -> str:
        """Determine content type from filename"""
        ext = filename.lower().split('.')[-1]
        content_types = {
            'pdf': 'application/pdf',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'tiff': 'image/tiff',
            'tif': 'image/tiff',
            'bmp': 'image/bmp'
        }
        return content_types.get(ext, 'application/octet-stream')

    def _extract_invoice_data(self, result) -> Dict[str, Any]:
        """Extract data from invoice analysis result"""
        extracted_data = {
            'document_type': 'INVOICE',
            'confidence': 0.0,
            'vendor_info': {},
            'customer_info': {},
            'invoice_info': {},
            'line_items': [],
            'amounts': {},
            'dates': {},
            'raw_text': '',
            'tables': []
        }

        # Extract text content
        if hasattr(result, 'content'):
            extracted_data['raw_text'] = result.content

        # Process documents
        for document in result.documents:
            doc_type = document.doc_type
            confidence = document.confidence
            extracted_data['confidence'] = confidence

            # Extract fields
            fields = document.fields

            # Vendor information
            if 'VendorName' in fields:
                extracted_data['vendor_info']['name'] = self._get_field_value(fields['VendorName'])
            if 'VendorAddress' in fields:
                extracted_data['vendor_info']['address'] = self._get_field_value(fields['VendorAddress'])
            if 'VendorAddressRecipient' in fields:
                extracted_data['vendor_info']['recipient'] = self._get_field_value(fields['VendorAddressRecipient'])

            # Customer information
            if 'CustomerName' in fields:
                extracted_data['customer_info']['name'] = self._get_field_value(fields['CustomerName'])
            if 'CustomerAddress' in fields:
                extracted_data['customer_info']['address'] = self._get_field_value(fields['CustomerAddress'])
            if 'CustomerAddressRecipient' in fields:
                extracted_data['customer_info']['recipient'] = self._get_field_value(fields['CustomerAddressRecipient'])

            # Invoice information
            if 'InvoiceId' in fields:
                extracted_data['invoice_info']['invoice_id'] = self._get_field_value(fields['InvoiceId'])
            if 'PurchaseOrder' in fields:
                extracted_data['invoice_info']['purchase_order'] = self._get_field_value(fields['PurchaseOrder'])

            # Dates
            if 'InvoiceDate' in fields:
                extracted_data['dates']['invoice_date'] = self._get_field_date(fields['InvoiceDate'])
            if 'DueDate' in fields:
                extracted_data['dates']['due_date'] = self._get_field_date(fields['DueDate'])

            # Amounts
            if 'SubTotal' in fields:
                extracted_data['amounts']['subtotal'] = self._get_field_amount(fields['SubTotal'])
            if 'TotalTax' in fields:
                extracted_data['amounts']['tax'] = self._get_field_amount(fields['TotalTax'])
            if 'InvoiceTotal' in fields:
                extracted_data['amounts']['total'] = self._get_field_amount(fields['InvoiceTotal'])
            if 'AmountDue' in fields:
                extracted_data['amounts']['amount_due'] = self._get_field_amount(fields['AmountDue'])

            # Line items
            if 'Items' in fields:
                items_field = fields['Items']
                if items_field.value_type == 'list':
                    for item in items_field.value:
                        line_item = self._extract_line_item(item.value)
                        if line_item:
                            extracted_data['line_items'].append(line_item)

        # Extract tables
        for table_idx, table in enumerate(result.tables):
            table_data = self._extract_table_data(table)
            if table_data:
                extracted_data['tables'].append(table_data)

        return extracted_data

    def _extract_line_item(self, item_fields) -> Optional[Dict[str, Any]]:
        """Extract line item information"""
        line_item = {}

        if 'Description' in item_fields:
            line_item['description'] = self._get_field_value(item_fields['Description'])
        if 'Quantity' in item_fields:
            line_item['quantity'] = self._get_field_value(item_fields['Quantity'])
        if 'Unit' in item_fields:
            line_item['unit'] = self._get_field_value(item_fields['Unit'])
        if 'UnitPrice' in item_fields:
            line_item['unit_price'] = self._get_field_amount(item_fields['UnitPrice'])
        if 'ProductCode' in item_fields:
            line_item['product_code'] = self._get_field_value(item_fields['ProductCode'])
        if 'Amount' in item_fields:
            line_item['amount'] = self._get_field_amount(item_fields['Amount'])

        return line_item if line_item else None

    def _extract_general_document_data(self, result) -> Dict[str, Any]:
        """Extract data from general document analysis"""
        extracted_data = {
            'document_type': 'GENERAL',
            'confidence': 0.0,
            'key_value_pairs': {},
            'raw_text': '',
            'tables': [],
            'entities': []
        }

        # Extract content
        if hasattr(result, 'content'):
            extracted_data['raw_text'] = result.content

        # Extract key-value pairs
        for kv_pair in result.key_value_pairs:
            if kv_pair.key and kv_pair.value:
                key = kv_pair.key.content
                value = kv_pair.value.content
                confidence = kv_pair.confidence
                extracted_data['key_value_pairs'][key] = {
                    'value': value,
                    'confidence': confidence
                }

        # Extract tables
        for table_idx, table in enumerate(result.tables):
            table_data = self._extract_table_data(table)
            if table_data:
                extracted_data['tables'].append(table_data)

        # Extract entities if available
        if hasattr(result, 'entities'):
            for entity in result.entities:
                extracted_data['entities'].append({
                    'category': entity.category,
                    'subcategory': entity.subcategory if hasattr(entity, 'subcategory') else None,
                    'content': entity.content,
                    'confidence': entity.confidence
                })

        return extracted_data

    def _extract_table_data(self, table) -> Dict[str, Any]:
        """Extract table data"""
        table_data = {
            'row_count': table.row_count,
            'column_count': table.column_count,
            'cells': []
        }

        for cell in table.cells:
            cell_data = {
                'row_index': cell.row_index,
                'column_index': cell.column_index,
                'content': cell.content,
                'row_span': cell.row_span if hasattr(cell, 'row_span') else 1,
                'column_span': cell.column_span if hasattr(cell, 'column_span') else 1,
                'is_header': cell.kind == 'columnHeader' if hasattr(cell, 'kind') else False
            }
            table_data['cells'].append(cell_data)

        return table_data

    def _get_field_value(self, field) -> Optional[str]:
        """Extract string value from field"""
        if field and hasattr(field, 'value'):
            return str(field.value) if field.value else None
        return None

    def _get_field_date(self, field) -> Optional[str]:
        """Extract date value from field"""
        if field and hasattr(field, 'value') and field.value:
            if isinstance(field.value, datetime):
                return field.value.isoformat()
            return str(field.value)
        return None

    def _get_field_amount(self, field) -> Optional[float]:
        """Extract amount value from field"""
        if field and hasattr(field, 'value') and field.value:
            try:
                return float(field.value)
            except (ValueError, TypeError):
                return None
        return None

    def extract_german_tax_info(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract German-specific tax information from document
        """
        tax_info = {
            'vat_id': None,
            'tax_number': None,
            'reverse_charge': False,
            'tax_rate': None,
            'tax_amount': None
        }

        # Look for VAT ID (USt-IdNr.)
        raw_text = extracted_data.get('raw_text', '')

        # VAT ID patterns
        import re
        vat_patterns = [
            r'USt[\.\-]?IdNr[\.\:]?\s*([A-Z]{2}\d+)',
            r'USt[\.\-]?ID[\.\:]?\s*([A-Z]{2}\d+)',
            r'UID[\.\:]?\s*([A-Z]{2}\d+)',
            r'VAT[\s\-]?ID[\.\:]?\s*([A-Z]{2}\d+)'
        ]

        for pattern in vat_patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                tax_info['vat_id'] = match.group(1)
                break

        # Tax number patterns
        tax_num_patterns = [
            r'Steuernummer[\.\:]?\s*(\d+[/\-]?\d+)',
            r'Steuer[\.\-]?Nr[\.\:]?\s*(\d+[/\-]?\d+)',
            r'Tax[\s\-]?Number[\.\:]?\s*(\d+[/\-]?\d+)'
        ]

        for pattern in tax_num_patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                tax_info['tax_number'] = match.group(1)
                break

        # Check for reverse charge
        reverse_charge_patterns = [
            r'Reverse[\s\-]?Charge',
            r'Steuerschuldnerschaft\s+des\s+Leistungsempf[äa]ngers',
            r'§\s*13b\s*UStG'
        ]

        for pattern in reverse_charge_patterns:
            if re.search(pattern, raw_text, re.IGNORECASE):
                tax_info['reverse_charge'] = True
                break

        # Extract tax rate
        if 'amounts' in extracted_data and 'tax' in extracted_data['amounts']:
            tax_amount = extracted_data['amounts']['tax']
            subtotal = extracted_data['amounts'].get('subtotal', 0)

            if tax_amount and subtotal:
                tax_rate = (tax_amount / subtotal) * 100
                # Round to standard German tax rates
                if 18 < tax_rate < 20:
                    tax_info['tax_rate'] = 19.0
                elif 6 < tax_rate < 8:
                    tax_info['tax_rate'] = 7.0
                else:
                    tax_info['tax_rate'] = round(tax_rate, 2)

                tax_info['tax_amount'] = tax_amount

        return tax_info
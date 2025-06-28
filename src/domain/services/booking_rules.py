# src/domain/services/booking_rules.py
"""
Business rules for bookings and accounting
"""

from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime


class BookingRules:
    """
    Encapsulates German accounting rules and SKR04 logic
    """

    def __init__(self):
        """Initialize booking rules with SKR04 definitions"""
        self.tax_rates = {
            'standard': Decimal('19'),
            'reduced': Decimal('7'),
            'zero': Decimal('0')
        }

        # Tax accounts in SKR04
        self.tax_accounts = {
            'input_tax_19': '1576',  # Abziehbare Vorsteuer 19%
            'input_tax_7': '1571',  # Abziehbare Vorsteuer 7%
            'output_tax_19': '1776',  # Umsatzsteuer 19%
            'output_tax_7': '1771',  # Umsatzsteuer 7%
            'tax_payable': '1790',  # Umsatzsteuer
            'tax_prepayment': '1780'  # Umsatzsteuer-Vorauszahlungen
        }

        # Common expense categories with typical accounts
        self.expense_categories = {
            'office_supplies': {
                'accounts': ['4930'],  # Bürobedarf
                'keywords': ['büro', 'office', 'papier', 'stift', 'toner', 'druckerpapier']
            },
            'software': {
                'accounts': ['6835'],  # EDV-Software/Wartung
                'keywords': ['software', 'lizenz', 'saas', 'cloud', 'adobe', 'microsoft', 'slack']
            },
            'internet': {
                'accounts': ['6815'],  # Internetkosten
                'keywords': ['internet', 'dsl', 'hosting', 'domain', 'server', 'aws', 'cloud']
            },
            'phone': {
                'accounts': ['6805'],  # Telefon
                'keywords': ['telefon', 'mobilfunk', 'handy', 'mobile', 'vodafone', 'telekom']
            },
            'rent': {
                'accounts': ['4200'],  # Raumkosten
                'keywords': ['miete', 'rent', 'büro', 'nebenkosten', 'heizung']
            },
            'travel': {
                'accounts': ['6673'],  # Reisekosten Unternehmer
                'keywords': ['reise', 'hotel', 'bahn', 'flug', 'taxi', 'mietwagen']
            },
            'marketing': {
                'accounts': ['6600'],  # Werbung
                'keywords': ['werbung', 'marketing', 'anzeige', 'facebook', 'google ads']
            },
            'professional_services': {
                'accounts': ['6815'],  # Rechts- und Beratungskosten
                'keywords': ['beratung', 'rechtsanwalt', 'steuerberater', 'notar', 'consulting']
            }
        }

    def validate_booking(self, entries: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        Validate a booking according to accounting rules

        Args:
            entries: List of booking entries with debit/credit amounts

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Check if entries exist
        if not entries:
            errors.append("Keine Buchungszeilen vorhanden")
            return False, errors

        # Calculate totals
        total_debit = Decimal('0')
        total_credit = Decimal('0')

        for entry in entries:
            # Validate required fields
            if 'account' not in entry:
                errors.append("Konto fehlt in Buchungszeile")
                continue

            # Validate amounts
            debit = entry.get('debit')
            credit = entry.get('credit')

            if debit is not None and credit is not None:
                errors.append(f"Konto {entry['account']}: Soll und Haben können nicht beide belegt sein")
            elif debit is None and credit is None:
                errors.append(f"Konto {entry['account']}: Entweder Soll oder Haben muss belegt sein")
            else:
                if debit is not None:
                    try:
                        total_debit += Decimal(str(debit))
                    except:
                        errors.append(f"Ungültiger Soll-Betrag: {debit}")

                if credit is not None:
                    try:
                        total_credit += Decimal(str(credit))
                    except:
                        errors.append(f"Ungültiger Haben-Betrag: {credit}")

        # Check if balanced
        if abs(total_debit - total_credit) > Decimal('0.01'):
            errors.append(f"Buchung nicht ausgeglichen: Soll {total_debit} != Haben {total_credit}")

        return len(errors) == 0, errors

    def suggest_expense_account(self, description: str, vendor: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Suggest expense accounts based on description and vendor

        Returns:
            List of account suggestions with confidence scores
        """
        suggestions = []

        # Normalize text for matching
        search_text = f"{description} {vendor or ''}".lower()

        # Check each category
        for category, config in self.expense_categories.items():
            score = 0.0
            matched_keywords = []

            # Check keywords
            for keyword in config['keywords']:
                if keyword in search_text:
                    score += 0.3
                    matched_keywords.append(keyword)

            if score > 0:
                for account in config['accounts']:
                    suggestions.append({
                        'account': account,
                        'category': category,
                        'confidence': min(score, 1.0),
                        'matched_keywords': matched_keywords
                    })

        # Sort by confidence
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)

        # Add generic fallback if no matches
        if not suggestions:
            suggestions.append({
                'account': '6840',  # Sonstige betriebliche Aufwendungen
                'category': 'other',
                'confidence': 0.3,
                'matched_keywords': []
            })

        return suggestions[:5]  # Return top 5

    def calculate_tax_split(
            self,
            gross_amount: Decimal,
            tax_rate: Optional[Decimal] = None
    ) -> Dict[str, Decimal]:
        """
        Calculate net amount and tax from gross amount

        Args:
            gross_amount: Total amount including tax
            tax_rate: Tax rate (if None, tries to detect from amount)

        Returns:
            Dict with net_amount and tax_amount
        """
        if tax_rate is None:
            # Try to detect standard rates
            # This is a simplified approach
            for rate in [self.tax_rates['standard'], self.tax_rates['reduced']]:
                net_test = gross_amount / (1 + rate / 100)
                tax_test = gross_amount - net_test

                # Check if tax amount seems reasonable
                if abs(tax_test - net_test * rate / 100) < Decimal('0.01'):
                    tax_rate = rate
                    break

        if tax_rate is None:
            # Default to standard rate
            tax_rate = self.tax_rates['standard']

        # Calculate split
        net_amount = gross_amount / (1 + tax_rate / 100)
        tax_amount = gross_amount - net_amount

        # Round to 2 decimal places
        net_amount = net_amount.quantize(Decimal('0.01'))
        tax_amount = tax_amount.quantize(Decimal('0.01'))

        return {
            'net_amount': net_amount,
            'tax_amount': tax_amount,
            'tax_rate': tax_rate,
            'gross_amount': gross_amount
        }

    def get_tax_account(
            self,
            is_revenue: bool,
            tax_rate: Decimal
    ) -> Optional[str]:
        """
        Get the appropriate tax account

        Args:
            is_revenue: True for revenue, False for expense
            tax_rate: Tax rate

        Returns:
            Account number or None
        """
        if is_revenue:
            if tax_rate == self.tax_rates['standard']:
                return self.tax_accounts['output_tax_19']
            elif tax_rate == self.tax_rates['reduced']:
                return self.tax_accounts['output_tax_7']
        else:
            if tax_rate == self.tax_rates['standard']:
                return self.tax_accounts['input_tax_19']
            elif tax_rate == self.tax_rates['reduced']:
                return self.tax_accounts['input_tax_7']

        return None

    def validate_tax_id(self, tax_id: str) -> Tuple[bool, Optional[str]]:
        """
        Validate German tax ID (USt-IdNr.)

        Args:
            tax_id: Tax ID to validate

        Returns:
            Tuple of (is_valid, normalized_id)
        """
        import re

        if not tax_id:
            return False, None

        # Remove spaces and uppercase
        tax_id = tax_id.replace(' ', '').replace('-', '').upper()

        # German VAT ID pattern: DE followed by 9 digits
        if re.match(r'^DE\d{9}$', tax_id):
            return True, tax_id

        return False, None

    def is_reverse_charge(self, document_data: Dict[str, Any]) -> bool:
        """
        Check if reverse charge procedure applies

        Args:
            document_data: Document information

        Returns:
            True if reverse charge applies
        """
        # Check explicit reverse charge indicator
        if document_data.get('tax_info', {}).get('reverse_charge'):
            return True

        # Check for EU VAT ID (not German)
        vendor_vat = document_data.get('vendor_info', {}).get('vat_id', '')
        if vendor_vat and not vendor_vat.startswith('DE'):
            # EU reverse charge for B2B
            return True

        # Check for specific text indicators
        raw_text = document_data.get('raw_text', '').lower()
        reverse_charge_indicators = [
            'reverse charge',
            'steuerschuldnerschaft',
            '§13b',
            '§ 13b',
            'tax liability'
        ]

        for indicator in reverse_charge_indicators:
            if indicator in raw_text:
                return True

        return False

    def get_payment_provider_account(self, provider: str) -> Optional[str]:
        """
        Get the appropriate account for payment provider transactions

        Args:
            provider: Payment provider name (PAYPAL, STRIPE, etc.)

        Returns:
            Account number or None
        """
        provider_accounts = {
            'PAYPAL': '1361',  # Guthaben bei Kreditinstituten (PayPal)
            'STRIPE': '1362',  # Guthaben bei Kreditinstituten (Stripe)
            'MOLLIE': '1363',  # Guthaben bei Kreditinstituten (Mollie)
            'BANK': '1200'  # Bank
        }

        return provider_accounts.get(provider.upper())

    def split_payment_fees(
            self,
            gross_amount: Decimal,
            fee_amount: Decimal
    ) -> List[Dict[str, Any]]:
        """
        Split payment provider transaction into revenue and fees

        Args:
            gross_amount: Total amount before fees
            fee_amount: Fee amount

        Returns:
            List of booking entries
        """
        net_amount = gross_amount - fee_amount

        entries = [
            {
                'description': 'Zahlung nach Gebühren',
                'amount': net_amount,
                'is_fee': False
            },
            {
                'description': 'Transaktionsgebühren',
                'amount': fee_amount,
                'is_fee': True,
                'expense_account': '6855'  # Nebenkosten des Geldverkehrs
            }
        ]

        return entries
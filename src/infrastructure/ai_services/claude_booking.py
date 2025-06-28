# src/infrastructure/ai_services/claude_booking.py
"""
Claude API integration for intelligent booking suggestions
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime

# Anthropic SDK
try:
    from anthropic import Anthropic

    ANTHROPIC_SDK_AVAILABLE = True
except ImportError:
    ANTHROPIC_SDK_AVAILABLE = False
    print("WARNING: Anthropic SDK not installed. Install with: pip install anthropic")

from src.core.config import settings
from src.domain.services.booking_rules import BookingRules

logger = logging.getLogger(__name__)


class ClaudeBookingService:
    """
    Use Claude AI to suggest bookings based on document content and business rules
    """

    def __init__(self):
        if not ANTHROPIC_SDK_AVAILABLE:
            raise ImportError("Anthropic SDK not available. Install anthropic")

        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")

        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens
        self.booking_rules = BookingRules()

        # SKR04 account mapping for common scenarios
        self.skr04_accounts = self._load_skr04_accounts()

    def _load_skr04_accounts(self) -> Dict[str, Dict[str, Any]]:
        """Load SKR04 account definitions"""
        return {
            # Assets
            "1200": {"name": "Bank", "type": "asset"},
            "1361": {"name": "Guthaben bei Kreditinstituten (PayPal)", "type": "asset"},
            "1362": {"name": "Guthaben bei Kreditinstituten (Stripe)", "type": "asset"},
            "1400": {"name": "Forderungen aus Lieferungen und Leistungen", "type": "asset"},
            "1576": {"name": "Abziehbare Vorsteuer 19%", "type": "asset"},
            "1571": {"name": "Abziehbare Vorsteuer 7%", "type": "asset"},

            # Liabilities
            "1600": {"name": "Verbindlichkeiten aus Lieferungen und Leistungen", "type": "liability"},
            "3736": {"name": "Erhaltene Anzahlungen 19% USt", "type": "liability"},

            # Expenses - Office
            "4200": {"name": "Raumkosten", "type": "expense"},
            "4930": {"name": "Bürobedarf", "type": "expense"},
            "4940": {"name": "Zeitschriften, Bücher", "type": "expense"},

            # Expenses - IT/Communication
            "6805": {"name": "Telefon", "type": "expense"},
            "6815": {"name": "Internetkosten", "type": "expense"},
            "6835": {"name": "EDV-Software/Wartung", "type": "expense"},
            "6840": {"name": "Sonstige EDV-Kosten", "type": "expense"},

            # Expenses - Travel
            "6640": {"name": "Bewirtungskosten abziehbar", "type": "expense"},
            "6660": {"name": "Reisekosten Arbeitnehmer", "type": "expense"},
            "6673": {"name": "Reisekosten Unternehmer", "type": "expense"},

            # Expenses - Marketing
            "6600": {"name": "Werbung", "type": "expense"},

            # Expenses - Professional services
            "6815": {"name": "Rechts- und Beratungskosten", "type": "expense"},
            "6825": {"name": "Buchführungskosten", "type": "expense"},

            # Revenue
            "8400": {"name": "Erlöse 19% USt", "type": "revenue"},
            "8300": {"name": "Erlöse 7% USt", "type": "revenue"},
            "8120": {"name": "Steuerfreie Umsätze", "type": "revenue"},

            # Special accounts
            "1790": {"name": "Umsatzsteuer", "type": "liability"},
            "1780": {"name": "Umsatzsteuer-Vorauszahlungen", "type": "asset"}
        }

    async def suggest_booking(
            self,
            document_data: Dict[str, Any],
            transaction_data: Optional[Dict[str, Any]] = None,
            additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Suggest booking entries based on document and transaction data

        Args:
            document_data: Extracted document information from Azure
            transaction_data: Related bank transaction if available
            additional_context: Additional context from user

        Returns:
            Booking suggestion with confidence scores
        """
        try:
            # Prepare the prompt
            prompt = self._create_booking_prompt(document_data, transaction_data, additional_context)

            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.1,  # Low temperature for consistent results
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Parse the response
            suggestion = self._parse_claude_response(response.content[0].text)

            # Validate against business rules
            validated_suggestion = self._validate_suggestion(suggestion, document_data)

            # Add metadata
            validated_suggestion['metadata'] = {
                'model': self.model,
                'confidence': suggestion.get('confidence', 0.0),
                'timestamp': datetime.utcnow().isoformat(),
                'document_type': document_data.get('document_type', 'UNKNOWN')
            }

            return validated_suggestion

        except Exception as e:
            logger.error(f"Error getting booking suggestion from Claude: {e}")
            return self._create_fallback_suggestion(document_data, transaction_data)

    def _create_booking_prompt(
            self,
            document_data: Dict[str, Any],
            transaction_data: Optional[Dict[str, Any]],
            additional_context: Optional[str]
    ) -> str:
        """Create prompt for Claude"""

        # Extract key information
        doc_type = document_data.get('document_type', 'UNKNOWN')
        vendor_name = document_data.get('vendor_info', {}).get('name', 'Unknown')
        total_amount = document_data.get('amounts', {}).get('total', 0)
        tax_amount = document_data.get('amounts', {}).get('tax', 0)
        invoice_date = document_data.get('dates', {}).get('invoice_date', '')
        invoice_id = document_data.get('invoice_info', {}).get('invoice_id', '')

        # Extract line items
        line_items = document_data.get('line_items', [])
        line_items_text = "\n".join([
            f"- {item.get('description', 'N/A')}: {item.get('amount', 0)}"
            for item in line_items[:5]  # Limit to first 5 items
        ])

        # Build the prompt
        prompt = f"""You are an expert German accountant specializing in SKR04 (Standardkontenrahmen 04).

Analyze the following invoice and suggest the appropriate double-entry bookkeeping entries.

INVOICE INFORMATION:
- Type: {doc_type}
- Vendor: {vendor_name}
- Invoice Number: {invoice_id}
- Date: {invoice_date}
- Total Amount: {total_amount} EUR
- Tax Amount: {tax_amount} EUR
- Net Amount: {total_amount - tax_amount} EUR

LINE ITEMS:
{line_items_text if line_items_text else "No line items available"}

"""

        if transaction_data:
            prompt += f"""
BANK TRANSACTION:
- Date: {transaction_data.get('booking_date', '')}
- Amount: {transaction_data.get('amount', 0)} EUR
- Description: {transaction_data.get('description', '')}
- Account: {transaction_data.get('account_number', '')}
"""

        if additional_context:
            prompt += f"""
ADDITIONAL CONTEXT:
{additional_context}
"""

        prompt += """
Please provide a booking suggestion in the following JSON format:
{
    "booking_text": "Brief description for the booking",
    "entries": [
        {
            "account": "account number",
            "account_name": "account name",
            "debit": amount or null,
            "credit": amount or null,
            "tax_key": "tax key if applicable"
        }
    ],
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of the booking logic",
    "alternative_accounts": ["list of alternative account numbers if unsure"]
}

IMPORTANT RULES:
1. Use SKR04 accounts only
2. Debit and credit must balance
3. Consider German VAT (19% or 7%)
4. Use account 1576 for deductible input tax (Vorsteuer) 19%
5. Use account 1571 for deductible input tax (Vorsteuer) 7%
6. Expense accounts are typically in the 4xxx-6xxx range
7. For vendor invoices: Credit 1600 (Verbindlichkeiten), Debit expense account + VAT account

Analyze the invoice and provide the booking suggestion:"""

        return prompt

    def _parse_claude_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Claude's response"""
        try:
            # Try to extract JSON from the response
            import re

            # Find JSON block in response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
            else:
                # Fallback: try to parse the entire response as JSON
                return json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.debug(f"Response text: {response_text}")

            # Return a basic structure
            return {
                "booking_text": "Failed to parse AI response",
                "entries": [],
                "confidence": 0.0,
                "reasoning": "Could not parse AI response",
                "parse_error": str(e)
            }

    def _validate_suggestion(self, suggestion: Dict[str, Any], document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and potentially correct the suggestion"""

        # Ensure required fields exist
        if 'entries' not in suggestion:
            suggestion['entries'] = []

        if 'confidence' not in suggestion:
            suggestion['confidence'] = 0.5

        # Validate entries
        total_debit = Decimal('0')
        total_credit = Decimal('0')

        for entry in suggestion.get('entries', []):
            # Ensure account exists in SKR04
            account = entry.get('account', '')
            if account not in self.skr04_accounts:
                # Try to find a similar account
                entry['account_valid'] = False
                entry['suggested_account'] = self._find_similar_account(account)
            else:
                entry['account_valid'] = True
                entry['account_name'] = self.skr04_accounts[account]['name']

            # Sum up debits and credits
            if entry.get('debit'):
                total_debit += Decimal(str(entry['debit']))
            if entry.get('credit'):
                total_credit += Decimal(str(entry['credit']))

        # Check if booking is balanced
        suggestion['is_balanced'] = abs(total_debit - total_credit) < Decimal('0.01')

        if not suggestion['is_balanced']:
            suggestion['validation_errors'] = [
                f"Booking is not balanced. Debit: {total_debit}, Credit: {total_credit}"
            ]
            suggestion['confidence'] *= 0.5  # Reduce confidence

        return suggestion

    def _find_similar_account(self, account: str) -> Optional[str]:
        """Find a similar account number in SKR04"""
        # Simple similarity check - could be enhanced
        if account.isdigit():
            # Try to find account with same first 2 digits
            prefix = account[:2]
            for skr_account in self.skr04_accounts:
                if skr_account.startswith(prefix):
                    return skr_account
        return None

    def _create_fallback_suggestion(
            self,
            document_data: Dict[str, Any],
            transaction_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create a fallback suggestion when AI fails"""

        total_amount = document_data.get('amounts', {}).get('total', 0)
        tax_amount = document_data.get('amounts', {}).get('tax', 0)
        net_amount = total_amount - tax_amount if total_amount and tax_amount else total_amount

        # Determine tax rate
        tax_rate = 19  # Default
        if net_amount > 0 and tax_amount > 0:
            calculated_rate = (tax_amount / net_amount) * 100
            if 6 < calculated_rate < 8:
                tax_rate = 7

        # Create basic suggestion
        suggestion = {
            "booking_text": "Verbindlichkeit aus Rechnung",
            "entries": [],
            "confidence": 0.3,
            "reasoning": "Fallback suggestion - AI service unavailable",
            "is_fallback": True
        }

        # Add entries based on document type
        if document_data.get('document_type') == 'INVOICE' and total_amount > 0:
            # Credit: Vendor liability
            suggestion['entries'].append({
                "account": "1600",
                "account_name": "Verbindlichkeiten aus Lieferungen und Leistungen",
                "debit": None,
                "credit": float(total_amount),
                "account_valid": True
            })

            # Debit: Generic expense
            if net_amount > 0:
                suggestion['entries'].append({
                    "account": "6840",
                    "account_name": "Sonstige betriebliche Aufwendungen",
                    "debit": float(net_amount),
                    "credit": None,
                    "account_valid": True
                })

            # Debit: VAT
            if tax_amount > 0:
                vat_account = "1576" if tax_rate == 19 else "1571"
                vat_name = f"Abziehbare Vorsteuer {tax_rate}%"

                suggestion['entries'].append({
                    "account": vat_account,
                    "account_name": vat_name,
                    "debit": float(tax_amount),
                    "credit": None,
                    "account_valid": True
                })

        suggestion['is_balanced'] = True
        return suggestion

    async def enhance_with_context(
            self,
            suggestion: Dict[str, Any],
            historical_bookings: List[Dict[str, Any]],
            vendor_history: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enhance booking suggestion with historical context
        """
        if not historical_bookings and not vendor_history:
            return suggestion

        # Build context prompt
        context_prompt = f"""Based on the following historical data, please verify or improve the booking suggestion:

CURRENT SUGGESTION:
{json.dumps(suggestion, indent=2)}

"""

        if vendor_history:
            context_prompt += f"""
VENDOR HISTORY:
- Previous bookings for {vendor_history.get('vendor_name', 'this vendor')}:
- Typical expense account: {vendor_history.get('common_account', 'N/A')}
- Average amount: {vendor_history.get('avg_amount', 0)} EUR
"""

        if historical_bookings:
            context_prompt += """
SIMILAR HISTORICAL BOOKINGS:
"""
            for booking in historical_bookings[:3]:  # Limit to 3 examples
                context_prompt += f"- {booking.get('description', '')}: {booking.get('debit_account', '')} -> {booking.get('credit_account', '')}\n"

        context_prompt += """
Please provide an updated suggestion if the historical data suggests a different booking approach.
Return the response in the same JSON format as before."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": context_prompt
                    }
                ]
            )

            enhanced_suggestion = self._parse_claude_response(response.content[0].text)
            enhanced_suggestion['enhanced_with_context'] = True

            return self._validate_suggestion(enhanced_suggestion, {})

        except Exception as e:
            logger.error(f"Error enhancing suggestion with context: {e}")
            suggestion['enhancement_error'] = str(e)
            return suggestion
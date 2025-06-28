# src/infrastructure/importers/factory.py

from typing import Optional
from .base import BaseImporter
from .bank_csv import BankCSVImporter
from .datev import DATEVImporter
from .pdf import PDFImporter
from .paypal import PayPalImporter
from .stripe import StripeImporter
from .mollie import MollieImporter


class ImporterFactory:
    """
    Factory to create appropriate importer based on file type
    """

    def __init__(self):
        # Order matters - more specific importers first
        self._importers = [
            BankCSVImporter(),      # Bank CSV should be checked before generic CSV
            PayPalImporter(),       # PayPal CSV
            StripeImporter(),       # Stripe CSV
            MollieImporter(),       # Mollie CSV
            PDFImporter(),          # PDF and image files
            DATEVImporter()         # DATEV handles remaining CSV files
        ]

    def get_importer(self, filename: str) -> Optional[BaseImporter]:
        """
        Get appropriate importer for the given filename

        Returns None if no importer can handle the file
        """
        for importer in self._importers:
            if importer.can_handle(filename):
                return importer

        return None

    def get_supported_extensions(self) -> list[str]:
        """
        Get list of supported file extensions
        """
        return ['.csv', '.pdf', '.jpg', '.jpeg', '.png']
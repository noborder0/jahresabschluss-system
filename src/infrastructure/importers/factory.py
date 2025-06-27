# src/infrastructure/importers/factory.py

from typing import Optional
from .base import BaseImporter
from .bank_xml import BankXMLImporter
from .datev import DATEVImporter
from .pdf import PDFImporter


class ImporterFactory:
    """
    Factory to create appropriate importer based on file type
    """

    def __init__(self):
        self._importers = [
            BankXMLImporter(),
            DATEVImporter(),
            PDFImporter()
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
        return ['.xml', '.csv', '.pdf']
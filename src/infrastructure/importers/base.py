# src/infrastructure/importers/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from sqlalchemy.orm import Session


class BaseImporter(ABC):
    """
    Abstract base class for all file importers
    """

    @abstractmethod
    async def import_file(self, file_path: str, db: Session) -> Dict[str, Any]:
        """
        Import a file and return import results

        Returns:
            Dict with keys:
            - import_id: Unique identifier for this import batch
            - transaction_count: Number of transactions imported
            - source_type: Type of import (BANK_XML, DATEV, PDF)
            - transactions: List of imported transaction data
        """
        pass

    @abstractmethod
    def can_handle(self, filename: str) -> bool:
        """
        Check if this importer can handle the given filename
        """
        pass

    def _generate_import_id(self) -> str:
        """
        Generate a unique import ID
        """
        import uuid
        return str(uuid.uuid4())
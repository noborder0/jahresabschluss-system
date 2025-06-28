# src/infrastructure/importers/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session


class BaseImporter(ABC):
    """
    Abstract base class for all file importers
    """

    @abstractmethod
    async def import_file(self, file_path: str, db: Session, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Import a file and return import results

        Args:
            file_path: Path to the file to import
            db: Database session
            metadata: Optional metadata (e.g., account information for bank imports)

        Returns:
            Dict with keys:
            - import_id: Unique identifier for this import batch
            - transaction_count: Number of transactions imported
            - source_type: Type of import (BANK_CSV, DATEV, PDF)
            - transactions: List of imported transaction data
            - bank_info: Additional metadata (for bank imports)
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
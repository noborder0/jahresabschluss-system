# src/infrastructure/ai_services/__init__.py
"""
AI services integration for Phase 2
"""

import logging

logger = logging.getLogger(__name__)

# Try to import AI services
try:
    from .azure_document import AzureDocumentProcessor
    from .claude_booking import ClaudeBookingService
    from .document_processor import DocumentProcessor

    __all__ = [
        'AzureDocumentProcessor',
        'ClaudeBookingService',
        'DocumentProcessor'
    ]

    logger.info("AI services modules loaded successfully")

except ImportError as e:
    logger.warning(f"Some AI services could not be loaded: {e}")
    logger.warning("The system will continue without AI features")


    # Export empty classes as fallback
    class AzureDocumentProcessor:
        def __init__(self):
            raise NotImplementedError("Azure Document Intelligence not available. Install azure-ai-formrecognizer")


    class ClaudeBookingService:
        def __init__(self):
            raise NotImplementedError("Claude API not available. Install anthropic")


    class DocumentProcessor:
        def __init__(self):
            logger.warning("AI services not available - document processor disabled")


    __all__ = [
        'AzureDocumentProcessor',
        'ClaudeBookingService',
        'DocumentProcessor'
    ]
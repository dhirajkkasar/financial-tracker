"""
ImportPipeline — parse → validate → deduplicate.

Stateless: creates a fresh run each call. Receives dependencies via constructor.
"""
from __future__ import annotations

from app.importers.base import ImportResult
from app.importers.registry import ImporterRegistry
from app.services.imports.deduplicator import IDeduplicator
from app.middleware.error_handler import ValidationError


class ImportPipeline:
    """
    Runs the three-step import pipeline for a single file.

    Steps:
        1. parse    — delegate to the registered importer for (source, format)
        2. validate — call importer.validate(result); raise ValidationError if invalid
        3. deduplicate — filter out txn_ids already in the database
    
    Accepts importer_kwargs (e.g., user_inputs, exchange_rates) passed to importer.__init__
    """

    def __init__(self, registry: ImporterRegistry, deduplicator: IDeduplicator):
        self._registry = registry
        self._deduplicator = deduplicator

    def run(self, source: str, fmt: str, file_bytes: bytes, **importer_kwargs) -> ImportResult:
        """Run the full import pipeline: parse → validate → deduplicate.
        
        Args:
            source: Importer source identifier (e.g., "fidelity_rsu", "fidelity_sale")
            fmt: File format (e.g., "csv", "pdf")
            file_bytes: Raw file bytes to parse
            **importer_kwargs: Additional arguments passed to importer.__init__ 
                             (e.g., user_inputs for exchange_rates)
        
        Returns:
            ImportResult with deduplicated transactions
            
        Raises:
            ValidationError: If importer.validate() fails
        """
        print("kwargs received by ImportPipeline.run:", importer_kwargs)
        importer = self._registry.get(source, fmt, **importer_kwargs)
        print(f"Using importer: {importer.__class__.__name__} for source={source} format={fmt}")
        result = importer.parse(file_bytes)
        print("calling validate")
        validation_result = importer.validate(result)
        if not validation_result.is_valid:
            # Raise ValidationError with first error message and structured details
            error_msg = validation_result.errors[0] if validation_result.errors else "Validation failed"
            raise ValidationError(error_msg)
        
        result = self._deduplicator.filter_duplicates(result)
        return result

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
        2. validate — call importer.validate(); raise ValidationError if invalid
        3. deduplicate — filter out txn_ids already in the database
    """

    def __init__(self, registry: ImporterRegistry, deduplicator: IDeduplicator):
        self._registry = registry
        self._deduplicator = deduplicator

    def run(self, source: str, fmt: str, file_bytes: bytes, **importer_kwargs) -> ImportResult:
        print("kwargs received by ImportPipeline.run:", importer_kwargs)
        # Extract filename if provided, otherwise use empty string
        filename = importer_kwargs.pop("filename", "")
        
        # Extract user_inputs (for validate) from constructor kwargs (for registry.get)
        # user_inputs are not passed to importer constructor, only to validate()
        user_inputs = importer_kwargs.pop("user_inputs", None)
        print("user_inputs extracted:", user_inputs)
        # Create importer without user_inputs
        importer = self._registry.get(source, fmt, **importer_kwargs)
        result = importer.parse(file_bytes, filename=filename)
        
        # Call validate with user_inputs and other kwargs
        validate_kwargs = importer_kwargs.copy()
        if user_inputs:
            validate_kwargs["user_inputs"] = user_inputs
        
        print("kwargs passed to importer.validate:", validate_kwargs)
        validation_result = importer.validate(result, **validate_kwargs)
        if not validation_result.is_valid:
            # Raise ValidationError with first error message and structured details
            error_msg = validation_result.errors[0] if validation_result.errors else "Validation failed"
            raise ValidationError(error_msg)
        
        result = self._deduplicator.filter_duplicates(result)
        return result

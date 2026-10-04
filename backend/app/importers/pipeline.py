"""
ImportPipeline — parse → validate → deduplicate.

Stateless: creates a fresh run each call. Receives dependencies via constructor.
"""
from __future__ import annotations

import logging

from app.importers.base import ImportResult
from app.importers.registry import ImporterRegistry
from app.services.imports.deduplicator import IDeduplicator
from app.middleware.error_handler import ValidationError

logger = logging.getLogger(__name__)


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
            source: Importer source identifier (e.g., "fidelity_open", "fidelity_closed")
            fmt: File format (e.g., "csv", "pdf")
            file_bytes: Raw file bytes to parse
            **importer_kwargs: Additional arguments passed to importer.__init__ 
                             (e.g., user_inputs for exchange_rates)
        
        Returns:
            ImportResult with deduplicated transactions
            
        Raises:
            ValidationError: If importer.validate() fails
        """
        logger.debug("kwargs received by ImportPipeline.run: %s", importer_kwargs)
        importer = self._registry.get(source, fmt, **importer_kwargs)
        logger.debug("Using importer: %s for source=%s format=%s", importer.__class__.__name__, source, fmt)
        result = importer.parse(file_bytes)
        logger.debug("calling validate")
        validation_result = importer.validate(result)
        # Parse errors must block preview even when validate() is the default (always-valid).
        combined_errors = list(validation_result.errors)
        for e in result.errors:
            if e not in combined_errors:
                combined_errors.append(e)
        if not validation_result.is_valid or combined_errors:
            # Preserve all validation errors + required_inputs hints in the message.
            error_msg = "; ".join(combined_errors) if combined_errors else "Validation failed"
            required_inputs = dict(validation_result.required_inputs or {})
            if required_inputs:
                required_months = required_inputs.get("required_months", [])
                provided_months = required_inputs.get("provided_months", [])
                error_msg += (
                    f" (required_months: {', '.join(required_months) if required_months else 'none'}; "
                    f"provided_months: {', '.join(provided_months) if provided_months else 'none'})"
                )
            exc = ValidationError(error_msg)
            # Attach structured detail for API consumers without changing the error schema.
            exc.detail = error_msg  # type: ignore[attr-defined]
            exc.required_inputs = required_inputs  # type: ignore[attr-defined]
            exc.errors = combined_errors  # type: ignore[attr-defined]
            raise exc
        
        result = self._deduplicator.filter_duplicates(result)
        return result

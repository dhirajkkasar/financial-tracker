"""
ImportPipeline — parse → validate → deduplicate.

Stateless: creates a fresh run each call. Receives dependencies via constructor.
"""
from __future__ import annotations

from app.importers.base import ImportResult
from app.importers.registry import ImporterRegistry
from app.services.imports.deduplicator import IDeduplicator


class ImportPipeline:
    """
    Runs the three-step import pipeline for a single file.

    Steps:
        1. parse    — delegate to the registered importer for (source, format)
        2. validate — call importer.validate(); append warnings to result
        3. deduplicate — filter out txn_ids already in the database
    """

    def __init__(self, registry: ImporterRegistry, deduplicator: IDeduplicator):
        self._registry = registry
        self._deduplicator = deduplicator

    def run(self, source: str, fmt: str, file_bytes: bytes, **importer_kwargs) -> ImportResult:
        # Extract filename if provided, otherwise use empty string
        filename = importer_kwargs.pop("filename", "")
        
        importer = self._registry.get(source, fmt, **importer_kwargs)
        result = importer.parse(file_bytes, filename=filename)
        warnings = importer.validate(result)
        result.warnings.extend(warnings)
        result = self._deduplicator.filter_duplicates(result)
        return result

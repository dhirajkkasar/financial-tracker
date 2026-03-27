"""
Deduplicator — pure, testable. Filters out transactions whose txn_id is
already in the database (or a provided set of known IDs).
"""
from __future__ import annotations

from typing import Protocol

from app.importers.base import ImportResult


class IDeduplicator(Protocol):
    def filter_duplicates(self, result: ImportResult) -> ImportResult: ...


class InMemoryDeduplicator:
    """
    Deduplicates against a pre-loaded set of known txn_ids.

    Use this in tests (inject the set of existing IDs directly).
    """

    def __init__(self, existing_txn_ids: set[str]):
        self._existing = existing_txn_ids

    def filter_duplicates(self, result: ImportResult) -> ImportResult:
        new_txns = []
        duplicate_count = 0
        for txn in result.transactions:
            if txn.txn_id in self._existing:
                duplicate_count += 1
            else:
                new_txns.append(txn)
        warnings = list(result.warnings)
        if duplicate_count:
            warnings.append(f"{duplicate_count} duplicate transaction(s) skipped")
        new_result = ImportResult(
            source=result.source,
            transactions=new_txns,
            snapshots=result.snapshots,
            errors=result.errors,
            warnings=warnings,
            duplicate_count=duplicate_count,
        )
        return new_result


class DBDeduplicator:
    """
    Deduplicates against the real database transaction table.
    Used in production via ImportPipeline.
    """

    def __init__(self, txn_repo):
        self._txn_repo = txn_repo

    def filter_duplicates(self, result: ImportResult) -> ImportResult:
        existing_ids = {
            txn.txn_id
            for txn in result.transactions
            if self._txn_repo.get_by_txn_id(txn.txn_id) is not None
        }
        return InMemoryDeduplicator(existing_ids).filter_duplicates(result)

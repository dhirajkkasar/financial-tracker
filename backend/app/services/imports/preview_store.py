"""
TTL-based in-memory preview store.

Replaces the module-level _PREVIEW_STORE dict in import_service.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.importers.base import ImportResult


class PreviewStore:
    """
    Stores ImportResult objects keyed by preview_id with TTL expiry.

    Not thread-safe for concurrent workers, but acceptable for single-process dev server.
    """

    def __init__(self, ttl_minutes: int = 15):
        self._ttl = timedelta(minutes=ttl_minutes)
        self._store: dict[str, tuple[ImportResult, datetime]] = {}

    def put(self, result: ImportResult) -> str:
        """Store result and return a preview_id."""
        preview_id = str(uuid.uuid4())
        self._store[preview_id] = (result, datetime.utcnow())
        return preview_id

    def get(self, preview_id: str) -> Optional[ImportResult]:
        """
        Retrieve result by preview_id. Returns None if not found or expired.
        Expired entries are cleaned up on access.
        """
        entry = self._store.get(preview_id)
        if entry is None:
            return None
        result, created_at = entry
        if datetime.utcnow() - created_at > self._ttl:
            del self._store[preview_id]
            return None
        return result

    def delete(self, preview_id: str) -> None:
        self._store.pop(preview_id, None)

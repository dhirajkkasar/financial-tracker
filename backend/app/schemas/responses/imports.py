from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class ParsedTransactionPreview(BaseModel):
    """One parsed transaction row shown in the import preview UI."""
    txn_id: str
    asset_name: str
    asset_type: str
    txn_type: str
    date: date
    units: Optional[float] = None
    amount_inr: float
    notes: Optional[str] = None
    is_duplicate: bool = False


class ImportPreviewResponse(BaseModel):
    """Response for POST /imports/preview"""
    preview_id: str
    new_count: int
    duplicate_count: int
    transactions: List[ParsedTransactionPreview]
    warnings: List[str] = []


class ImportCommitResponse(BaseModel):
    """Response for POST /imports/commit/{preview_id}"""
    inserted: int
    skipped: int
    errors: List[str] = []

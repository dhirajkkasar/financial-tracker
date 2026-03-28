from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class AssetPriceEntry(BaseModel):
    """Price record for a single asset."""
    asset_id: int
    asset_name: str
    asset_type: str
    price_inr: float
    source: str
    fetched_at: datetime
    is_stale: bool


class PriceRefreshResponse(BaseModel):
    """Response for POST /prices/refresh"""
    refreshed: int
    failed: int
    stale: int = 0
    errors: List[str] = []

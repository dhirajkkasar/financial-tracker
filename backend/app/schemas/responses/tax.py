from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class TaxGainEntry(BaseModel):
    """Rolled-up tax gains for one broad category (Equity / Debt / Gold / Real Estate)."""
    category: str                          # "Equity", "Debt", "Gold", "Real Estate"
    asset_types: List[str]                 # e.g. ["STOCK_IN", "MF"]
    st_gain: float                         # INR
    lt_gain: float                         # INR
    st_tax: Optional[float] = None         # None when slab rate applies
    lt_tax: Optional[float] = None         # None when slab rate applies
    is_st_slab: bool = False
    is_lt_slab: bool = False
    ltcg_exemption_used: float = 0.0       # INR, Section 112A


class TaxSummaryResponse(BaseModel):
    """Response for GET /tax/summary?fy=..."""
    fy: str                                # "2024-25"
    entries: List[TaxGainEntry]
    total_estimated_tax: Optional[float] = None


class UnrealisedGainEntry(BaseModel):
    """Unrealised gain for one asset (GET /tax/unrealised)."""
    asset_id: int
    asset_name: str
    asset_type: str
    st_unrealised_gain: Optional[float] = None
    lt_unrealised_gain: Optional[float] = None
    total_unrealised_gain: Optional[float] = None


class HarvestOpportunityEntry(BaseModel):
    """A lot with negative unrealised gain (tax-loss harvesting candidate)."""
    asset_id: int
    asset_name: str
    asset_type: str
    lot_id: str
    buy_date: date
    units: float
    unrealised_loss: float                 # positive number representing the loss magnitude
    is_short_term: bool

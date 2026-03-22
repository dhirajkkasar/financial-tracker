from datetime import date
from typing import Optional, List
from pydantic import BaseModel


class AssetReturnsResponse(BaseModel):
    asset_id: int
    asset_name: str
    total_invested: float  # INR
    current_value: float  # INR
    absolute_return_pct: Optional[float] = None
    xirr_pct: Optional[float] = None
    cagr_pct: Optional[float] = None
    holding_days: Optional[int] = None
    xirr_message: Optional[str] = None


class ReturnResponse(BaseModel):
    asset_id: int
    asset_type: str
    xirr: Optional[float] = None
    cagr: Optional[float] = None
    absolute_return: Optional[float] = None
    total_invested: Optional[float] = None
    current_value: Optional[float] = None
    message: Optional[str] = None
    # FD/RD specific
    maturity_amount: Optional[float] = None
    accrued_value_today: Optional[float] = None
    days_to_maturity: Optional[int] = None
    # Currently held units and average cost (market-based assets only)
    total_units: Optional[float] = None
    avg_price: Optional[float] = None
    # Lot-based gain breakdown (None for non-lot assets)
    st_unrealised_gain: Optional[float] = None
    lt_unrealised_gain: Optional[float] = None
    st_realised_gain: Optional[float] = None
    lt_realised_gain: Optional[float] = None
    # FD/RD tax fields
    taxable_interest: Optional[float] = None
    potential_tax_30pct: Optional[float] = None
    # Price cache metadata
    price_is_stale: Optional[bool] = None
    price_fetched_at: Optional[str] = None  # ISO datetime string


class LotResponse(BaseModel):
    lot_id: str
    buy_date: date
    buy_amount: float
    units: Optional[float] = None
    current_value: Optional[float] = None
    holding_days: Optional[int] = None
    is_short_term: Optional[bool] = None
    unrealised_gain: Optional[float] = None
    xirr_pct: Optional[float] = None


class LotsResponse(BaseModel):
    lots: List[LotResponse]


class OverviewReturnsResponse(BaseModel):
    total_invested: float  # INR
    total_current_value: float  # INR
    absolute_return: Optional[float] = None
    xirr: Optional[float] = None
    st_unrealised_gain: Optional[float] = None
    lt_unrealised_gain: Optional[float] = None
    st_realised_gain: Optional[float] = None
    lt_realised_gain: Optional[float] = None
    total_taxable_interest: Optional[float] = None
    total_potential_tax: Optional[float] = None


class AssetTypeBreakdownEntry(BaseModel):
    asset_type: str
    total_invested: float
    total_current_value: float
    xirr: Optional[float] = None
    current_pnl: Optional[float] = None
    alltime_pnl: Optional[float] = None


class BreakdownResponse(BaseModel):
    breakdown: List[AssetTypeBreakdownEntry]


class OverviewResponse(BaseModel):
    total_invested: float  # INR
    current_value: float  # INR
    absolute_return_pct: Optional[float] = None
    xirr_pct: Optional[float] = None
    as_of: date


class AllocationEntry(BaseModel):
    asset_class: str
    value_inr: float
    pct_of_total: float


class AllocationResponse(BaseModel):
    total_value: float
    allocations: List[AllocationEntry]


class GainerEntry(BaseModel):
    asset_id: int
    name: str
    asset_type: str
    total_invested: Optional[float] = None
    current_value: Optional[float] = None
    absolute_return_pct: Optional[float] = None
    xirr: Optional[float] = None


class GainersResponse(BaseModel):
    gainers: List[GainerEntry]
    losers: List[GainerEntry]


class BulkReturnResponse(BaseModel):
    returns: List[ReturnResponse]

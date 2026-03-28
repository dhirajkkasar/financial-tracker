from datetime import date
from typing import List, Optional
from pydantic import BaseModel
from app.schemas.responses.common import PaginatedResponse


class AssetReturnsResponse(BaseModel):
    """Service-layer return type produced by each returns strategy."""
    asset_id: int
    asset_name: str
    asset_type: str
    is_active: bool

    # Core financials (None when not computable)
    invested: Optional[float] = None          # INR
    current_value: Optional[float] = None     # INR
    current_pnl: Optional[float] = None       # unrealised, INR
    current_pnl_pct: Optional[float] = None
    alltime_pnl: Optional[float] = None       # unrealised + realised, INR
    xirr: Optional[float] = None
    cagr: Optional[float] = None
    message: Optional[str] = None            # human-readable reason when null

    # Market-based extras
    total_units: Optional[float] = None
    avg_price: Optional[float] = None
    current_price: Optional[float] = None
    price_is_stale: Optional[bool] = None
    price_fetched_at: Optional[str] = None

    # Lot-based gain breakdown
    st_unrealised_gain: Optional[float] = None
    lt_unrealised_gain: Optional[float] = None
    st_realised_gain: Optional[float] = None
    lt_realised_gain: Optional[float] = None

    # FD/RD extras
    maturity_amount: Optional[float] = None
    accrued_value_today: Optional[float] = None
    days_to_maturity: Optional[int] = None
    taxable_interest: Optional[float] = None
    potential_tax_30pct: Optional[float] = None


class LotComputedResponse(BaseModel):
    """Single FIFO lot with computed unrealised gain."""
    lot_id: str
    buy_date: date
    units: float
    buy_price_per_unit: float
    buy_amount_inr: float
    current_price: float
    current_value: float
    holding_days: int
    is_short_term: bool
    unrealised_gain: float
    unrealised_gain_pct: float


class LotsPageResponse(PaginatedResponse[LotComputedResponse]):
    """Paginated lots for a single asset."""
    pass

from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class StcgAssetEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    gain: float
    tax_estimate: float
    is_slab: bool = False
    tax_rate_pct: Optional[float] = None


class LtcgAssetEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    gain: float
    tax_estimate: float
    is_slab: bool = False
    tax_rate_pct: Optional[float] = None
    ltcg_exempt_eligible: bool = False


class InterestAssetEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    interest: float
    tax_estimate: float


class StcgSection(BaseModel):
    total_gain: float = 0.0
    total_tax: float = 0.0
    has_slab_items: bool = False
    assets: List[StcgAssetEntry] = []


class LtcgSection(BaseModel):
    total_gain: float = 0.0
    total_tax: float = 0.0
    ltcg_exemption_used: float = 0.0
    has_slab_items: bool = False
    assets: List[LtcgAssetEntry] = []


class InterestSection(BaseModel):
    total_interest: float = 0.0
    total_tax: float = 0.0
    slab_rate_pct: float = 30.0
    assets: List[InterestAssetEntry] = []


class TaxSummaryResponse(BaseModel):
    fy: str
    stcg: StcgSection = StcgSection()
    ltcg: LtcgSection = LtcgSection()
    interest: InterestSection = InterestSection()


# Keep existing UnrealisedGainEntry and HarvestOpportunityEntry unchanged
class UnrealisedGainEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    st_unrealised_gain: Optional[float] = None
    lt_unrealised_gain: Optional[float] = None
    total_unrealised_gain: Optional[float] = None


class HarvestOpportunityEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    lot_id: str
    buy_date: date
    units: float
    unrealised_loss: float
    is_short_term: bool

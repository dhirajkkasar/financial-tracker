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
    net_gain_after_setoff: float = 0.0
    total_tax: float = 0.0
    assets: List[StcgAssetEntry] = []


class LtcgSection(BaseModel):
    total_gain: float = 0.0
    net_gain_after_setoff: float = 0.0
    total_tax: float = 0.0
    ltcg_exemption_used: float = 0.0
    assets: List[LtcgAssetEntry] = []


class InterestSection(BaseModel):
    total_interest: float = 0.0
    total_tax: float = 0.0
    assets: List[InterestAssetEntry] = []


class CapitalGainsTaxSection(BaseModel):
    tax_before_surcharge_cess: float = 0.0
    surcharge: float = 0.0
    cess: float = 0.0
    total: float = 0.0


class SlabIncomeTaxSection(BaseModel):
    tax_before_surcharge_cess: float = 0.0
    surcharge: float = 0.0
    cess: float = 0.0
    total: float = 0.0


class SetoffSummary(BaseModel):
    stcl_applied: float = 0.0
    ltcl_applied: float = 0.0
    stcl_carryforward_remaining: float = 0.0
    ltcl_carryforward_remaining: float = 0.0


class CarryForwardEntry(BaseModel):
    fy_label: str
    remaining_inr: float
    expires_fy_label: str


class CarryForwardSummary(BaseModel):
    stcl: List[CarryForwardEntry] = []
    ltcl: List[CarryForwardEntry] = []


class TaxSummaryResponse(BaseModel):
    fy: str
    member_id: Optional[int] = None
    total_income_inr: float = 0.0
    stcg: StcgSection = StcgSection()
    ltcg: LtcgSection = LtcgSection()
    interest: InterestSection = InterestSection()
    capital_gains_tax: CapitalGainsTaxSection = CapitalGainsTaxSection()
    slab_income_tax: SlabIncomeTaxSection = SlabIncomeTaxSection()
    rebate_87a: float = 0.0
    total_tax: float = 0.0
    setoff_summary: SetoffSummary = SetoffSummary()
    carryforward_balances: CarryForwardSummary = CarryForwardSummary()


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

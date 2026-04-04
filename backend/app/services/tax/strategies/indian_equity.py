# backend/app/services/tax/strategies/indian_equity.py
from typing import ClassVar

from app.services.tax.strategies.base import register_tax_strategy
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy


class IndianEquityTaxGainsStrategy(FifoTaxGainsStrategy):
    """
    STOCK_IN and equity MF: STCG 20%, LTCG 12.5%, Section-112A exemption eligible.
    Holding threshold: 365 days.
    """
    stcg_days: ClassVar[int] = 365
    stcg_rate_pct: ClassVar[float | None] = 20.0
    ltcg_rate_pct: ClassVar[float | None] = 12.5
    ltcg_exempt_eligible: ClassVar[bool] = True
    ltcg_slab: ClassVar[bool] = False


@register_tax_strategy(("STOCK_IN", "*"))
class StockINTaxGainsStrategy(IndianEquityTaxGainsStrategy):
    pass


@register_tax_strategy(("MF", "EQUITY"))
class EquityMFTaxGainsStrategy(IndianEquityTaxGainsStrategy):
    pass

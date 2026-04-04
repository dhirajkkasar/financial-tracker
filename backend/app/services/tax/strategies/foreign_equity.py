from typing import ClassVar, Optional
from app.services.tax.strategies.base import register_tax_strategy
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy


@register_tax_strategy(("STOCK_US", "*"))
class ForeignEquityTaxGainsStrategy(FifoTaxGainsStrategy):
    """Foreign stocks: STCG at slab, LTCG 12.5%, 730-day threshold."""
    stcg_days: ClassVar[int] = 730
    stcg_rate_pct: ClassVar[Optional[float]] = None    # slab
    ltcg_rate_pct: ClassVar[Optional[float]] = 12.5
    ltcg_exempt_eligible: ClassVar[bool] = False
    ltcg_slab: ClassVar[bool] = False

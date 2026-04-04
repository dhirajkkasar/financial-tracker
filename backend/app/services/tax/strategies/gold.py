from typing import ClassVar, Optional
from app.services.tax.strategies.base import register_tax_strategy
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy


@register_tax_strategy(("GOLD", "*"))
class GoldTaxGainsStrategy(FifoTaxGainsStrategy):
    """Gold/Gold ETF: STCG at slab, LTCG 12.5%, 1095-day threshold."""
    stcg_days: ClassVar[int] = 1095
    stcg_rate_pct: ClassVar[Optional[float]] = None    # slab
    ltcg_rate_pct: ClassVar[Optional[float]] = 12.5
    ltcg_exempt_eligible: ClassVar[bool] = False
    ltcg_slab: ClassVar[bool] = False

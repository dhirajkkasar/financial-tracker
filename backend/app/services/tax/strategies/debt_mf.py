from typing import ClassVar, Optional
from app.services.tax.strategies.base import register_tax_strategy
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy


@register_tax_strategy(("MF", "DEBT"))
class DebtMFTaxGainsStrategy(FifoTaxGainsStrategy):
    """Debt MF: all gains at slab rate (post-2023 budget change), 365-day threshold."""
    stcg_days: ClassVar[int] = 365
    stcg_rate_pct: ClassVar[Optional[float]] = None    # slab
    ltcg_rate_pct: ClassVar[Optional[float]] = None    # slab
    ltcg_exempt_eligible: ClassVar[bool] = False
    ltcg_slab: ClassVar[bool] = True

from datetime import date
from typing import ClassVar, Optional

from app.services.tax.strategies.base import register_tax_strategy
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy

# Units bought before this date may qualify for LTCG treatment if held > 2 years
_BUDGET_2023_CUTOFF = date(2023, 4, 1)
_DEBT_MF_LTCG_DAYS = 730  # 24 months


@register_tax_strategy(("MF", "DEBT"))
class DebtMFTaxGainsStrategy(FifoTaxGainsStrategy):
    """
    Debt MF tax rules (post-2023 budget):
    - Units bought on/after April 1, 2023: always STCG at slab rate
    - Units bought before April 1, 2023, held > 24 months: LTCG at 12.5%
    - Units bought before April 1, 2023, held ≤ 24 months: STCG at slab rate
    """
    stcg_days: ClassVar[int] = 730  # baseline for lot engine; _fy_gains handles classification
    stcg_rate_pct: ClassVar[Optional[float]] = None   # slab
    ltcg_rate_pct: ClassVar[Optional[float]] = 12.5   # 12.5% for pre-2023 grandfathered LTCG
    ltcg_exempt_eligible: ClassVar[bool] = False
    ltcg_slab: ClassVar[bool] = False

    def _fy_gains(
        self, matched: list[dict], fy_start: date, fy_end: date
    ) -> tuple[float, float]:
        st, lt = 0.0, 0.0
        for m in matched:
            sell_date = m["sell_date"]
            if isinstance(sell_date, str):
                sell_date = date.fromisoformat(sell_date)
            if not (fy_start <= sell_date <= fy_end):
                continue

            buy_date = m["buy_date"]
            if isinstance(buy_date, str):
                buy_date = date.fromisoformat(buy_date)

            gain = m["realised_gain_inr"]
            holding_days = (sell_date - buy_date).days

            # Only pre-Apr-2023 lots held more than 2 years qualify for LTCG
            if buy_date < _BUDGET_2023_CUTOFF and holding_days >= _DEBT_MF_LTCG_DAYS:
                lt += gain
            else:
                st += gain
        return st, lt

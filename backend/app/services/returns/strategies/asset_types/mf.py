"""
MFStrategy — current value = units × price_cache NAV (same as all market-based assets).

Active fund:   invested = open lot cost basis; current = units × NAV; alltime_pnl = unrealised + realised.
Inactive fund: invested = 0 (no open lots); current = 0; alltime_pnl = st_realised + lt_realised from lot engine.
XIRR is computed from transaction cashflows for both states.
"""
from typing import ClassVar

from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("MF")
class MFStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 365

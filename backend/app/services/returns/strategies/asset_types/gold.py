from typing import ClassVar
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("GOLD")
class GoldStrategy(MarketBasedStrategy):
    # Finance Act 2024 w.e.f. 23-Jul-2024: gold LTCG after 24 months
    # (was 36 months). SGBs have their own 12-month strategy.
    stcg_days: ClassVar[int] = 730

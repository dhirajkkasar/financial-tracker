from typing import ClassVar
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("RSU")
class RSUStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 730

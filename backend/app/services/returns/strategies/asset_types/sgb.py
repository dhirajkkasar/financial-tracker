from typing import ClassVar
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("SGB")
class SGBStrategy(MarketBasedStrategy):
    # Listed SGBs: 12-month LTCG threshold (Finance Act 2024). RBI-maturity
    # exemption is a tax-layer concern (see SGBTaxGainsStrategy).
    stcg_days: ClassVar[int] = 365

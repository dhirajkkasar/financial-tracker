from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("PPF")
class PPFStrategy(ValuationBasedStrategy):
    pass  # Default ValuationBasedStrategy behavior is correct for PPF

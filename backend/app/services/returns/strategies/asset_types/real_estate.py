from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("REAL_ESTATE")
class RealEstateStrategy(ValuationBasedStrategy):
    pass  # Default ValuationBasedStrategy behavior is correct

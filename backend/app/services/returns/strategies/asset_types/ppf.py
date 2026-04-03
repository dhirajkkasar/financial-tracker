from typing import Optional

from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy
from app.repositories.unit_of_work import UnitOfWork


@register_strategy("PPF")
class PPFStrategy(ValuationBasedStrategy):
    pass

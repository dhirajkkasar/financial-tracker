from typing import Optional

from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy
from app.repositories.unit_of_work import UnitOfWork


@register_strategy("PPF")
class PPFStrategy(ValuationBasedStrategy):
   
    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        txns = uow.transactions.list_by_asset(asset.id)
        contributions = [abs(t.amount_inr / 100) for t in txns if t.type.value == "CONTRIBUTION"]
        return sum(contributions) if contributions else 0.0

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        invested = self.get_invested_value(asset, uow)
        txns = uow.transactions.list_by_asset(asset.id)
        interest = sum(t.amount_inr / 100 for t in txns if t.type.value == "INTEREST")
        return round(invested + interest, 2)

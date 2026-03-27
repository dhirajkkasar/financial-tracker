"""
RDStrategy — invested = sum of monthly installments (CONTRIBUTION txns),
             current_value = rd formula.
"""
from typing import Optional

from app.engine.fd_engine import compute_fd_current_value
from app.repositories.unit_of_work import UnitOfWork
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("RD")
class RDStrategy(ValuationBasedStrategy):

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        txns = uow.transactions.list_by_asset(asset.id)
        contributions = [abs(t.amount_inr / 100) for t in txns if t.type.value == "CONTRIBUTION"]
        return sum(contributions) if contributions else 0.0

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail is None:
            return None
        result = compute_fd_current_value(fd_detail)
        return result.get("accrued_value_today")

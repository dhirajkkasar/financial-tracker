"""
RDStrategy — invested = sum of monthly installments (CONTRIBUTION txns),
             current_value = rd formula for elapsed months.
"""
from datetime import date as date_cls
from typing import Optional

from app.engine.fd_engine import compute_rd_maturity
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
        principal_inr = fd_detail.principal_amount / 100.0
        total_months = round((fd_detail.maturity_date - fd_detail.start_date).days / 30.44)
        elapsed = round((date_cls.today() - fd_detail.start_date).days / 30.44)
        elapsed = max(0, min(elapsed, total_months))
        return compute_rd_maturity(principal_inr, fd_detail.interest_rate_pct, elapsed)

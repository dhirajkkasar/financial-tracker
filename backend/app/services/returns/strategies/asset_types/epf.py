"""
EPFStrategy — invested = sum of all CONTRIBUTION outflows (employee + employer + EPS).
              current_value = invested + sum of all INTEREST inflows − TDS.
"""
from typing import Optional

from app.engine.returns import OUTFLOW_TYPES
from app.repositories.unit_of_work import UnitOfWork
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("EPF")
class EPFStrategy(ValuationBasedStrategy):

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        txns = uow.transactions.list_by_asset(asset.id)
        contributions = [abs(t.amount_inr / 100) for t in txns if t.type.value == "CONTRIBUTION"]
        return sum(contributions) if contributions else 0.0

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        invested = self.get_invested_value(asset, uow)
        if not invested:
            return None  # no contributions — can't compute current value
        txns = uow.transactions.list_by_asset(asset.id)
        interest = sum(t.amount_inr / 100 for t in txns if t.type.value == "INTEREST")
        return round(invested + interest, 2)

    def build_cashflows(self, asset, uow: UnitOfWork):
        """
        XIRR cashflows: only CONTRIBUTION outflows.

        INTEREST accumulates inside the EPF account — it is NOT a cash inflow to the
        investor until withdrawal. The terminal inflow (current_value = invested +
        interest) is appended by base.compute() so XIRR is still computed correctly.
        """
        txns = uow.transactions.list_by_asset(asset.id)
        return [
            (t.date, -(t.amount_inr / 100))
            for t in txns
            if t.type.value in OUTFLOW_TYPES
        ]

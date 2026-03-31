"""
ValuationBasedStrategy — current_value = latest Valuation entry (manual passbook).

Used for PPF and REAL_ESTATE. Subclasses override get_current_value() for FD/RD.
"""
from __future__ import annotations

from typing import Optional

from app.engine.returns import OUTFLOW_TYPES
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import AssetReturnsStrategy


class ValuationBasedStrategy(AssetReturnsStrategy):
    """
    Intermediate: current_value = latest Valuation.value_inr.

    If no Valuation exists, current_value is None and xirr is None.
    """

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        valuations = uow.valuations.list_by_asset(asset.id)
        if not valuations:
            return None
        latest = sorted(valuations, key=lambda v: v.date, reverse=True)[0]
        return latest.value_inr / 100  # paise → INR

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        base = super().compute(asset, uow)
        if base.current_value is None:
            return base.model_copy(update={
                "message": "No valuation entry found. Add one via /assets/{id}/valuations.",
            })
        return base

    def get_portfolio_cashflows(self, asset, uow: UnitOfWork):
        """
        Outflows only — interest and gains accumulate inside the account and are
        already embedded in current_value (the portfolio terminal inflow). Including
        intermediate INTEREST inflows alongside the terminal would double-count returns.
        Applies to FD, RD, EPF, PPF, REAL_ESTATE.
        """
        txns = uow.transactions.list_by_asset(asset.id)
        return [
            (t.date, t.amount_inr / 100.0)
            for t in txns
            if t.type.value in OUTFLOW_TYPES
        ]

    def get_inactive_realized_gain(self, asset, uow: UnitOfWork) -> Optional[float]:
        """
        Realized gain from a closed fixed-income/valuation-based position.
        Terminal gain = final_value − total_invested (earned interest / appreciation).
        """
        current = self.get_current_value(asset, uow)
        invested = self.get_invested_value(asset, uow)
        if current is None or invested is None:
            return None
        realized = current - invested
        return realized if realized != 0 else None

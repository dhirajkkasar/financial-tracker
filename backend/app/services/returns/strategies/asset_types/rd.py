"""
RDStrategy — invested = sum of monthly installments (CONTRIBUTION txns),
             current_value = rd formula for elapsed months.
"""
from datetime import date as date_cls
from typing import Optional

from app.engine.fd_engine import compute_rd_maturity
from app.engine.returns import OUTFLOW_TYPES, compute_xirr
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("RD")
class RDStrategy(ValuationBasedStrategy):

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        txns = uow.transactions.list_by_asset(asset.id)
        contributions = [abs(t.amount_inr / 100) for t in txns if t.type.value == "CONTRIBUTION"]
        if contributions:
            return sum(contributions)
        # No CONTRIBUTION transactions: derive from fd_detail (elapsed months × monthly installment)
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail is None:
            return 0.0
        total_months = round((fd_detail.maturity_date - fd_detail.start_date).days / 30.44)
        elapsed = round((date_cls.today() - fd_detail.start_date).days / 30.44)
        elapsed = max(0, min(elapsed, total_months))
        return elapsed * (fd_detail.principal_amount / 100.0)

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail is None:
            return None
        principal_inr = fd_detail.principal_amount / 100.0
        total_months = round((fd_detail.maturity_date - fd_detail.start_date).days / 30.44)
        elapsed = round((date_cls.today() - fd_detail.start_date).days / 30.44)
        elapsed = max(0, min(elapsed, total_months))
        return compute_rd_maturity(principal_inr, fd_detail.interest_rate_pct, elapsed)

    def build_cashflows(self, asset, uow: UnitOfWork):
        """XIRR: contributions as outflows + maturity_amount as terminal at maturity_date."""
        fd = uow.fd.get_by_asset_id(asset.id)
        txns = uow.transactions.list_by_asset(asset.id)

        cashflows = [
            (t.date, -(t.amount_inr / 100))
            for t in txns
            if t.type.value in OUTFLOW_TYPES
        ]

        if fd is not None:
            principal_inr = fd.principal_amount / 100.0
            total_months = round((fd.maturity_date - fd.start_date).days / 30.44)
            maturity_amount = compute_rd_maturity(principal_inr, fd.interest_rate_pct, total_months)
            effective_end = fd.maturity_date
            cashflows.append((effective_end, -maturity_amount))

        return cashflows

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        """Use build_cashflows directly — the maturity terminal is already included."""
        invested = self.get_invested_value(asset, uow)
        current = self.get_current_value(asset, uow)
        cashflows = self.build_cashflows(asset, uow)
        xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None
        pnl = (current - invested) if (current is not None and invested is not None) else None
        pnl_pct = (pnl / invested * 100) if (pnl is not None and invested and invested > 0) else None
        return AssetReturnsResponse(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            is_active=asset.is_active,
            invested=invested,
            current_value=current,
            current_pnl=pnl,
            current_pnl_pct=pnl_pct,
            xirr=xirr,
        )

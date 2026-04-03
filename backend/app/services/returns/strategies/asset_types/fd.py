"""
FDStrategy — current_value = fd_engine formula (not latest valuation).
"""
from datetime import date as date_cls
from typing import Optional

from app.engine.fd_engine import compute_fd_current_value, compute_fd_maturity
from app.engine.returns import OUTFLOW_TYPES
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("FD")
class FDStrategy(ValuationBasedStrategy):

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """Principal from fd_detail (authoritative); fall back to OUTFLOW transactions."""
        fd = uow.fd.get_by_asset_id(asset.id)
        if fd is not None:
            return fd.principal_amount / 100.0
        txns = uow.transactions.list_by_asset(asset.id)
        outflows = [abs(t.amount_inr / 100) for t in txns if t.type.value in OUTFLOW_TYPES]
        return sum(outflows) if outflows else 0.0

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail is None:
            return None
        principal_inr = fd_detail.principal_amount / 100.0
        return compute_fd_current_value(
            principal_inr,
            fd_detail.interest_rate_pct,
            fd_detail.compounding.value,
            fd_detail.start_date,
            fd_detail.maturity_date,
        )

    def build_cashflows(self, asset, uow: UnitOfWork):
        """XIRR uses maturity_amount at maturity_date (the contractual terminal cash flow)."""
        fd = uow.fd.get_by_asset_id(asset.id)
        txns = uow.transactions.list_by_asset(asset.id)

        cashflows = [
            (t.date, -(t.amount_inr / 100))
            for t in txns
            if t.type.value in OUTFLOW_TYPES
        ]

        if fd is not None:
            principal_inr = fd.principal_amount / 100.0
            tenure_years = (fd.maturity_date - fd.start_date).days / 365.0
            maturity_amount = compute_fd_maturity(
                principal_inr, fd.interest_rate_pct, fd.compounding.value, tenure_years,
            )
            effective_end = fd.maturity_date
            cashflows.append((effective_end, -maturity_amount))

        return cashflows

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        # Compute XIRR from build_cashflows directly — maturity terminal already included
        from app.engine.returns import compute_xirr
        invested = self.get_invested_value(asset, uow)
        current = self.get_current_value(asset, uow)
        cashflows = self.build_cashflows(asset, uow)
        xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None
        pnl = (current - invested) if (current is not None and invested is not None) else None
        pnl_pct = (pnl / invested * 100) if (pnl is not None and invested and invested > 0) else None
        base = AssetReturnsResponse(
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

        fd = uow.fd.get_by_asset_id(asset.id)
        if fd is None:
            return base.model_copy(update={"message": "No FD detail found"})

        principal_inr = fd.principal_amount / 100.0
        tenure_years = (fd.maturity_date - fd.start_date).days / 365.0
        maturity_amount = compute_fd_maturity(
            principal_inr, fd.interest_rate_pct, fd.compounding.value, tenure_years,
        )
        accrued_today = compute_fd_current_value(
            principal_inr, fd.interest_rate_pct, fd.compounding.value,
            fd.start_date, fd.maturity_date,
        )
        days_to_maturity = max(0, (fd.maturity_date - date_cls.today()).days)

        # Formula-based taxable interest; fall back to summing INTEREST txns if already posted
        txns = uow.transactions.list_by_asset(asset.id)
        interest_txns = [t for t in txns if t.type.value == "INTEREST"]
        if interest_txns:
            taxable_interest = sum(abs(t.amount_inr / 100) for t in interest_txns)
        else:
            taxable_interest = max(0.0, accrued_today - principal_inr)

        return base.model_copy(update={
            "maturity_amount": maturity_amount,
            "accrued_value_today": accrued_today,
            "days_to_maturity": days_to_maturity,
            "taxable_interest": taxable_interest,
            "potential_tax_30pct": round(taxable_interest * 0.30, 2),
        })

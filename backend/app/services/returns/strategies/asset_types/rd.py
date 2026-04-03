"""
RDStrategy — invested = sum of monthly installments (CONTRIBUTION txns),
             current_value = rd formula for elapsed months.
"""
import calendar
from datetime import date as date_cls
from typing import Optional

from app.engine.fd_engine import compute_rd_maturity
from app.engine.returns import compute_xirr
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("RD")
class RDStrategy(ValuationBasedStrategy):

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail is None:
            return super().get_invested_value(asset, uow)
        total_months = round((fd_detail.maturity_date - fd_detail.start_date).days / 30.44)
        elapsed = round((date_cls.today() - fd_detail.start_date).days / 30.44)
        elapsed = max(0, min(elapsed, total_months))
        return elapsed * (fd_detail.principal_amount / 100.0)

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail is None:
            return None
        if fd_detail.is_matured and fd_detail.maturity_amount is not None:
            return fd_detail.maturity_amount / 100.0
        principal_inr = fd_detail.principal_amount / 100.0
        total_months = round((fd_detail.maturity_date - fd_detail.start_date).days / 30.44)
        elapsed = round((date_cls.today() - fd_detail.start_date).days / 30.44)
        elapsed = max(0, min(elapsed, total_months))
        return compute_rd_maturity(principal_inr, fd_detail.interest_rate_pct, elapsed)

    def get_inactive_realized_gain(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd = uow.fd.get_by_asset_id(asset.id)
        if fd is None or not fd.is_matured or fd.maturity_amount is None:
            return super().get_inactive_realized_gain(asset, uow)
        invested = self.get_invested_value(asset, uow)
        if invested is None:
            return None
        return fd.maturity_amount / 100.0 - invested

    def build_cashflows(self, asset, uow: UnitOfWork):
        """XIRR: monthly installments as outflows + maturity_amount as terminal inflow."""
        fd = uow.fd.get_by_asset_id(asset.id)
        cashflows = []

        if fd is not None:
            principal_inr = fd.principal_amount / 100.0
            total_months = round((fd.maturity_date - fd.start_date).days / 30.44)

            # One outflow per month on the same day-of-month as start_date
            start = fd.start_date
            for i in range(total_months):
                raw_month = start.month + i
                year = start.year + (raw_month - 1) // 12
                month = ((raw_month - 1) % 12) + 1
                day = min(start.day, calendar.monthrange(year, month)[1])
                cashflows.append((date_cls(year, month, day), -principal_inr))

            # Terminal inflow at maturity
            if fd.is_matured and fd.maturity_amount is not None:
                maturity_inr = fd.maturity_amount / 100.0
            else:
                maturity_inr = compute_rd_maturity(principal_inr, fd.interest_rate_pct, total_months)
            cashflows.append((fd.maturity_date, maturity_inr))

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

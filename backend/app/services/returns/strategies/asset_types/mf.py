"""
MFStrategy — uses CAS snapshot as source of truth for current value.

Snapshot < 5 days old → use snapshot.market_value directly.
Snapshot ≥ 5 days old → snapshot.closing_units × latest price_cache NAV.
"""
from datetime import date
from typing import ClassVar, Optional

from app.engine.returns import EXCLUDED_TYPES, OUTFLOW_TYPES, compute_xirr
from app.middleware.error_handler import ValidationError
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


SNAPSHOT_STALE_DAYS = 5


@register_strategy("MF")
class MFStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 365

    def _get_snapshot(self, asset, uow: UnitOfWork):
        snap = uow.cas_snapshots.get_latest_by_asset_id(asset.id)
        if snap is None:
            raise ValidationError(
                f"No CAS snapshot found for '{asset.name}'. "
                "Please import your CAS PDF statement first."
            )
        return snap

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """Invested = CAS total_cost (authoritative cost basis from statement)."""
        snap = self._get_snapshot(asset, uow)
        return snap.total_cost_inr / 100

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        snap = self._get_snapshot(asset, uow)
        today = date.today()
        snap_age = (today - snap.date).days
        if snap_age < SNAPSHOT_STALE_DAYS:
            return snap.market_value_inr / 100  # paise -> INR

        # Stale snapshot: recompute using latest NAV
        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        if price_entry is None:
            return snap.market_value_inr / 100  # best guess

        nav = price_entry.price_inr / 100
        return round(snap.closing_units * nav, 2)

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        snap = self._get_snapshot(asset, uow)

        # Fully redeemed fund
        if snap.closing_units == 0:
            txns = uow.transactions.list_by_asset(asset.id)
            invested = sum(
                abs(t.amount_inr / 100)
                for t in txns
                if t.type.value in OUTFLOW_TYPES
            )
            cashflows = [
                (t.date, -(t.amount_inr / 100))
                for t in txns
                if t.type.value not in EXCLUDED_TYPES
            ]
            xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None
            return AssetReturnsResponse(
                asset_id=asset.id,
                asset_name=asset.name,
                asset_type=asset.asset_type.value,
                is_active=asset.is_active,
                invested=invested,
                current_value=0,
                current_pnl=None,
                current_pnl_pct=None,
                xirr=xirr,
                message="Fully redeemed",
            )

        # Active fund — delegate to MarketBasedStrategy
        return super().compute(asset, uow)

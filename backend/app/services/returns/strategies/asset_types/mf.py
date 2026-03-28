"""
MFStrategy — uses CAS snapshot as source of truth for current value.

Snapshot < 5 days old → use snapshot.market_value directly.
Snapshot ≥ 5 days old → snapshot.closing_units × latest price_cache NAV.
"""
from datetime import date
from typing import ClassVar, Optional

from app.repositories.unit_of_work import UnitOfWork
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


SNAPSHOT_STALE_DAYS = 5


@register_strategy("MF")
class MFStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 365

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        from app.middleware.error_handler import ValidationError
        snap = uow.cas_snapshots.get_latest_by_asset_id(asset.id)
        if snap is None:
            raise ValidationError(
                f"No CAS snapshot found for '{asset.name}'. "
                "Please import your CAS PDF statement first."
            )

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

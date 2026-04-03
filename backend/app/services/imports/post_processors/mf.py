"""
MFPostProcessor — persists CAS snapshots after an MF import commit.
"""
from typing import ClassVar
import logging

logger = logging.getLogger(__name__)


class MFPostProcessor:
    asset_types: ClassVar[list[str]] = ["MF"]

    def process(self, asset, import_result, uow) -> None:
        with uow:
            snapshot_count = 0
            
            for snap in import_result.snapshots or []:
                if not (snap.isin == asset.identifier or snap.asset_name == asset.name):
                    continue

                uow.cas_snapshots.create(
                    asset_id=asset.id,
                    date=snap.date,
                    closing_units=snap.closing_units,
                    nav_price_inr=round(snap.nav_price_inr * 100),
                    market_value_inr=round(snap.market_value_inr * 100),
                    total_cost_inr=round(snap.total_cost_inr * 100),
                )
                asset.is_active = snap.closing_units > 0
                snapshot_count += 1
                logger.info(
                    "CAS snapshot saved for %s (id=%s): units=%.3f active=%s",
                    asset.name, asset.id, snap.closing_units, asset.is_active,
                )
            logger.info("MFPostProcessor: %d snapshots saved for asset %s (id=%s)",
                        snapshot_count, asset.name, asset.id)
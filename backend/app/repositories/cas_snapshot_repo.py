from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from app.models.cas_snapshot import CasSnapshot


class CasSnapshotRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        asset_id: int,
        date: date,
        closing_units: float,
        nav_price_inr: int,
        market_value_inr: int,
        total_cost_inr: int,
    ) -> CasSnapshot:
        snap = CasSnapshot(
            asset_id=asset_id,
            date=date,
            closing_units=closing_units,
            nav_price_inr=nav_price_inr,
            market_value_inr=market_value_inr,
            total_cost_inr=total_cost_inr,
        )
        self.db.add(snap)
        self.db.flush()
        self.db.refresh(snap)
        return snap

    def get_latest_by_asset_id(self, asset_id: int) -> Optional[CasSnapshot]:
        return (
            self.db.query(CasSnapshot)
            .filter(CasSnapshot.asset_id == asset_id)
            .order_by(CasSnapshot.date.desc(), CasSnapshot.created_at.desc())
            .first()
        )

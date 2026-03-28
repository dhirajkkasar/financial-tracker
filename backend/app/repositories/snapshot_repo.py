from datetime import date
from sqlalchemy.orm import Session
from app.models.snapshot import PortfolioSnapshot


class SnapshotRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, snapshot_date: date, total_value_paise: int, breakdown_json: str) -> PortfolioSnapshot:
        existing = self.db.query(PortfolioSnapshot).filter_by(date=snapshot_date).first()
        if existing:
            existing.total_value_paise = total_value_paise
            existing.breakdown_json = breakdown_json
            self.db.flush()
            self.db.refresh(existing)
            return existing
        snapshot = PortfolioSnapshot(
            date=snapshot_date,
            total_value_paise=total_value_paise,
            breakdown_json=breakdown_json,
        )
        self.db.add(snapshot)
        self.db.flush()
        self.db.refresh(snapshot)
        return snapshot

    def list(self, from_date: date | None = None, to_date: date | None = None) -> list[PortfolioSnapshot]:
        q = self.db.query(PortfolioSnapshot)
        if from_date:
            q = q.filter(PortfolioSnapshot.date >= from_date)
        if to_date:
            q = q.filter(PortfolioSnapshot.date <= to_date)
        return q.order_by(PortfolioSnapshot.date.asc()).all()

from __future__ import annotations

from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.snapshot import PortfolioSnapshot


class SnapshotRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, snapshot_date: date, total_value_paise: int, breakdown_json: str, member_id: Optional[int] = None) -> PortfolioSnapshot:
        q = self.db.query(PortfolioSnapshot).filter_by(date=snapshot_date)
        if member_id is not None:
            q = q.filter_by(member_id=member_id)
        existing = q.first()
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
            member_id=member_id,
        )
        self.db.add(snapshot)
        self.db.flush()
        self.db.refresh(snapshot)
        return snapshot

    def list(self, from_date: Optional[date] = None, to_date: Optional[date] = None, member_ids: Optional[list[int]] = None) -> list[PortfolioSnapshot]:
        q = self.db.query(PortfolioSnapshot)
        if member_ids is not None:
            q = q.filter(PortfolioSnapshot.member_id.in_(member_ids))
        if from_date:
            q = q.filter(PortfolioSnapshot.date >= from_date)
        if to_date:
            q = q.filter(PortfolioSnapshot.date <= to_date)
        return q.order_by(PortfolioSnapshot.date.asc()).all()

    def list_aggregated(self, from_date: Optional[date] = None, to_date: Optional[date] = None, member_ids: Optional[list[int]] = None) -> list[dict]:
        """Return date-level aggregated snapshots (SUM across members)."""
        q = self.db.query(
            PortfolioSnapshot.date,
            func.sum(PortfolioSnapshot.total_value_paise).label("total_value_paise"),
        )
        if member_ids is not None:
            q = q.filter(PortfolioSnapshot.member_id.in_(member_ids))
        if from_date:
            q = q.filter(PortfolioSnapshot.date >= from_date)
        if to_date:
            q = q.filter(PortfolioSnapshot.date <= to_date)
        q = q.group_by(PortfolioSnapshot.date).order_by(PortfolioSnapshot.date.asc())
        return [{"date": row.date, "total_value_paise": row.total_value_paise} for row in q.all()]

    def get_by_date(self, snapshot_date: date) -> Optional[PortfolioSnapshot]:
        return self.db.query(PortfolioSnapshot).filter_by(date=snapshot_date).first()

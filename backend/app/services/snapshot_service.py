import json
import logging
from typing import Optional
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.repositories.snapshot_repo import SnapshotRepository
from app.services.returns.portfolio_returns_service import PortfolioReturnsService
from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


class SnapshotService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = SnapshotRepository(db)

    def take_snapshot(self) -> dict:
        """Compute current portfolio value per member and store as today's snapshot (IST date)."""
        from datetime import datetime
        from app.repositories.member_repo import MemberRepository
        today_ist = datetime.now(tz=IST).date()

        member_repo = MemberRepository(self.db)
        members = member_repo.list_all()

        if not members:
            # Fallback: single aggregate snapshot (no members yet)
            try:
                strategy_registry = DefaultReturnsStrategyRegistry()
                svc = PortfolioReturnsService(self.db, strategy_registry)
                overview = svc.get_overview()
                total_value_inr = overview.get("total_current_value", 0.0)
                total_value_paise = round(total_value_inr * 100)
                breakdown = svc.get_breakdown()
                breakdown_dict = {
                    entry["asset_type"]: round(entry["total_current_value"] * 100)
                    for entry in breakdown.get("breakdown", [])
                }
                snapshot = self.repo.upsert(today_ist, total_value_paise, json.dumps(breakdown_dict))
                logger.info("SnapshotService: stored aggregate snapshot for %s — ₹%.2f", today_ist, total_value_inr)
                return {"date": str(snapshot.date), "total_value_inr": total_value_inr}
            except Exception as e:
                logger.warning("SnapshotService: failed to take snapshot: %s", e)
                return {}

        results = []
        for member in members:
            try:
                strategy_registry = DefaultReturnsStrategyRegistry()
                svc = PortfolioReturnsService(self.db, strategy_registry)
                overview = svc.get_overview(member_ids=[member.id])
                total_value_inr = overview.get("total_current_value", 0.0)
                total_value_paise = round(total_value_inr * 100)

                breakdown = svc.get_breakdown(member_ids=[member.id])
                breakdown_dict = {
                    entry["asset_type"]: round(entry["total_current_value"] * 100)
                    for entry in breakdown.get("breakdown", [])
                }

                snapshot = self.repo.upsert(today_ist, total_value_paise, json.dumps(breakdown_dict), member_id=member.id)
                logger.info("SnapshotService: stored snapshot for %s (member=%s) — ₹%.2f", today_ist, member.name, total_value_inr)
                results.append({"member_id": member.id, "member_name": member.name, "date": str(snapshot.date), "total_value_inr": total_value_inr})
            except Exception as e:
                logger.warning("SnapshotService: failed to take snapshot for member %s: %s", member.name, e)

        return {"snapshots": results}

    def list(self, from_date=None, to_date=None, member_ids: Optional[list[int]] = None) -> list[dict]:
        rows = self.repo.list_aggregated(from_date, to_date, member_ids)
        return [
            {
                "date": str(row["date"]),
                "total_value_inr": row["total_value_paise"] / 100.0,
            }
            for row in rows
        ]

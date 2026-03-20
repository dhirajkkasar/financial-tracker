import json
import logging
from datetime import timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.repositories.snapshot_repo import SnapshotRepository
from app.services.returns_service import ReturnsService

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


class SnapshotService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = SnapshotRepository(db)

    def take_snapshot(self) -> dict:
        """Compute current portfolio value and store as today's snapshot (IST date). Idempotent."""
        from datetime import datetime
        today_ist = datetime.now(tz=IST).date()

        try:
            overview = ReturnsService(self.db).get_overview()
            total_value_inr = overview.get("total_current_value", 0.0)
            total_value_paise = round(total_value_inr * 100)

            breakdown = ReturnsService(self.db).get_breakdown()
            breakdown_dict = {
                entry["asset_type"]: round(entry["total_current_value"] * 100)
                for entry in breakdown.get("breakdown", [])
            }
            breakdown_json = json.dumps(breakdown_dict)

            snapshot = self.repo.upsert(today_ist, total_value_paise, breakdown_json)
            logger.info("SnapshotService: stored snapshot for %s — ₹%.2f", today_ist, total_value_inr)
            return {"date": str(snapshot.date), "total_value_inr": total_value_inr}
        except Exception as e:
            logger.warning("SnapshotService: failed to take snapshot: %s", e)
            return {}

    def list(self, from_date=None, to_date=None) -> list[dict]:
        snapshots = self.repo.list(from_date, to_date)
        return [
            {
                "date": str(s.date),
                "total_value_inr": s.total_value_paise / 100.0,
                "breakdown": json.loads(s.breakdown_json or "{}"),
            }
            for s in snapshots
        ]

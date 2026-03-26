"""
Seed portfolio snapshots with historical portfolio values.
Portfolio snapshots represent daily portfolio valuations.
Idempotent — safe to run multiple times.
"""
import sys, os, json
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.snapshot import PortfolioSnapshot


def _paise(inr: float) -> int:
    return round(inr * 100)


def _add_portfolio_snapshot(db, snap_date, total_value_inr, breakdown_json):
    """Add or update portfolio snapshot."""
    existing = db.query(PortfolioSnapshot).filter_by(date=snap_date).first()
    if existing:
        existing.total_value_paise = _paise(total_value_inr)
        existing.breakdown_json = breakdown_json
        return existing

    snap = PortfolioSnapshot(
        date=snap_date,
        total_value_paise=_paise(total_value_inr),
        breakdown_json=breakdown_json,
    )
    db.add(snap)
    return snap


def seed(db):
    print("\n[Portfolio Snapshots]")

    # Create sample portfolio snapshots for recent months
    # These represent end-of-month portfolio valuations

    snapshots_data = [
        # date, total_value_inr, breakdown_json
        (date(2025, 12, 31), 2500000.0, {
            "equity": {"value": 1500000.0, "percentage": 60.0},
            "debt": {"value": 500000.0, "percentage": 20.0},
            "gold": {"value": 250000.0, "percentage": 10.0},
            "real_estate": {"value": 250000.0, "percentage": 10.0}
        }),
        (date(2025, 11, 30), 2450000.0, {
            "equity": {"value": 1470000.0, "percentage": 60.0},
            "debt": {"value": 490000.0, "percentage": 20.0},
            "gold": {"value": 245000.0, "percentage": 10.0},
            "real_estate": {"value": 245000.0, "percentage": 10.0}
        }),
        (date(2025, 10, 31), 2400000.0, {
            "equity": {"value": 1440000.0, "percentage": 60.0},
            "debt": {"value": 480000.0, "percentage": 20.0},
            "gold": {"value": 240000.0, "percentage": 10.0},
            "real_estate": {"value": 240000.0, "percentage": 10.0}
        }),
        (date(2025, 9, 30), 2350000.0, {
            "equity": {"value": 1410000.0, "percentage": 60.0},
            "debt": {"value": 470000.0, "percentage": 20.0},
            "gold": {"value": 235000.0, "percentage": 10.0},
            "real_estate": {"value": 235000.0, "percentage": 10.0}
        }),
        (date(2025, 8, 31), 2300000.0, {
            "equity": {"value": 1380000.0, "percentage": 60.0},
            "debt": {"value": 460000.0, "percentage": 20.0},
            "gold": {"value": 230000.0, "percentage": 10.0},
            "real_estate": {"value": 230000.0, "percentage": 10.0}
        }),
        (date(2025, 7, 31), 2250000.0, {
            "equity": {"value": 1350000.0, "percentage": 60.0},
            "debt": {"value": 450000.0, "percentage": 20.0},
            "gold": {"value": 225000.0, "percentage": 10.0},
            "real_estate": {"value": 225000.0, "percentage": 10.0}
        }),
    ]

    snapshots_added = 0
    for snap_date, total_value, breakdown in snapshots_data:
        _add_portfolio_snapshot(db, snap_date, total_value, json.dumps(breakdown))
        snapshots_added += 1

    db.commit()
    print(f"  {snapshots_added} portfolio snapshots created/updated.")


def main():
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
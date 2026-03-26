"""
Seed CAS snapshots for MF assets.
CAS snapshots represent the closing balance summary from CAS PDF imports.
Idempotent — safe to run multiple times.
"""
import sys, os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType
from app.models.cas_snapshot import CasSnapshot


def _paise(inr: float) -> int:
    return round(inr * 100)


def _add_cas_snapshot(db, asset_id, snap_date, closing_units, nav_price_inr,
                      market_value_inr, total_cost_inr):
    """Add CAS snapshot if it doesn't exist."""
    existing = db.query(CasSnapshot).filter_by(
        asset_id=asset_id, date=snap_date
    ).first()
    if existing:
        return existing

    snap = CasSnapshot(
        asset_id=asset_id,
        date=snap_date,
        closing_units=closing_units,
        nav_price_inr=_paise(nav_price_inr),
        market_value_inr=_paise(market_value_inr),
        total_cost_inr=_paise(total_cost_inr),
    )
    db.add(snap)
    return snap


def seed(db):
    print("\n[CAS Snapshots]")

    # Get all MF assets
    mf_assets = db.query(Asset).filter(Asset.asset_type == AssetType.MF).all()

    if not mf_assets:
        print("  No MF assets found. Run seed_market_assets.py first.")
        return

    snapshots_added = 0

    for asset in mf_assets:
        print(f"  Processing {asset.name}")

        # Create realistic CAS snapshots for recent periods
        # These represent quarterly CAS statements

        # Q4 2024 (Dec 31, 2024)
        if asset.name == "HDFC Multi Cap Fund Direct Growth":
            _add_cas_snapshot(db, asset.id, date(2024, 12, 31),
                            5000.0, 17.5, 87500.0, 85000.0)
            snapshots_added += 1

        elif asset.name == "Kotak Multicap Fund Direct Plan - Growth":
            _add_cas_snapshot(db, asset.id, date(2024, 12, 31),
                            4500.0, 19.0, 85500.0, 83000.0)
            snapshots_added += 1

        elif asset.name == "Kotak Small Cap Fund - Direct Plan - Growth":
            _add_cas_snapshot(db, asset.id, date(2024, 12, 31),
                            200.0, 260.0, 52000.0, 48000.0)
            snapshots_added += 1

        elif asset.name == "Parag Parikh Flexi Cap Fund - Direct Plan Growth (formerly Parag Parikh Long Term Value Fund)":
            _add_cas_snapshot(db, asset.id, date(2024, 12, 31),
                            300.0, 85.0, 25500.0, 24000.0)
            snapshots_added += 1

        elif asset.name == "UTI Nifty 50 Index Fund - Direct Plan":
            _add_cas_snapshot(db, asset.id, date(2024, 12, 31),
                            800.0, 80.0, 64000.0, 62000.0)
            snapshots_added += 1

        elif asset.name == "UTI Nifty Next 50 Index Fund - Direct Plan":
            _add_cas_snapshot(db, asset.id, date(2024, 12, 31),
                            1200.0, 23.0, 27600.0, 26400.0)
            snapshots_added += 1

        # Q3 2024 (Sep 30, 2024) - slightly older values
        if asset.name == "HDFC Multi Cap Fund Direct Growth":
            _add_cas_snapshot(db, asset.id, date(2024, 9, 30),
                            4800.0, 16.8, 80640.0, 79200.0)
            snapshots_added += 1

        elif asset.name == "Kotak Multicap Fund Direct Plan - Growth":
            _add_cas_snapshot(db, asset.id, date(2024, 9, 30),
                            4300.0, 18.2, 78260.0, 76600.0)
            snapshots_added += 1

    db.commit()
    print(f"  {snapshots_added} CAS snapshots created/verified.")


def main():
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
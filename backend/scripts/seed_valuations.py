"""
Seed manual valuations for assets that don't have market prices.
Valuations are for assets like real estate, PPF, EPF, etc.
Idempotent — safe to run multiple times.
"""
import sys, os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType
from app.models.valuation import Valuation


def _paise(inr: float) -> int:
    return round(inr * 100)


def _add_valuation(db, asset_id, val_date, value_inr, source="manual", notes=None):
    """Add valuation if it doesn't exist."""
    existing = db.query(Valuation).filter_by(
        asset_id=asset_id, date=val_date
    ).first()
    if existing:
        return existing

    v = Valuation(
        asset_id=asset_id,
        date=val_date,
        value_inr=_paise(value_inr),
        source=source,
        notes=notes,
    )
    db.add(v)
    return v


def seed(db):
    print("\n[Manual Valuations]")

    # Get assets that typically need manual valuations
    assets = db.query(Asset).filter(
        Asset.asset_type.in_([
            AssetType.REAL_ESTATE,
            AssetType.PPF,
            AssetType.EPF,
            AssetType.NPS,
            AssetType.FD,
            AssetType.RD
        ])
    ).all()

    if not assets:
        print("  No assets found that need manual valuations.")
        return

    valuations_added = 0

    for asset in assets:
        print(f"  Processing {asset.name} ({asset.asset_type.value})")

        # Add valuations based on asset type and name
        if asset.asset_type == AssetType.REAL_ESTATE:
            if "Bengaluru Apartment" in asset.name:
                _add_valuation(db, asset.id, date(2025, 12, 31), 8500000.0,
                             notes="Current market valuation - 3BHK apartment")
                _add_valuation(db, asset.id, date(2025, 6, 30), 8000000.0,
                             notes="Mid-year valuation")
                valuations_added += 2

        elif asset.asset_type == AssetType.PPF:
            if "PPF Account" in asset.name:
                _add_valuation(db, asset.id, date(2025, 12, 31), 1250000.0,
                             notes="PPF balance as per latest passbook")
                _add_valuation(db, asset.id, date(2025, 6, 30), 1150000.0,
                             notes="Mid-year balance")
                valuations_added += 2

        elif asset.asset_type == AssetType.EPF:
            if "EPF Account" in asset.name:
                _add_valuation(db, asset.id, date(2025, 12, 31), 2800000.0,
                             notes="EPF balance including employer contribution")
                _add_valuation(db, asset.id, date(2025, 6, 30), 2600000.0,
                             notes="Mid-year balance")
                valuations_added += 2

        elif asset.asset_type == AssetType.NPS:
            if "NPS" in asset.name:
                _add_valuation(db, asset.id, date(2025, 12, 31), 1800000.0,
                             notes="NPS Tier-I balance")
                _add_valuation(db, asset.id, date(2025, 6, 30), 1650000.0,
                             notes="Mid-year balance")
                valuations_added += 2

        elif asset.asset_type == AssetType.FD:
            if "Fixed Deposit" in asset.name:
                _add_valuation(db, asset.id, date(2025, 12, 31), 525000.0,
                             notes="FD principal + accrued interest")
                valuations_added += 1

        elif asset.asset_type == AssetType.RD:
            if "Recurring Deposit" in asset.name:
                _add_valuation(db, asset.id, date(2025, 12, 31), 420000.0,
                             notes="RD principal + accrued interest")
                valuations_added += 1

    db.commit()
    print(f"  {valuations_added} valuations created/verified.")


def main():
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
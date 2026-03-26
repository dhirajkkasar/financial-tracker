"""
Seed rich EPF data mimicking a real EPF account structure (anonymised).

Structure:
  - Transfer-in from previous employer (employee + employer share)
  - Monthly contributions: employee share, employer share, EPS (separate transactions)
  - Annual interest rows (employee, employer, EPS interest + TDS deduction)
  - Wage increase mid-2025
  - EPF valuation entry

Employer: TechCorp (anonymised)
Member ID: DEMO00012345678901234 (anonymised)
"""
import sys, os, hashlib, uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import Transaction, TransactionType
from app.models.valuation import Valuation


def _paise(inr: float) -> int:
    return round(inr * 100)


def _txn_id(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _add_txn(db, asset_id, txn_type, txn_date, amount_inr, notes=None):
    tid = _txn_id(asset_id, txn_type, txn_date, amount_inr, notes or "")
    if db.query(Transaction).filter_by(txn_id=tid).first():
        return
    lot_id = str(uuid.uuid4()) if txn_type in ("CONTRIBUTION",) else None
    db.add(Transaction(
        txn_id=tid,
        asset_id=asset_id,
        type=TransactionType(txn_type),
        date=txn_date,
        amount_inr=_paise(amount_inr),
        charges_inr=0,
        lot_id=lot_id,
        notes=notes,
    ))


def seed(db):
    print("\n[EPF Rich]")

    # Find or create EPF asset
    existing = db.query(Asset).filter_by(identifier="DEMO00012345678901234").first()
    if existing:
        print("  skip 'EPF - TechCorp' (already exists)")
        asset = existing
    else:
        asset = Asset(
            name="EPF - TechCorp",
            identifier="DEMO00012345678901234",
            asset_type=AssetType.EPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
            is_active=True,
        )
        db.add(asset)
        db.flush()
        print("  + asset 'EPF - TechCorp'")

    aid = asset.id

    # -------------------------------------------------------------------------
    # Transfer-in from previous employer (Nov 2022)
    # -------------------------------------------------------------------------
    _add_txn(db, aid, "CONTRIBUTION", date(2022, 11, 25), -1112001.0,
             notes="Transfer In - Employee Share")
    _add_txn(db, aid, "CONTRIBUTION", date(2022, 11, 25), -904786.0,
             notes="Transfer In - Employer Share")

    # -------------------------------------------------------------------------
    # Initial small contribution for Oct 2022 (partial month)
    # -------------------------------------------------------------------------
    _add_txn(db, aid, "CONTRIBUTION", date(2022, 10, 31), -300.0,
             notes="Employee Share")
    _add_txn(db, aid, "CONTRIBUTION", date(2022, 10, 31), -92.0,
             notes="Employer Share")
    _add_txn(db, aid, "CONTRIBUTION", date(2022, 10, 31), -208.0,
             notes="Pension Contribution (EPS)")

    # -------------------------------------------------------------------------
    # Monthly contributions Nov 2022 – Apr 2025 (₹27k/₹25.75k/₹1.25k)
    # Wage increase from May 2025: ₹38.87k/₹37.62k/₹1.25k
    # -------------------------------------------------------------------------
    # Phase 1: Nov 2022 – Apr 2025
    phase1_months = []
    for year in range(2022, 2026):
        for month in range(1, 13):
            if year == 2022 and month < 11:
                continue
            if year == 2025 and month > 4:
                break
            # Get the last day of the month
            if month == 12:
                last_day = 31
            elif month == 2:
                last_day = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
            elif month in (4, 6, 9, 11):
                last_day = 30
            else:
                last_day = 31
            phase1_months.append(date(year, month, last_day))

    for d in phase1_months:
        _add_txn(db, aid, "CONTRIBUTION", d, -27000.0, notes="Employee Share")
        _add_txn(db, aid, "CONTRIBUTION", d, -25750.0, notes="Employer Share")
        _add_txn(db, aid, "CONTRIBUTION", d, -1250.0,  notes="Pension Contribution (EPS)")

    # Phase 2: May 2025 – Mar 2026 (after wage revision)
    phase2_months = []
    for year in range(2025, 2027):
        for month in range(1, 13):
            if year == 2025 and month < 5:
                continue
            if year == 2026 and month > 3:
                break
            phase2_months.append(date(year, month, 28 if month == 2 else 30 if month in (4,6,9,11) else 31))

    for d in phase2_months:
        _add_txn(db, aid, "CONTRIBUTION", d, -38870.0, notes="Employee Share")
        _add_txn(db, aid, "CONTRIBUTION", d, -37620.0, notes="Employer Share")
        _add_txn(db, aid, "CONTRIBUTION", d, -1250.0,  notes="Pension Contribution (EPS)")

    # -------------------------------------------------------------------------
    # Annual interest entries
    # -------------------------------------------------------------------------
    # FY 2022-23 (8.15%)
    _add_txn(db, aid, "INTEREST", date(2023, 3, 31), 39720.0,
             notes="Employee Interest")
    _add_txn(db, aid, "INTEREST", date(2023, 3, 31), 32591.0,
             notes="Employer Interest")
    _add_txn(db, aid, "INTEREST", date(2023, 3, 31), 0.0,
             notes="EPS Interest")

    # FY 2023-24 (8.25%)
    _add_txn(db, aid, "INTEREST", date(2024, 3, 31), 122874.0,
             notes="Employee Interest")
    _add_txn(db, aid, "INTEREST", date(2024, 3, 31), 103302.0,
             notes="Employer Interest")
    _add_txn(db, aid, "INTEREST", date(2024, 3, 31), 0.0,
             notes="EPS Interest")

    # FY 2024-25 (8.25%) — with TDS
    _add_txn(db, aid, "INTEREST", date(2025, 3, 31), 159741.0,
             notes="Employee Interest")
    _add_txn(db, aid, "INTEREST", date(2025, 3, 31), 137317.0,
             notes="Employer Interest")
    _add_txn(db, aid, "INTEREST", date(2025, 3, 31), 0.0,
             notes="EPS Interest")
    _add_txn(db, aid, "INTEREST", date(2025, 3, 31), -660.0,
             notes="TDS Deduction")

    # -------------------------------------------------------------------------
    # Valuation (EPF passbook balance — computed value)
    # -------------------------------------------------------------------------
    if not db.query(Valuation).filter_by(asset_id=aid, date=date(2026, 3, 24)).first():
        db.add(Valuation(
            asset_id=aid,
            date=date(2026, 3, 24),
            value_inr=_paise(0),   # EPF valuation computed from transactions
            source="epf_pdf",
            notes="Net balance from PDF import (member DEMO00012345678901234)",
        ))

    db.commit()
    print("  + EPF TechCorp: transfer-in + ~50 months contributions + annual interest + TDS")


def main():
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()

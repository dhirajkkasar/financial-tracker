"""
Seed a comprehensive set of FD/RD assets mimicking a real multi-bank portfolio.

FDs (active/recently matured):
  1. SBI FD — Family 2026   ₹22.6L @ 6.8% quarterly  (Jan 2025 – Dec 2026)
  2. HDFC FD — Self 2026    ₹1.76L @ 7.25% quarterly (Nov 2024 – May 2026)
  3. ICICI FD — HUF         ₹1.0L  @ 7.2% quarterly  (Jul 2024 – Jan 2026)  ← matured
  4. SBI FD — Self          ₹2.0L  @ 7.0% monthly    (Jan 2024 – Jan 2026)  ← matured
  5. HDFC FD — Self 2027    ₹2.0L  @ 7.25% quarterly (Feb 2025 – Aug 2026)
  6. SBI FD — Family 2027   ₹0.45L @ 6.7% quarterly  (May 2025 – May 2027)

RD:
  7. SBI RD — Monthly ₹5k   @ 7.0% quarterly (Jun 2024 – Jun 2026)

All amounts anonymised (slight differences from real data).
Idempotent — safe to run multiple times.
"""
import sys, os, hashlib, uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import Transaction, TransactionType
from app.models.fd_detail import FDDetail, FDType, CompoundingType


def _p(inr: float) -> int:
    return round(inr * 100)


def _txn_id(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _lot() -> str:
    return str(uuid.uuid4())


def _find_or_create_asset(db, identifier: str, name: str, **kwargs) -> Asset:
    existing = db.query(Asset).filter_by(identifier=identifier).first()
    if existing:
        print(f"  skip '{name}' (exists)")
        return existing
    a = Asset(identifier=identifier, name=name, **kwargs)
    db.add(a)
    db.flush()
    print(f"  + {name}")
    return a


def _add_txn(db, asset_id, txn_type, txn_date, amount_inr, notes=None):
    tid = _txn_id("fd", asset_id, txn_type, txn_date, amount_inr)
    if db.query(Transaction).filter_by(txn_id=tid).first():
        return
    db.add(Transaction(
        txn_id=tid,
        asset_id=asset_id,
        type=TransactionType(txn_type),
        date=txn_date,
        amount_inr=_p(amount_inr),
        charges_inr=0,
        lot_id=_lot() if txn_type == "CONTRIBUTION" else None,
        notes=notes,
    ))


def _add_fd_detail(db, asset_id, bank, fd_type, principal_inr,
                   rate, compounding, start, maturity,
                   maturity_amount_inr=None, is_matured=False, tds=True):
    if db.query(FDDetail).filter_by(asset_id=asset_id).first():
        return
    db.add(FDDetail(
        asset_id=asset_id,
        bank=bank,
        fd_type=fd_type,
        principal_amount=_p(principal_inr),
        interest_rate_pct=rate,
        compounding=compounding,
        start_date=start,
        maturity_date=maturity,
        maturity_amount=_p(maturity_amount_inr) if maturity_amount_inr else None,
        is_matured=is_matured,
        tds_applicable=tds,
    ))


def seed(db):
    print("\n[FD / RD — Comprehensive]")

    # 1. SBI FD — Family 2026
    a1 = _find_or_create_asset(
        db, identifier="SBI-FD-FAM-2026", name="SBI FD — Family 2026",
        asset_type=AssetType.FD, asset_class=AssetClass.DEBT, currency="INR", is_active=True,
    )
    _add_fd_detail(db, a1.id, "SBI", FDType.FD, 2260000, 6.8,
                   CompoundingType.QUARTERLY, date(2025, 1, 10), date(2026, 12, 10), tds=True)
    _add_txn(db, a1.id, "CONTRIBUTION", date(2025, 1, 10), -2260000.0, notes="FD principal")

    # 2. HDFC FD — Self 2026
    a2 = _find_or_create_asset(
        db, identifier="HDFC-FD-SELF-2026", name="HDFC FD — Self 2026",
        asset_type=AssetType.FD, asset_class=AssetClass.DEBT, currency="INR", is_active=True,
    )
    _add_fd_detail(db, a2.id, "HDFC Bank", FDType.FD, 176000, 7.25,
                   CompoundingType.QUARTERLY, date(2024, 11, 5), date(2026, 5, 5), tds=True)
    _add_txn(db, a2.id, "CONTRIBUTION", date(2024, 11, 5), -176000.0, notes="FD principal")

    # 3. ICICI FD — HUF (maturity 2026-01-04 — will be auto-matured on server start)
    a3 = _find_or_create_asset(
        db, identifier="ICICI-FD-HUF", name="ICICI FD — HUF",
        asset_type=AssetType.FD, asset_class=AssetClass.DEBT, currency="INR", is_active=True,
    )
    _add_fd_detail(db, a3.id, "ICICI Bank", FDType.FD, 100000, 7.2,
                   CompoundingType.QUARTERLY, date(2024, 7, 4), date(2026, 1, 4), tds=False)
    _add_txn(db, a3.id, "CONTRIBUTION", date(2024, 7, 4), -100000.0, notes="FD principal")

    # 4. SBI FD — Self (maturity 2026-01-11 — will be auto-matured on server start)
    a4 = _find_or_create_asset(
        db, identifier="SBI-FD-SELF-2026", name="SBI FD — Self",
        asset_type=AssetType.FD, asset_class=AssetClass.DEBT, currency="INR", is_active=True,
    )
    _add_fd_detail(db, a4.id, "SBI", FDType.FD, 200000, 7.0,
                   CompoundingType.MONTHLY, date(2024, 1, 11), date(2026, 1, 11), tds=True)
    _add_txn(db, a4.id, "CONTRIBUTION", date(2024, 1, 11), -200000.0, notes="FD principal")

    # 5. HDFC FD — Self 2027
    a5 = _find_or_create_asset(
        db, identifier="HDFC-FD-SELF-2027", name="HDFC FD — Self 2027",
        asset_type=AssetType.FD, asset_class=AssetClass.DEBT, currency="INR", is_active=True,
    )
    _add_fd_detail(db, a5.id, "HDFC Bank", FDType.FD, 200000, 7.25,
                   CompoundingType.QUARTERLY, date(2025, 2, 22), date(2026, 8, 22), tds=True)
    _add_txn(db, a5.id, "CONTRIBUTION", date(2025, 2, 22), -200000.0, notes="FD principal")

    # 6. SBI FD — Family 2027
    a6 = _find_or_create_asset(
        db, identifier="SBI-FD-FAM-2027", name="SBI FD — Family 2027",
        asset_type=AssetType.FD, asset_class=AssetClass.DEBT, currency="INR", is_active=True,
    )
    _add_fd_detail(db, a6.id, "SBI", FDType.FD, 45000, 6.7,
                   CompoundingType.QUARTERLY, date(2025, 5, 31), date(2027, 5, 31), tds=False)
    _add_txn(db, a6.id, "CONTRIBUTION", date(2025, 5, 31), -45000.0, notes="FD principal")

    # 7. SBI RD — Monthly ₹5k
    a7 = _find_or_create_asset(
        db, identifier="SBI-RD-SELF-2026", name="SBI RD — Monthly ₹5k",
        asset_type=AssetType.RD, asset_class=AssetClass.DEBT, currency="INR", is_active=True,
    )
    _add_fd_detail(db, a7.id, "SBI", FDType.RD, 5000, 7.0,
                   CompoundingType.QUARTERLY, date(2024, 6, 1), date(2026, 6, 1), tds=False)
    # Monthly RD instalments Jun 2024 – Mar 2026
    rd_start = date(2024, 6, 1)
    rd_end   = date(2026, 3, 1)
    d = rd_start
    instalment = 1
    while d <= rd_end:
        _add_txn(db, a7.id, "CONTRIBUTION", d, -5000.0,
                 notes=f"RD instalment {instalment}")
        instalment += 1
        mo = d.month % 12 + 1
        yr = d.year + (1 if d.month == 12 else 0)
        d = d.replace(year=yr, month=mo)

    db.commit()
    print("  7 FD/RD assets seeded.")


def main():
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()

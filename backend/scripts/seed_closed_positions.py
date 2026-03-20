"""
Seed closed/inactive positions to verify Show Inactive toggle:

  Stocks   — 2 fully sold (profit), 1 fully sold (loss) → inactive
  MFs      — 2 fully redeemed (profit), 1 fully redeemed (loss) → inactive
  FDs      — 2 matured FDs (inactive), 1 active FD added for variety
  NPS      — extra CONTRIBUTION lots + 1 WITHDRAWAL on NPS asset 29

Idempotent — re-running skips already-existing records via txn_id hash.

Usage:
    cd backend
    python scripts/seed_closed_positions.py
"""
import sys, os, hashlib, uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import Transaction, TransactionType
from app.models.fd_detail import FDDetail, FDType, CompoundingType


# ── helpers ──────────────────────────────────────────────────────────────────

def _p(inr: float) -> int:
    """INR → paise."""
    return round(inr * 100)

def _tid(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]

def _lot() -> str:
    return str(uuid.uuid4())

def _asset(db, *, name, identifier=None, asset_type, asset_class,
           currency="INR", is_active=True, notes=None) -> Asset:
    q = db.query(Asset).filter_by(name=name)
    if identifier:
        q = db.query(Asset).filter_by(identifier=identifier)
    existing = q.first()
    if existing:
        print(f"  skip '{name}' (exists, id={existing.id})")
        return existing
    a = Asset(
        name=name, identifier=identifier,
        asset_type=asset_type, asset_class=asset_class,
        currency=currency, is_active=is_active, notes=notes,
    )
    db.add(a)
    db.flush()
    print(f"  + '{name}' (id={a.id}, active={is_active})")
    return a

def _txn(db, asset_id, txn_type, txn_date, amount_inr,
         units=None, price_per_unit=None, charges=0.0, notes=None) -> Transaction:
    tid = _tid("closed", asset_id, txn_type, txn_date, amount_inr, units)
    if db.query(Transaction).filter_by(txn_id=tid).first():
        return None
    needs_lot = txn_type in ("BUY", "SIP", "CONTRIBUTION", "VEST")
    t = Transaction(
        txn_id=tid,
        asset_id=asset_id,
        type=TransactionType(txn_type),
        date=txn_date,
        units=units,
        price_per_unit=price_per_unit,
        amount_inr=_p(amount_inr),
        charges_inr=_p(charges),
        lot_id=_lot() if needs_lot else None,
        notes=notes,
    )
    db.add(t)
    return t


# ── Stocks ────────────────────────────────────────────────────────────────────

def seed_closed_stocks(db):
    print("\n[Closed Stocks]")

    # 1. RELIANCE — bought 2022, sold 2024 at +42% profit → inactive
    rel = _asset(db, name="RELIANCE", identifier="INE002A01018",
                 asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY,
                 is_active=False, notes="Fully exited position")
    _txn(db, rel.id, "BUY", date(2022, 1, 10), -240000.0,
         units=100, price_per_unit=2400.0, notes="Bought 100 shares @ ₹2400")
    _txn(db, rel.id, "BUY", date(2022, 9, 5),  -126000.0,
         units=45,  price_per_unit=2800.0, notes="Added 45 shares @ ₹2800")
    _txn(db, rel.id, "SELL", date(2024, 2, 20), +522900.0,
         units=145, price_per_unit=3606.2, charges=450.0,
         notes="Full exit @ ₹3606 — profit ~₹1.57L")

    # 2. BAJFINANCE — bought 2023, sold 2024 at +18% profit → inactive
    baj = _asset(db, name="BAJFINANCE", identifier="INE296A01024",
                 asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY,
                 is_active=False, notes="Fully exited position")
    _txn(db, baj.id, "BUY", date(2023, 3, 14), -372000.0,
         units=50, price_per_unit=7440.0, notes="Bought 50 shares @ ₹7440")
    _txn(db, baj.id, "SELL", date(2024, 8, 5), +435250.0,
         units=50, price_per_unit=8705.0, charges=380.0,
         notes="Full exit @ ₹8705 — profit ~₹63K")

    # 3. ZOMATO — bought 2021, sold 2023 at loss → inactive
    zom = _asset(db, name="ZOMATO", identifier="INE758T01015",
                 asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY,
                 is_active=False, notes="Stop-loss exit — realised loss")
    _txn(db, zom.id, "BUY", date(2021, 7, 23), -150000.0,
         units=1000, price_per_unit=150.0, notes="IPO allotment price")
    _txn(db, zom.id, "BUY", date(2022, 1, 10), -52000.0,
         units=800, price_per_unit=65.0, notes="Averaging down")
    _txn(db, zom.id, "SELL", date(2023, 6, 15), +108900.0,
         units=1800, price_per_unit=60.5, charges=200.0,
         notes="Stop-loss exit @ ₹60.5 — loss ~₹93K")

    db.commit()
    print("  Stocks committed.")


# ── Mutual Funds ─────────────────────────────────────────────────────────────

def seed_closed_mfs(db):
    print("\n[Closed Mutual Funds]")

    # 1. Axis Bluechip Fund — SIPs 2021-2023, redeemed 2024 at profit → inactive
    axis = _asset(db, name="Axis Bluechip Fund Direct Growth",
                  identifier="AXIS-BLUECHIP-CLOSED",
                  asset_type=AssetType.MF, asset_class=AssetClass.EQUITY,
                  is_active=False, notes="Fully redeemed")
    # 24 monthly SIPs of ₹5,000 — total invested ₹1.2L
    sip_schedule = [
        (date(2021,  7, 10),  263.85, 18.95),
        (date(2021,  8, 10),  271.74, 18.40),
        (date(2021,  9, 10),  257.73, 19.40),
        (date(2021, 10, 10),  244.14, 20.48),
        (date(2021, 11, 10),  248.26, 20.14),
        (date(2021, 12, 10),  239.08, 20.91),
        (date(2022,  1, 10),  253.81, 19.70),
        (date(2022,  2, 10),  275.48, 18.15),
        (date(2022,  3, 10),  289.44, 17.27),
        (date(2022,  4, 10),  282.11, 17.72),
        (date(2022,  5, 10),  294.62, 16.97),
        (date(2022,  6, 10),  318.47, 15.70),
        (date(2022,  7, 10),  297.09, 16.83),
        (date(2022,  8, 10),  274.73, 18.20),
        (date(2022,  9, 10),  285.71, 17.50),
        (date(2022, 10, 10),  262.47, 19.05),
        (date(2022, 11, 10),  249.38, 20.05),
        (date(2022, 12, 10),  254.07, 19.68),
        (date(2023,  1, 10),  240.19, 20.82),
        (date(2023,  2, 10),  263.85, 18.95),
        (date(2023,  3, 10),  271.74, 18.40),
        (date(2023,  4, 10),  257.73, 19.40),
        (date(2023,  5, 10),  244.14, 20.48),
        (date(2023,  6, 10),  248.26, 20.14),
    ]
    total_units = sum(u for _, u, _ in sip_schedule)
    for sip_date, units, nav in sip_schedule:
        _txn(db, axis.id, "SIP", sip_date, -5000.0,
             units=units, price_per_unit=nav)
    # Redeemed all @ NAV ₹24.80 — total ~₹1.51L (invested ₹1.2L → profit ~₹31K)
    redemption_nav = 24.80
    _txn(db, axis.id, "REDEMPTION", date(2024, 3, 15),
         +(total_units * redemption_nav),
         units=total_units, price_per_unit=redemption_nav,
         notes=f"Full redemption @ ₹{redemption_nav}")

    # 2. Mirae Asset Large Cap — lump sum + SIPs, redeemed at profit → inactive
    mirae = _asset(db, name="Mirae Asset Large Cap Fund Direct Growth",
                   identifier="MIRAE-LARGECAP-CLOSED",
                   asset_type=AssetType.MF, asset_class=AssetClass.EQUITY,
                   is_active=False, notes="Switched to flexi cap")
    _txn(db, mirae.id, "BUY", date(2020, 5, 15), -200000.0,
         units=3174.60, price_per_unit=63.00,
         notes="Lump sum during COVID dip")
    _txn(db, mirae.id, "SIP", date(2020,  9, 5), 523.56, 5000.0)
    for m, (nav,) in enumerate([
        (9.55,),(9.20,),(8.80,),(8.50,),(8.15,),(9.30,),(9.60,),(9.90,),
        (10.1,),(10.5,),(10.8,),(11.2,),(11.6,),(12.0,),(12.4,),(12.8,),
    ], start=1):
        mo = (9 + m - 1) % 12 + 1
        yr = 2020 + (9 + m - 1) // 12
        _txn(db, mirae.id, "SIP", date(yr, mo, 5), -5000.0,
             units=round(5000/nav, 2), price_per_unit=nav)
    # Full redemption @ ₹95/unit in 2022 — big profit
    all_units_mirae = 3174.60 + sum(round(5000/nav, 2) for (nav,) in [
        (9.55,),(9.20,),(8.80,),(8.50,),(8.15,),(9.30,),(9.60,),(9.90,),
        (10.1,),(10.5,),(10.8,),(11.2,),(11.6,),(12.0,),(12.4,),(12.8,),
    ]) + 523.56
    _txn(db, mirae.id, "REDEMPTION", date(2022, 11, 10),
         +(all_units_mirae * 95.0),
         units=all_units_mirae, price_per_unit=95.0,
         notes="Full redemption @ ₹95")

    # 3. ICICI Pru Technology Fund — bought at peak, redeemed at loss → inactive
    icici = _asset(db, name="ICICI Pru Technology Fund Direct Growth",
                   identifier="ICICI-TECH-CLOSED",
                   asset_type=AssetType.MF, asset_class=AssetClass.EQUITY,
                   is_active=False, notes="Redeemed at loss after tech crash")
    _txn(db, icici.id, "BUY", date(2021, 10, 18), -150000.0,
         units=1093.75, price_per_unit=137.15,
         notes="Lump sum at tech peak")
    _txn(db, icici.id, "SIP", date(2022,  1, 18), -10000.0,
         units=90.91, price_per_unit=110.0)
    _txn(db, icici.id, "SIP", date(2022,  4, 18), -10000.0,
         units=116.28, price_per_unit=86.0)
    _txn(db, icici.id, "REDEMPTION", date(2022, 12, 5), +112819.40,
         units=1300.94, price_per_unit=86.72,
         notes="Exit after -34% drawdown — loss ~₹57K")

    db.commit()
    print("  MFs committed.")


# ── Fixed Deposits ────────────────────────────────────────────────────────────

def seed_fds(db):
    print("\n[Fixed Deposits — matured + new active]")

    # 1. ICICI Bank FD — 1 year, matured → inactive
    icici_fd = _asset(db, name="ICICI Bank FD (Matured 2024)",
                      identifier="ICICI-FD-MAT-2024",
                      asset_type=AssetType.FD, asset_class=AssetClass.DEBT,
                      is_active=False, notes="Matured — proceeds moved to savings")
    if not db.query(FDDetail).filter_by(asset_id=icici_fd.id).first():
        db.add(FDDetail(
            asset_id=icici_fd.id, bank="ICICI Bank", fd_type=FDType.FD,
            principal_amount=_p(300000),
            interest_rate_pct=7.1, compounding=CompoundingType.QUARTERLY,
            start_date=date(2023, 4, 1), maturity_date=date(2024, 4, 1),
            maturity_amount=_p(321836),  # 300000 × (1+0.071/4)^4 ≈ 321836
            is_matured=True, tds_applicable=True,
        ))
        _txn(db, icici_fd.id, "CONTRIBUTION", date(2023, 4, 1), -300000.0,
             notes="FD principal")
        _txn(db, icici_fd.id, "INTEREST", date(2024, 4, 1), +21836.0,
             notes="Maturity interest (net of TDS)")
        print("  + ICICI FD (matured)")

    # 2. Axis Bank FD — 2 year, matured → inactive
    axis_fd = _asset(db, name="Axis Bank FD (Matured 2023)",
                     identifier="AXIS-FD-MAT-2023",
                     asset_type=AssetType.FD, asset_class=AssetClass.DEBT,
                     is_active=False, notes="Matured — reinvested in SGB")
    if not db.query(FDDetail).filter_by(asset_id=axis_fd.id).first():
        db.add(FDDetail(
            asset_id=axis_fd.id, bank="Axis Bank", fd_type=FDType.FD,
            principal_amount=_p(500000),
            interest_rate_pct=6.75, compounding=CompoundingType.QUARTERLY,
            start_date=date(2021, 6, 15), maturity_date=date(2023, 6, 15),
            maturity_amount=_p(575650),
            is_matured=True, tds_applicable=True,
        ))
        _txn(db, axis_fd.id, "CONTRIBUTION", date(2021, 6, 15), -500000.0,
             notes="FD principal")
        _txn(db, axis_fd.id, "INTEREST", date(2023, 6, 15), +75650.0,
             notes="Maturity interest (net of TDS)")
        print("  + Axis FD (matured)")

    # 3. Kotak Bank FD — 15 months, still active
    kotak_fd = _asset(db, name="Kotak Bank FD 2025",
                      identifier="KOTAK-FD-2025",
                      asset_type=AssetType.FD, asset_class=AssetClass.DEBT,
                      is_active=True)
    if not db.query(FDDetail).filter_by(asset_id=kotak_fd.id).first():
        db.add(FDDetail(
            asset_id=kotak_fd.id, bank="Kotak Mahindra Bank", fd_type=FDType.FD,
            principal_amount=_p(250000),
            interest_rate_pct=7.4, compounding=CompoundingType.QUARTERLY,
            start_date=date(2024, 9, 1), maturity_date=date(2025, 12, 1),
            is_matured=False, tds_applicable=True,
        ))
        _txn(db, kotak_fd.id, "CONTRIBUTION", date(2024, 9, 1), -250000.0,
             notes="FD principal")
        print("  + Kotak FD (active)")

    db.commit()
    print("  FDs committed.")


# ── NPS ───────────────────────────────────────────────────────────────────────

def seed_nps(db):
    """Add extra CONTRIBUTION lots + 1 WITHDRAWAL to NPS Tier-I (asset 29)."""
    print("\n[NPS — extra contributions + withdrawal]")

    nps = db.query(Asset).filter_by(id=29).first()
    if not nps:
        print("  NPS asset 29 not found — skipping")
        return

    # Back-fill a few more CONTRIBUTION lots on NPS Tier-I (HDFC Pension)
    extra_contribs = [
        (date(2022, 4, 10),  120.45, 41.51, -5000.0),
        (date(2022, 7, 10),  118.60, 42.16, -5000.0),
        (date(2022, 10, 10), 125.12, 39.96, -5000.0),
        (date(2023, 1, 10),  117.83, 42.44, -5000.0),
        (date(2023, 4, 10),  113.28, 44.14, -5000.0),
        (date(2023, 7, 10),  111.52, 44.84, -5000.0),
        (date(2023, 10, 10), 108.90, 45.92, -5000.0),
        (date(2024, 1, 10),  105.37, 47.45, -5000.0),
        (date(2024, 4, 10),  102.85, 48.61, -5000.0),
        (date(2024, 7, 10),  100.00, 50.00, -5000.0),
    ]
    added = 0
    for txn_date, units, nav, amount in extra_contribs:
        t = _txn(db, nps.id, "CONTRIBUTION", txn_date, amount,
                 units=units, price_per_unit=nav, notes="Annual employer NPS")
        if t:
            added += 1

    # One partial WITHDRAWAL (allowed after 3 years in Tier-I for specific goals)
    _txn(db, nps.id, "WITHDRAWAL", date(2025, 3, 31), +48000.0,
         notes="Partial withdrawal — higher education (25% of own contributions)")

    db.commit()
    print(f"  Added {added} NPS contribution lots + 1 withdrawal.")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    db = SessionLocal()
    try:
        seed_closed_stocks(db)
        seed_closed_mfs(db)
        seed_fds(db)
        seed_nps(db)
        print("\nDone — closed positions seeded.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

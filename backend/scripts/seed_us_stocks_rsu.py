"""
Seed US stock RSU + Gold ETF + SGB assets.

  AMZN RSU — 5 vest events (Sep 2023 – Mar 2026), anonymised quantities/prices
  GOLDBEES  — Gold ETF on NSE, 500 units BUY (Dec 2025)
  SGBJUN29II — Sovereign Gold Bond Jun 2029, 15 units + semi-annual interest

All values anonymised from real portfolio data.
Idempotent — safe to re-run.
"""
import sys, os, hashlib, uuid
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import Transaction, TransactionType
from app.models.price_cache import PriceCache


def _p(inr: float) -> int:
    return round(inr * 100)


def _txn_id(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _lot() -> str:
    return str(uuid.uuid4())


def _find_or_create(db, identifier: str, name: str, **kwargs) -> Asset:
    existing = db.query(Asset).filter_by(identifier=identifier).first()
    if existing:
        print(f"  skip '{name}' (exists)")
        return existing
    a = Asset(identifier=identifier, name=name, **kwargs)
    db.add(a)
    db.flush()
    print(f"  + {name}")
    return a


def _add_txn(db, asset_id, txn_type, txn_date, amount_inr,
             units=None, price_per_unit=None, forex_rate=None, notes=None):
    tid = _txn_id("us_stocks", asset_id, txn_type, txn_date, amount_inr, units or "")
    if db.query(Transaction).filter_by(txn_id=tid).first():
        return
    needs_lot = txn_type in ("BUY", "VEST", "SIP", "CONTRIBUTION")
    db.add(Transaction(
        txn_id=tid,
        asset_id=asset_id,
        type=TransactionType(txn_type),
        date=txn_date,
        units=units,
        price_per_unit=price_per_unit,
        forex_rate=forex_rate,
        amount_inr=_p(amount_inr),
        charges_inr=0,
        lot_id=_lot() if needs_lot else None,
        notes=notes,
    ))


def _price_cache(db, asset_id, price_inr):
    if not db.query(PriceCache).filter_by(asset_id=asset_id).first():
        db.add(PriceCache(
            asset_id=asset_id,
            price_inr=_p(price_inr),
            fetched_at=datetime.utcnow(),
            source="demo_seed",
            is_stale=False,
        ))


def seed_amzn_rsu(db):
    """5 vest events — anonymised from real account (employer: TechCorp Global)."""
    print("\n[AMZN RSU]")
    amzn = _find_or_create(
        db, identifier="AMZN", name="AMZN",
        asset_type=AssetType.STOCK_US,
        asset_class=AssetClass.EQUITY,
        currency="USD",
        is_active=True,
        notes="RSU vesting — TechCorp Global",
    )

    vests = [
        # (vest_date, units, usd_price, forex_rate, inr_amount)
        (date(2023,  9, 15),  17, 141.22, 82.68, -198490.0),
        (date(2024,  9, 16),  51, 184.49, 83.87, -789132.0),
        (date(2025,  3, 17),  68, 196.40, 87.40, -1167259.0),
        (date(2025,  9, 15),  68, 231.84, 87.85, -1384971.0),
        (date(2026,  3, 16),  66, 209.18, 90.95, -1255718.0),
    ]
    for vest_date, units, usd_price, forex, inr_amt in vests:
        _add_txn(db, amzn.id, "VEST", vest_date, inr_amt,
                 units=float(units), price_per_unit=usd_price, forex_rate=forex,
                 notes=f"{units} units vested @ ${usd_price:.2f} (USD/INR {forex})")

    # Current price: ~$209 × ₹90.95 ≈ ₹19,008 per share
    _price_cache(db, amzn.id, 209.18 * 90.95)
    total_units = sum(v[1] for v in vests)
    print(f"  + AMZN — {total_units} units across {len(vests)} vest events")


def seed_goldbees(db):
    """GOLDBEES Gold ETF — NSE listed, priced like a stock."""
    print("\n[GOLDBEES ETF]")
    goldbees = _find_or_create(
        db, identifier="GOLDBEES", name="GOLDBEES",
        asset_type=AssetType.STOCK_IN,
        asset_class=AssetClass.GOLD,
        currency="INR",
        is_active=True,
        notes="Gold ETF — HDFC AMC, NSE listed",
    )
    # 500 units @ ₹111.15 (Dec 2025)
    _add_txn(db, goldbees.id, "BUY", date(2025, 12, 30), -55575.0,
             units=500.0, price_per_unit=111.15,
             notes="500 units @ ₹111.15")

    # Current NAV ~₹90 (gold ETF tracks gold, 1 unit ≈ 0.01g of gold)
    _price_cache(db, goldbees.id, 90.0)
    print("  + GOLDBEES 500 units")


def seed_sgb(db):
    """SGBJUN29II — Sovereign Gold Bond, Jun 2029 series."""
    print("\n[SGB Jun 2029]")
    sgb = _find_or_create(
        db, identifier="SGBJUN29II", name="SGBJUN29II",
        asset_type=AssetType.SGB,
        asset_class=AssetClass.GOLD,
        currency="INR",
        is_active=True,
        notes="SGB Jun 2029 series — RBI issue Jun 2021",
    )
    # 15 units @ ₹4,792 issue price (Jun 2021)
    _add_txn(db, sgb.id, "BUY", date(2021, 6, 25), -71880.0,
             units=15.0, price_per_unit=4792.0,
             notes="15 units @ ₹4792 issue price")

    # Semi-annual interest: 2.5% p.a. on issue price = ₹119.80/unit/year
    # 15 units × ₹59.90/semi = ₹898.50 per payment
    interest_payments = [
        date(2021, 12, 25), date(2022,  6, 25), date(2022, 12, 25),
        date(2023,  6, 25), date(2023, 12, 25), date(2024,  6, 25),
        date(2024, 12, 25), date(2025,  6, 25), date(2025, 12, 25),
    ]
    for pd in interest_payments:
        _add_txn(db, sgb.id, "INTEREST", pd, 898.5,
                 notes="SGB semi-annual interest @2.5% p.a.")

    # Price per unit ≈ current gold spot ~₹9,500/gram (each SGB unit = 1 gram)
    _price_cache(db, sgb.id, 9500.0)
    print(f"  + SGBJUN29II 15 units + {len(interest_payments)} interest payments")


def main():
    db = SessionLocal()
    try:
        seed_amzn_rsu(db)
        seed_goldbees(db)
        seed_sgb(db)
        db.commit()
        print("\nUS stocks / RSU / Gold ETF / SGB seeded.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""
Seed historical SIP/BUY transactions for MF and Indian stock assets so XIRR
can be computed properly. Idempotent — safe to run multiple times.

Adds:
  - 3 years of monthly SIPs (Apr 2022 – Dec 2024) for each MF fund
  - Multi-lot BUY history (2020–2023) for each Indian stock
  - BUY transactions for stocks that only had SELLs (fixing 0-invested edge cases)
"""
import sys, os, hashlib
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType
from app.models.transaction import Transaction, TransactionType


def _paise(inr: float) -> int:
    return round(inr * 100)


def _txn_id(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _add_txn(db, asset_id, txn_type, txn_date, amount_inr,
             units=None, price_per_unit=None, notes=None):
    tid = _txn_id(asset_id, txn_type, txn_date, amount_inr, units)
    if db.query(Transaction).filter_by(txn_id=tid).first():
        return  # already exists
    import uuid
    lot_id = str(uuid.uuid4()) if txn_type in ("BUY", "SIP", "CONTRIBUTION", "VEST") else None
    db.add(Transaction(
        txn_id=tid,
        asset_id=asset_id,
        type=TransactionType(txn_type),
        date=txn_date,
        units=units,
        price_per_unit=price_per_unit,
        amount_inr=_paise(amount_inr),
        charges_inr=0,
        lot_id=lot_id,
        notes=notes,
    ))


def monthly_dates(start: date, end: date):
    """Yield first-of-month dates from start to end inclusive."""
    d = start.replace(day=1)
    while d <= end:
        yield d
        # advance 1 month
        month = d.month % 12 + 1
        year = d.year + (1 if d.month == 12 else 0)
        d = d.replace(year=year, month=month, day=1)


# ---------------------------------------------------------------------------
# Historical NAVs — approximate quarterly checkpoints for linear interpolation
# ---------------------------------------------------------------------------

def _lerp_nav(checkpoints: list[tuple[date, float]], target: date) -> float:
    """Linearly interpolate NAV between known checkpoints."""
    if target <= checkpoints[0][0]:
        return checkpoints[0][1]
    if target >= checkpoints[-1][0]:
        return checkpoints[-1][1]
    for i in range(len(checkpoints) - 1):
        d0, v0 = checkpoints[i]
        d1, v1 = checkpoints[i + 1]
        if d0 <= target <= d1:
            t = (target - d0).days / (d1 - d0).days
            return v0 + t * (v1 - v0)
    return checkpoints[-1][1]


# Approximate historical NAVs (₹) — intentionally slightly lower than current to
# reflect realistic 3-year growth
MF_NAV_HISTORY = {
    "HDFC Multi Cap Fund Direct Growth": [
        (date(2021, 9, 1),  10.0),   # NFO
        (date(2022, 4, 1),   9.5),
        (date(2022, 10, 1),  8.1),
        (date(2023, 4, 1),  10.8),
        (date(2023, 10, 1), 13.4),
        (date(2024, 4, 1),  15.2),
        (date(2024, 10, 1), 16.9),
        (date(2025, 3, 1),  17.9),
    ],
    "Kotak Multicap Fund Direct Plan - Growth": [
        (date(2021, 9, 1),  10.0),
        (date(2022, 4, 1),   9.8),
        (date(2022, 10, 1),  8.7),
        (date(2023, 4, 1),  11.8),
        (date(2023, 10, 1), 15.0),
        (date(2024, 4, 1),  16.8),
        (date(2024, 10, 1), 18.4),
        (date(2025, 3, 1),  19.2),
    ],
    "Kotak Small Cap Fund - Direct Plan - Growth": [
        (date(2021, 9, 1),  148.0),
        (date(2022, 4, 1),  152.0),
        (date(2022, 10, 1), 118.0),
        (date(2023, 4, 1),  172.0),
        (date(2023, 10, 1), 218.0),
        (date(2024, 4, 1),  248.0),
        (date(2024, 10, 1), 261.0),
        (date(2025, 3, 1),  267.0),
    ],
    "Parag Parikh Flexi Cap Fund - Direct Plan Growth (formerly Parag Parikh Long Term Value Fund)": [
        (date(2021, 4, 1),  42.0),
        (date(2022, 4, 1),  52.0),
        (date(2022, 10, 1), 46.0),
        (date(2023, 4, 1),  60.0),
        (date(2023, 10, 1), 71.0),
        (date(2024, 4, 1),  80.0),
        (date(2024, 10, 1), 86.0),
        (date(2025, 3, 1),  87.7),
    ],
    "UTI Nifty 50 Index Fund - Direct Plan": [
        (date(2021, 4, 1),  50.0),
        (date(2022, 4, 1),  60.0),
        (date(2022, 10, 1), 54.0),
        (date(2023, 4, 1),  68.0),
        (date(2023, 10, 1), 75.0),
        (date(2024, 4, 1),  80.0),
        (date(2024, 10, 1), 82.0),
        (date(2025, 3, 1),  81.0),
    ],
    "UTI Nifty Next 50 Index Fund - Direct Plan": [
        (date(2021, 4, 1),  12.5),
        (date(2022, 4, 1),  15.0),
        (date(2022, 10, 1), 11.5),
        (date(2023, 4, 1),  16.0),
        (date(2023, 10, 1), 19.5),
        (date(2024, 4, 1),  22.0),
        (date(2024, 10, 1), 23.0),
        (date(2025, 3, 1),  23.5),
    ],
}

# Monthly SIP amounts per fund (₹)
MF_SIP_AMOUNTS = {
    "HDFC Multi Cap Fund Direct Growth":      5000,
    "Kotak Multicap Fund Direct Plan - Growth": 5000,
    "Kotak Small Cap Fund - Direct Plan - Growth": 5000,
    "Parag Parikh Flexi Cap Fund - Direct Plan Growth (formerly Parag Parikh Long Term Value Fund)": 10000,
    "UTI Nifty 50 Index Fund - Direct Plan":  10000,
    "UTI Nifty Next 50 Index Fund - Direct Plan": 5000,
}

# SIP start dates per fund
MF_SIP_START = {
    "HDFC Multi Cap Fund Direct Growth":      date(2022, 1, 1),
    "Kotak Multicap Fund Direct Plan - Growth": date(2022, 1, 1),
    "Kotak Small Cap Fund - Direct Plan - Growth": date(2022, 1, 1),
    "Parag Parikh Flexi Cap Fund - Direct Plan Growth (formerly Parag Parikh Long Term Value Fund)": date(2021, 7, 1),
    "UTI Nifty 50 Index Fund - Direct Plan":  date(2022, 1, 1),
    "UTI Nifty Next 50 Index Fund - Direct Plan": date(2022, 1, 1),
}

SIP_END = date(2025, 12, 1)   # historical SIPs up to Dec 2025


def seed_mf_sips(db):
    print("\n[MF Historical SIPs]")
    mf_assets = db.query(Asset).filter(Asset.asset_type == AssetType.MF).all()

    for asset in mf_assets:
        nav_history = MF_NAV_HISTORY.get(asset.name)
        sip_amount  = MF_SIP_AMOUNTS.get(asset.name)
        sip_start   = MF_SIP_START.get(asset.name)
        if not nav_history or not sip_amount or not sip_start:
            print(f"  skip '{asset.name}' — no config")
            continue

        count = 0
        for sip_date in monthly_dates(sip_start, SIP_END):
            nav = _lerp_nav(nav_history, sip_date)
            units = round(sip_amount / nav, 3)
            _add_txn(db, asset.id, "SIP", sip_date, -sip_amount,
                     units=units, price_per_unit=round(nav, 4))
            count += 1

        print(f"  + {asset.name[:45]} — {count} monthly SIPs added")


# ---------------------------------------------------------------------------
# Stock historical BUY data
# Approximate historical NSE prices (₹) — realistic ballpark for demo
# ---------------------------------------------------------------------------

STOCK_BUY_HISTORY = {
    "TCS": [
        (date(2020, 6, 15),  5, 2100.0),
        (date(2021, 2, 10), 10, 3050.0),
        (date(2022, 6, 20),  5, 3300.0),
        (date(2023, 9, 5),   8, 3450.0),
        (date(2024, 3, 12),  5, 3820.0),
    ],
    "PIDILITIND": [
        (date(2020, 8, 10),  8, 1550.0),
        (date(2021, 7, 5),   5, 2050.0),
        (date(2022, 10, 14), 8, 2400.0),
        (date(2023, 5, 8),   5, 2600.0),
    ],
    "UNITDSPR": [
        (date(2020, 9, 12), 20, 580.0),
        (date(2021, 8, 3),  15, 720.0),
        (date(2022, 4, 6),  15, 810.0),
        (date(2023, 3, 9),  10, 850.0),
    ],
    "ADANIENT": [
        (date(2021, 4, 8),  10, 1020.0),
        (date(2022, 1, 11), 10, 1780.0),
        (date(2023, 6, 5),  10, 2180.0),
    ],
    "INFY": [
        (date(2020, 7, 14), 10, 840.0),
        (date(2021, 6, 9),  10, 1450.0),
        (date(2022, 7, 12), 10, 1380.0),
        (date(2023, 5, 15),  8, 1330.0),
    ],
    "PVRINOX": [
        (date(2021, 9, 8),  10, 1680.0),
        (date(2022, 8, 3),  10, 1920.0),
        (date(2023, 7, 10),  8, 1650.0),
    ],
    "SUNPHARMA": [
        (date(2020, 11, 5), 10, 530.0),
        (date(2021, 10, 12), 8, 780.0),
        (date(2022, 9, 6),   8, 870.0),
        (date(2023, 8, 14),  8, 1100.0),
    ],
    "HDFCBANK": [
        (date(2020, 9, 22), 10, 1050.0),
        (date(2021, 11, 8), 10, 1580.0),
        (date(2022, 7, 5),  10, 1310.0),
        (date(2023, 4, 4),  12, 1620.0),
    ],
    "ASIANPAINT": [
        (date(2020, 10, 7),  5, 2350.0),
        (date(2021, 9, 13),  5, 3250.0),
        (date(2022, 11, 2),  5, 2900.0),
        (date(2023, 10, 9),  5, 3100.0),
    ],
    "CROMPTON": [
        (date(2021, 5, 10), 50, 420.0),
        (date(2022, 6, 14), 30, 360.0),
        (date(2023, 7, 3),  30, 295.0),
    ],
    "HDFCAMC": [
        (date(2021, 3, 8),   5, 2800.0),
        (date(2022, 4, 4),   5, 2650.0),
        (date(2023, 5, 10),  5, 2900.0),
        (date(2024, 2, 6),   5, 3600.0),
    ],
    "CDSL": [
        (date(2021, 6, 7),  10, 820.0),
        (date(2022, 8, 9),  10, 1050.0),
        (date(2023, 9, 5),  10, 1420.0),
    ],
    "CAMS": [
        (date(2021, 4, 12), 10, 1950.0),
        (date(2022, 5, 3),  10, 2300.0),
        (date(2023, 6, 8),   8, 2650.0),
    ],
    "HAPPSTMNDS": [
        (date(2021, 7, 6),  15, 980.0),
        (date(2022, 9, 13), 15, 1150.0),
        (date(2023, 11, 7), 10, 820.0),
    ],
    "ITC": [
        (date(2020, 8, 4),  50, 195.0),
        (date(2021, 12, 8), 30, 215.0),
        (date(2022, 6, 7),  30, 265.0),
        (date(2023, 8, 1),  20, 450.0),
    ],
}


def seed_stock_history(db):
    print("\n[Indian Stock Historical BUYs]")
    stock_assets = db.query(Asset).filter(Asset.asset_type == AssetType.STOCK_IN).all()
    stock_map = {a.name: a for a in stock_assets}

    for ticker, buys in STOCK_BUY_HISTORY.items():
        asset = stock_map.get(ticker)
        if not asset:
            print(f"  skip {ticker} — asset not found")
            continue
        for buy_date, units, price in buys:
            amount = -(units * price)
            _add_txn(db, asset.id, "BUY", buy_date, amount,
                     units=float(units), price_per_unit=price)
        print(f"  + {ticker:15} — {len(buys)} BUY lots added")


def main():
    db = SessionLocal()
    try:
        seed_mf_sips(db)
        seed_stock_history(db)
        db.commit()
        print("\nDone. Historical data seeded.")
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

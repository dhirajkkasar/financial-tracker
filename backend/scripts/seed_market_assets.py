"""
Create MF and Indian stock assets needed by seed_historical_sips.py.
Idempotent — safe to re-run.

Also seeds approximate price_cache entries so the portfolio shows value
before a live price refresh.
"""
import sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType, AssetClass
from app.models.price_cache import PriceCache


def _p(inr: float) -> int:
    return round(inr * 100)


def _find_or_create(db, name, identifier=None, **kwargs) -> Asset:
    q = db.query(Asset).filter_by(name=name)
    existing = q.first()
    if existing:
        return existing
    a = Asset(name=name, identifier=identifier, **kwargs)
    db.add(a)
    db.flush()
    print(f"  + {kwargs.get('asset_type').value}: {name}")
    return a


def _price_cache(db, asset, price_inr: float):
    existing = db.query(PriceCache).filter_by(asset_id=asset.id).first()
    if existing:
        return
    db.add(PriceCache(
        asset_id=asset.id,
        price_inr=_p(price_inr),
        fetched_at=datetime.utcnow(),
        source="demo_seed",
        is_stale=False,
    ))


# ---------------------------------------------------------------------------
# Mutual Fund assets
# (identifier = mfapi scheme code; left None here — price refresh auto-fills)
# ---------------------------------------------------------------------------

MF_ASSETS = [
    # name, approx current NAV (₹) — March 2026
    ("HDFC Multi Cap Fund Direct Growth",                    18.5),
    ("Kotak Multicap Fund Direct Plan - Growth",             20.2),
    ("Kotak Small Cap Fund - Direct Plan - Growth",         272.0),
    ("Parag Parikh Flexi Cap Fund - Direct Plan Growth "
     "(formerly Parag Parikh Long Term Value Fund)",         88.3),
    ("UTI Nifty 50 Index Fund - Direct Plan",                82.5),
    ("UTI Nifty Next 50 Index Fund - Direct Plan",           24.1),
]

# ---------------------------------------------------------------------------
# Indian stock assets
# name = NSE ticker (used by yfinance TICKER.NS price feed)
# identifier = ISIN (best-effort, can be None — not required for price feed)
# approx price in ₹ — March 2026
# ---------------------------------------------------------------------------

STOCK_ASSETS = [
    # (ticker, isin, approx_price)
    ("TCS",        "INE467B01029", 3850.0),
    ("PIDILITIND", "INE318A01026", 2980.0),
    ("UNITDSPR",   "INE351K01013", 1020.0),
    ("ADANIENT",   "INE423A01024", 2250.0),
    ("INFY",       "INE009A01021", 1820.0),
    ("PVRINOX",    "INE191H01014", 1540.0),
    ("SUNPHARMA",  "INE044A01036", 1870.0),
    ("HDFCBANK",   "INE040A01034", 1820.0),
    ("ASIANPAINT", "INE021A01026", 2310.0),
    ("CROMPTON",   "INE299U01018",  265.0),
    ("HDFCAMC",    "INE127D01025", 5100.0),
    ("CDSL",       "INE736A01011", 1950.0),
    ("CAMS",       "INE596I01012", 5050.0),
    ("HAPPSTMNDS", "INE769S01029",  620.0),
    ("ITC",        "INE154A01025",  440.0),
]


def seed(db):
    print("\n[Market Assets — MF + Stocks]")

    for name, nav in MF_ASSETS:
        asset = _find_or_create(
            db, name=name,
            asset_type=AssetType.MF,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            is_active=True,
        )
        _price_cache(db, asset, nav)

    for ticker, isin, price in STOCK_ASSETS:
        asset = _find_or_create(
            db, name=ticker, identifier=isin,
            asset_type=AssetType.STOCK_IN,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            is_active=True,
        )
        _price_cache(db, asset, price)

    db.commit()
    print(f"  {len(MF_ASSETS)} MF assets + {len(STOCK_ASSETS)} stock assets created/verified.")


def main():
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()

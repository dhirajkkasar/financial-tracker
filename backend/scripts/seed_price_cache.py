"""
Seed price cache entries for assets that don't have them.
Price cache stores current market prices for assets.
Idempotent — safe to run multiple times.
"""
import sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset, AssetType, AssetClass
from app.models.price_cache import PriceCache


def _paise(inr: float) -> int:
    return round(inr * 100)


def _ensure_price_cache(db, asset, price_inr, source="seed_script"):
    """Ensure asset has a price cache entry."""
    existing = db.query(PriceCache).filter_by(asset_id=asset.id).first()
    if existing:
        return existing

    pc = PriceCache(
        asset_id=asset.id,
        price_inr=_paise(price_inr),
        fetched_at=datetime.utcnow(),
        source=source,
        is_stale=False,
    )
    db.add(pc)
    return pc


def seed(db):
    print("\n[Price Cache]")

    # Get all assets that should have price cache
    assets = db.query(Asset).filter(
        Asset.asset_type.in_([
            AssetType.STOCK_IN,
            AssetType.STOCK_US,
            AssetType.MF,
            AssetType.GOLD,
            AssetType.SGB
        ])
    ).all()

    if not assets:
        print("  No assets found that need price cache.")
        return

    price_cache_added = 0

    for asset in assets:
        print(f"  Processing {asset.name} ({asset.asset_type.value})")

        # Set default prices based on asset type and name
        price = None

        if asset.asset_type == AssetType.MF:
            # MF prices are NAVs
            if "HDFC Multi Cap" in asset.name:
                price = 18.5
            elif "Kotak Multicap" in asset.name:
                price = 20.2
            elif "Kotak Small Cap" in asset.name:
                price = 272.0
            elif "Parag Parikh Flexi Cap" in asset.name:
                price = 88.3
            elif "UTI Nifty 50" in asset.name:
                price = 82.5
            elif "UTI Nifty Next 50" in asset.name:
                price = 24.1
            else:
                price = 10.0  # default NAV

        elif asset.asset_type == AssetType.STOCK_IN:
            # Indian stock prices
            stock_prices = {
                "TCS": 3850.0,
                "PIDILITIND": 2980.0,
                "UNITDSPR": 1020.0,
                "ADANIENT": 2250.0,
                "INFY": 1820.0,
                "PVRINOX": 1540.0,
                "SUNPHARMA": 1870.0,
                "HDFCBANK": 1820.0,
                "ASIANPAINT": 2310.0,
                "CROMPTON": 265.0,
                "HDFCAMC": 5100.0,
                "CDSL": 1950.0,
                "CAMS": 5050.0,
                "HAPPSTMNDS": 620.0,
                "ITC": 440.0,
            }
            price = stock_prices.get(asset.name, 1000.0)  # default stock price

        elif asset.asset_type == AssetType.STOCK_US:
            # US stock prices (approximate as of March 2026)
            if "Apple" in asset.name or "AAPL" in asset.name:
                price = 221.0 * 84.0  # ~₹18,564
            elif "Infosys" in asset.name:
                price = 17.50 * 84.0  # ~₹1,470
            else:
                price = 100.0 * 84.0  # default US stock

        elif asset.asset_type in [AssetType.GOLD, AssetType.SGB]:
            price = 9200.0  # gold price per gram

        if price:
            _ensure_price_cache(db, asset, price)
            price_cache_added += 1

    db.commit()
    print(f"  {price_cache_added} price cache entries created/verified.")


def main():
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
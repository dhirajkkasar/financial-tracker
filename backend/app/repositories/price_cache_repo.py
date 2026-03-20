from typing import Optional
from sqlalchemy.orm import Session
from app.models.price_cache import PriceCache


class PriceCacheRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_asset_id(self, asset_id: int) -> Optional[PriceCache]:
        return self.db.query(PriceCache).filter(PriceCache.asset_id == asset_id).first()

    def upsert(self, asset_id: int, price_inr: int, source: str, fetched_at=None, is_stale: bool = False) -> PriceCache:
        from datetime import datetime
        existing = self.get_by_asset_id(asset_id)
        if existing:
            existing.price_inr = price_inr
            existing.source = source
            existing.fetched_at = fetched_at or datetime.utcnow()
            existing.is_stale = is_stale
            self.db.commit()
            self.db.refresh(existing)
            return existing
        pc = PriceCache(
            asset_id=asset_id,
            price_inr=price_inr,
            source=source,
            fetched_at=fetched_at or datetime.utcnow(),
            is_stale=is_stale,
        )
        self.db.add(pc)
        self.db.commit()
        self.db.refresh(pc)
        return pc

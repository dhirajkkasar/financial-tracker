from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class PriceCacheResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    price_inr: float  # returned as INR decimal
    fetched_at: datetime
    source: Optional[str] = None
    is_stale: bool

    @classmethod
    def from_orm_convert(cls, obj) -> "PriceCacheResponse":
        return cls(
            id=obj.id,
            asset_id=obj.asset_id,
            price_inr=obj.price_inr / 100.0,
            fetched_at=obj.fetched_at,
            source=obj.source,
            is_stale=obj.is_stale,
        )

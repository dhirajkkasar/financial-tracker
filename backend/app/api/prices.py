from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware.error_handler import NotFoundError
from app.services.price_service import PriceService
from app.services.snapshot_service import SnapshotService

router = APIRouter(tags=["prices"])


@router.get("/assets/{asset_id}/price")
def get_price(asset_id: int, db: Session = Depends(get_db)):
    svc = PriceService(db)
    cache = svc.get_price(asset_id)
    if cache is None:
        raise NotFoundError(f"No price cache for asset {asset_id}")
    return {
        "asset_id": asset_id,
        "price_inr": cache.price_inr / 100.0,
        "fetched_at": cache.fetched_at,
        "source": cache.source,
        "is_stale": cache.is_stale,
    }


@router.post("/assets/{asset_id}/price/refresh")
def refresh_price(asset_id: int, db: Session = Depends(get_db)):
    svc = PriceService(db)
    cache = svc.refresh_asset(asset_id)
    if cache is None:
        raise NotFoundError(f"No price feed available for asset {asset_id}")
    return {
        "asset_id": asset_id,
        "price_inr": cache.price_inr / 100.0,
        "fetched_at": cache.fetched_at,
        "source": cache.source,
        "is_stale": cache.is_stale,
    }


@router.post("/prices/refresh-all", status_code=status.HTTP_200_OK)
def refresh_all(db: Session = Depends(get_db)):
    svc = PriceService(db)
    result = svc.refresh_all()
    SnapshotService(db).take_snapshot()
    return result

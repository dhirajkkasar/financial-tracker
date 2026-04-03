from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_price_service, get_snapshot_service
from app.middleware.error_handler import NotFoundError
from app.services.price_service import PriceService
from app.services.snapshot_service import SnapshotService

router = APIRouter(tags=["prices"])


@router.get("/assets/{asset_id}/price")
def get_price(asset_id: int, svc: PriceService = Depends(get_price_service)):
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
def refresh_price(asset_id: int, svc: PriceService = Depends(get_price_service)):
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
def refresh_all(
    price_svc: PriceService = Depends(get_price_service),
    snapshot_svc: SnapshotService = Depends(get_snapshot_service),
):
    result = price_svc.refresh_all()
    snapshot_svc.take_snapshot()
    return result

from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_asset_service
from app.models.asset import AssetType, AssetClass
from app.schemas.asset import AssetCreate, AssetUpdate, AssetResponse
from app.services.asset_service import AssetService

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset(
    body: AssetCreate,
    service: AssetService = Depends(get_asset_service),
):
    return service.create(body)


@router.get("", response_model=list[AssetResponse])
def list_assets(
    type: Optional[AssetType] = Query(None),
    asset_class: Optional[AssetClass] = Query(None),
    active: Optional[bool] = Query(None),
    service: AssetService = Depends(get_asset_service),
):
    return service.list(asset_type=type, asset_class=asset_class, active=active)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: int, service: AssetService = Depends(get_asset_service)):
    return service.get_by_id(asset_id)


@router.put("/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: int,
    body: AssetUpdate,
    service: AssetService = Depends(get_asset_service),
):
    return service.update(asset_id, body)


@router.delete("/{asset_id}", response_model=AssetResponse)
def delete_asset(asset_id: int, service: AssetService = Depends(get_asset_service)):
    return service.delete(asset_id)

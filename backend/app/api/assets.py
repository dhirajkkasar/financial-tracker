from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import NotFoundError
from app.models.asset import Asset, AssetType, AssetClass
from app.repositories.asset_repo import AssetRepository
from app.repositories.goal_repo import GoalRepository
from app.schemas.asset import AssetCreate, AssetUpdate, AssetResponse

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset(body: AssetCreate, db: Session = Depends(get_db)):
    repo = AssetRepository(db)
    asset = repo.create(**body.model_dump())
    return asset


@router.get("", response_model=list[AssetResponse])
def list_assets(
    type: Optional[AssetType] = Query(None),
    asset_class: Optional[AssetClass] = Query(None),
    active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    repo = AssetRepository(db)
    return repo.list(asset_type=type, asset_class=asset_class, active=active)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    repo = AssetRepository(db)
    asset = repo.get_by_id(asset_id)
    if not asset:
        raise NotFoundError(f"Asset {asset_id} not found")
    allocations = GoalRepository(db).list_allocations_for_asset(asset_id)
    asset.goals = [{"id": a.goal.id, "name": a.goal.name} for a in allocations]
    return asset


@router.put("/{asset_id}", response_model=AssetResponse)
def update_asset(asset_id: int, body: AssetUpdate, db: Session = Depends(get_db)):
    repo = AssetRepository(db)
    asset = repo.get_by_id(asset_id)
    if not asset:
        raise NotFoundError(f"Asset {asset_id} not found")
    return repo.update(asset, **body.model_dump(exclude_none=True))


@router.delete("/{asset_id}", response_model=AssetResponse)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    repo = AssetRepository(db)
    asset = repo.get_by_id(asset_id)
    if not asset:
        raise NotFoundError(f"Asset {asset_id} not found")
    return repo.soft_delete(asset)


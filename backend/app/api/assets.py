import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import NotFoundError
from app.models.asset import Asset, AssetType, AssetClass
from app.repositories.asset_repo import AssetRepository
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


@router.post("/fix-inactive-stocks")
def fix_inactive_stocks(db: Session = Depends(get_db)):
    """
    Retroactively scan all STOCK_IN/STOCK_US assets.
    Mark as inactive any asset whose net_units (total bought - total sold) <= 0.
    Idempotent — safe to run multiple times.
    """
    from app.repositories.transaction_repo import TransactionRepository

    _UNIT_ADD_TYPES = {"BUY", "SIP", "VEST"}
    _UNIT_SUB_TYPES = {"SELL", "REDEMPTION"}
    stock_types = [AssetType.STOCK_IN, AssetType.STOCK_US]

    assets = db.query(Asset).filter(Asset.asset_type.in_(stock_types)).all()
    txn_repo = TransactionRepository(db)
    fixed = 0

    for asset in assets:
        txns = txn_repo.list_by_asset(asset.id)
        net_units = sum(
            (t.units or 0.0) if t.type.value in _UNIT_ADD_TYPES
            else -(t.units or 0.0) if t.type.value in _UNIT_SUB_TYPES
            else 0.0
            for t in txns
        )
        if net_units < -1e-6:
            logging.getLogger(__name__).warning(
                "Asset %d '%s' has negative net_units=%.4f — skipping", asset.id, asset.name, net_units
            )
            continue
        if net_units <= 1e-6 and asset.is_active:
            asset.is_active = False
            fixed += 1

    db.commit()
    return {"fixed": fixed, "total_checked": len(assets)}

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import NotFoundError, ValidationError
from app.repositories.asset_repo import AssetRepository
from app.services.corp_actions_service import CorpActionsService

router = APIRouter(prefix="/corp-actions", tags=["corp-actions"])


@router.post("/fetch-all")
def fetch_all_corp_actions(db: Session = Depends(get_db)):
    """Fetch and apply corporate actions for all active STOCK_IN assets."""
    return CorpActionsService(db).process_all_stocks()


@router.post("/fetch-asset/{asset_id}")
def fetch_asset_corp_actions(asset_id: int, db: Session = Depends(get_db)):
    """Fetch and apply corporate actions for a single asset."""
    asset = AssetRepository(db).get_by_id(asset_id)
    if not asset:
        raise NotFoundError(f"Asset {asset_id} not found")
    if asset.asset_type.value != "STOCK_IN":
        raise ValidationError("Corp actions only apply to STOCK_IN assets")
    return CorpActionsService(db).process_asset(asset)

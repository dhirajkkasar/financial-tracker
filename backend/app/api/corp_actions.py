from fastapi import APIRouter, Depends

from app.api.dependencies import get_corp_actions_service
from app.services.corp_actions_service import CorpActionsService

router = APIRouter(prefix="/corp-actions", tags=["corp-actions"])


@router.post("/fetch-all")
def fetch_all_corp_actions(svc: CorpActionsService = Depends(get_corp_actions_service)):
    """Fetch and apply corporate actions for all active STOCK_IN assets."""
    return svc.process_all_stocks()


@router.post("/fetch-asset/{asset_id}")
def fetch_asset_corp_actions(asset_id: int, svc: CorpActionsService = Depends(get_corp_actions_service)):
    """Fetch and apply corporate actions for a single asset."""
    return svc.process_asset_by_id(asset_id)

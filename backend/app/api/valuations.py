from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_valuation_service
from app.schemas.valuation import ValuationCreate, ValuationResponse
from app.services.valuation_service import ValuationService

router = APIRouter(prefix="/assets/{asset_id}/valuations", tags=["valuations"])


@router.get("", response_model=list[ValuationResponse])
def list_valuations(asset_id: int, svc: ValuationService = Depends(get_valuation_service)):
    return svc.list(asset_id)


@router.post("", response_model=ValuationResponse, status_code=status.HTTP_201_CREATED)
def create_valuation(asset_id: int, body: ValuationCreate, svc: ValuationService = Depends(get_valuation_service)):
    return svc.create(asset_id, body)


@router.delete("/{valuation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_valuation(asset_id: int, valuation_id: int, svc: ValuationService = Depends(get_valuation_service)):
    svc.delete(asset_id, valuation_id)

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import NotFoundError
from app.repositories.asset_repo import AssetRepository
from app.repositories.valuation_repo import ValuationRepository
from app.schemas.valuation import ValuationCreate, ValuationResponse

router = APIRouter(prefix="/assets/{asset_id}/valuations", tags=["valuations"])


@router.get("", response_model=list[ValuationResponse])
def list_valuations(asset_id: int, db: Session = Depends(get_db)):
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")
    repo = ValuationRepository(db)
    valuations = repo.list_by_asset(asset_id)
    return [ValuationResponse.from_orm_convert(v) for v in valuations]


@router.post("", response_model=ValuationResponse, status_code=status.HTTP_201_CREATED)
def create_valuation(asset_id: int, body: ValuationCreate, db: Session = Depends(get_db)):
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")

    data = body.model_dump()
    data["value_inr"] = round(data["value_inr"] * 100)
    data["asset_id"] = asset_id

    repo = ValuationRepository(db)
    val = repo.create(**data)
    return ValuationResponse.from_orm_convert(val)


@router.delete("/{valuation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_valuation(asset_id: int, valuation_id: int, db: Session = Depends(get_db)):
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")

    repo = ValuationRepository(db)
    val = repo.get_by_id(valuation_id)
    if not val or val.asset_id != asset_id:
        raise NotFoundError(f"Valuation {valuation_id} not found")
    repo.delete(val)

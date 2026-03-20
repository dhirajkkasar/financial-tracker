import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import ValidationError
from app.services.tax_service import TaxService
from app.engine.tax_engine import parse_fy

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tax", tags=["tax"])


def get_tax_service(db: Session = Depends(get_db)) -> TaxService:
    return TaxService(db)


@router.get("/summary")
def get_tax_summary(
    fy: str = Query(..., description="Fiscal year label, e.g. '2024-25'"),
    svc: TaxService = Depends(get_tax_service),
):
    try:
        parse_fy(fy)
    except ValueError as e:
        raise ValidationError(str(e))
    return svc.get_tax_summary(fy)


@router.get("/unrealised")
def get_unrealised(svc: TaxService = Depends(get_tax_service)):
    return svc.get_unrealised_summary()


@router.get("/harvest-opportunities")
def get_harvest_opportunities(svc: TaxService = Depends(get_tax_service)):
    return svc.get_harvest_opportunities()

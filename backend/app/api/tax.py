import logging

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_tax_service
from app.middleware.error_handler import ValidationError
from app.services.tax_service import TaxService
from app.engine.tax_engine import parse_fy

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/fiscal-years")
def get_fiscal_years(svc: TaxService = Depends(get_tax_service)):
    return {"fiscal_years": svc.get_available_fys()}


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

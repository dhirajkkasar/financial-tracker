from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_interest_rate_service
from app.models.interest_rate import InstrumentType
from app.schemas.interest_rate import InterestRateResponse
from app.services.interest_rate_service import InterestRateService

router = APIRouter(prefix="/interest-rates", tags=["interest-rates"])


@router.get("/all", response_model=list[InterestRateResponse])
def list_all_rates(
    instrument: Optional[InstrumentType] = Query(None),
    svc: InterestRateService = Depends(get_interest_rate_service),
):
    return svc.list_all(instrument=instrument)


@router.get("", response_model=InterestRateResponse)
def get_rate_for_date(
    instrument: InstrumentType = Query(...),
    date: date = Query(...),
    svc: InterestRateService = Depends(get_interest_rate_service),
):
    return svc.get_for_date(instrument, date)

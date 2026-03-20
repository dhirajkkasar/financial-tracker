from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import NotFoundError, ValidationError
from app.models.interest_rate import InstrumentType
from app.repositories.interest_rate_repo import InterestRateRepository
from app.schemas.interest_rate import InterestRateResponse

router = APIRouter(prefix="/interest-rates", tags=["interest-rates"])


@router.get("/all", response_model=list[InterestRateResponse])
def list_all_rates(
    instrument: Optional[InstrumentType] = Query(None),
    db: Session = Depends(get_db),
):
    repo = InterestRateRepository(db)
    rates = repo.list_all(instrument=instrument)
    return rates


@router.get("", response_model=InterestRateResponse)
def get_rate_for_date(
    instrument: InstrumentType = Query(...),
    date: date = Query(...),
    db: Session = Depends(get_db),
):
    repo = InterestRateRepository(db)
    rate = repo.get_applicable(instrument, date)
    if not rate:
        raise NotFoundError(f"No interest rate found for {instrument} on {date}")
    return rate

from datetime import date
from typing import Optional
from app.middleware.error_handler import NotFoundError
from app.models.interest_rate import InstrumentType
from app.repositories.unit_of_work import IUnitOfWorkFactory
from app.schemas.interest_rate import InterestRateResponse


class InterestRateService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def list_all(self, instrument: Optional[InstrumentType] = None) -> list[InterestRateResponse]:
        with self._uow_factory() as uow:
            return uow.interest_rates.list_all(instrument=instrument)

    def get_for_date(self, instrument: InstrumentType, on_date: date) -> InterestRateResponse:
        with self._uow_factory() as uow:
            rate = uow.interest_rates.get_applicable(instrument, on_date)
            if not rate:
                raise NotFoundError(f"No interest rate found for {instrument} on {on_date}")
            return rate

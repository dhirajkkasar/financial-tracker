from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from app.models.interest_rate import InterestRate, InstrumentType


class InterestRateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_applicable(self, instrument: InstrumentType, on_date: date) -> Optional[InterestRate]:
        """Return the interest rate applicable on the given date."""
        return (
            self.db.query(InterestRate)
            .filter(
                InterestRate.instrument == instrument,
                InterestRate.effective_from <= on_date,
            )
            .filter(
                (InterestRate.effective_to == None) | (InterestRate.effective_to >= on_date)
            )
            .order_by(InterestRate.effective_from.desc())
            .first()
        )

    def list_all(self, instrument: Optional[InstrumentType] = None) -> list[InterestRate]:
        q = self.db.query(InterestRate)
        if instrument:
            q = q.filter(InterestRate.instrument == instrument)
        return q.order_by(InterestRate.instrument, InterestRate.effective_from.desc()).all()

    def upsert(self, instrument: InstrumentType, rate_pct: float, effective_from: date, effective_to: Optional[date], fy_label: str) -> InterestRate:
        """Insert or skip if already exists."""
        existing = (
            self.db.query(InterestRate)
            .filter(
                InterestRate.instrument == instrument,
                InterestRate.effective_from == effective_from,
            )
            .first()
        )
        if existing:
            return existing
        new_rate = InterestRate(
            instrument=instrument,
            rate_pct=rate_pct,
            effective_from=effective_from,
            effective_to=effective_to,
            fy_label=fy_label,
        )
        self.db.add(new_rate)
        self.db.commit()
        self.db.refresh(new_rate)
        return new_rate

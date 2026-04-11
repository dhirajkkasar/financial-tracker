import enum
from datetime import date, datetime
from sqlalchemy import Float, Date, String, Enum as SAEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class InstrumentType(str, enum.Enum):
    PPF = "PPF"
    EPF = "EPF"


class InterestRate(Base):
    __tablename__ = "interest_rates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    instrument: Mapped[InstrumentType] = mapped_column(SAEnum(InstrumentType), nullable=False, index=True)
    rate_pct: Mapped[float] = mapped_column(Float, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    fy_label: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        UniqueConstraint("instrument", "effective_from", name="uq_instrument_effective_from"),
    )


# Alias for compatibility with seed script and spec
InterestRateHistory = InterestRate

import enum
from datetime import date, datetime
from sqlalchemy import Integer, Float, Boolean, Date, ForeignKey, Text, String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class FDType(str, enum.Enum):
    FD = "FD"
    RD = "RD"


class CompoundingType(str, enum.Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    HALF_YEARLY = "HALF_YEARLY"
    YEARLY = "YEARLY"
    SIMPLE = "SIMPLE"


class FDDetail(Base):
    __tablename__ = "fd_details"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, unique=True, index=True)
    bank: Mapped[str] = mapped_column(String(100), nullable=False)
    fd_type: Mapped[FDType] = mapped_column(SAEnum(FDType), nullable=False)
    # For FD: lump-sum deposit in paise. For RD: monthly installment in paise.
    principal_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    interest_rate_pct: Mapped[float] = mapped_column(Float, nullable=False)
    compounding: Mapped[CompoundingType] = mapped_column(SAEnum(CompoundingType), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)  # paise
    is_matured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tds_applicable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="fd_detail")

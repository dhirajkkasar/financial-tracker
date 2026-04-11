from datetime import date, datetime
from sqlalchemy import BigInteger, Integer, Float, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CasSnapshot(Base):
    """
    One row per fund per CAS import.
    Stores the closing balance summary line from the CAS PDF.
    Latest row per asset_id is the authoritative source for:
      - closing_units  → used as the unit count (avoids float-sum precision bugs)
      - market_value_inr → current value when snapshot is < 30 days old
      - total_cost_inr   → cost basis for current P&L
    """
    __tablename__ = "cas_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)           # NAV date from CAS
    closing_units: Mapped[float] = mapped_column(Float, nullable=False)
    nav_price_inr: Mapped[int] = mapped_column(BigInteger, nullable=False)   # paise per unit
    market_value_inr: Mapped[int] = mapped_column(BigInteger, nullable=False) # paise total
    total_cost_inr: Mapped[int] = mapped_column(BigInteger, nullable=False)   # paise cost basis
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="cas_snapshots")

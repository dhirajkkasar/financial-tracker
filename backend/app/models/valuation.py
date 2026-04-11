from datetime import date, datetime
from sqlalchemy import BigInteger, Integer, Date, ForeignKey, Text, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Valuation(Base):
    __tablename__ = "valuations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value_inr: Mapped[int] = mapped_column(BigInteger, nullable=False)  # paise
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="valuations")

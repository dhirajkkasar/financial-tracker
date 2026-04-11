import enum
from datetime import date, datetime
from sqlalchemy import BigInteger, String, Integer, Float, Date, ForeignKey, Text, Enum as SAEnum, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class TransactionType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    SIP = "SIP"
    REDEMPTION = "REDEMPTION"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    CONTRIBUTION = "CONTRIBUTION"
    WITHDRAWAL = "WITHDRAWAL"
    SWITCH_IN = "SWITCH_IN"
    SWITCH_OUT = "SWITCH_OUT"
    BONUS = "BONUS"
    SPLIT = "SPLIT"
    VEST = "VEST"
    TRANSFER = "TRANSFER"
    BILLING = "BILLING"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    txn_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    type: Mapped[TransactionType] = mapped_column(SAEnum(TransactionType), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    units: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_per_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    forex_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Stored as signed integer paise; negative = outflow, positive = inflow
    amount_inr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    charges_inr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    lot_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_asset_id_date", "asset_id", "date"),
    )

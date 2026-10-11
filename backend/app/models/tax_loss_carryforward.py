"""Tax loss carry-forward — tracks unabsorbed STCL/LTCL across financial years."""
from datetime import datetime
from sqlalchemy import String, Integer, Float, ForeignKey, Enum as SAEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import enum


class LossType(str, enum.Enum):
    STCL = "STCL"  # Short-term capital loss
    LTCL = "LTCL"  # Long-term capital loss


class TaxLossCarryForward(Base):
    __tablename__ = "tax_loss_carryforwards"
    __table_args__ = (
        UniqueConstraint("member_id", "fy_label", "loss_type", name="uq_carryforward"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False, index=True)
    fy_label: Mapped[str] = mapped_column(String(10), nullable=False)
    loss_type: Mapped[LossType] = mapped_column(SAEnum(LossType), nullable=False)
    amount_inr: Mapped[float] = mapped_column(Float, nullable=False)
    remaining_inr: Mapped[float] = mapped_column(Float, nullable=False)
    expires_fy_label: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

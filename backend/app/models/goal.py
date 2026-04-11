from datetime import date, datetime
from sqlalchemy import BigInteger, Integer, Float, Date, ForeignKey, Text, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_amount_inr: Mapped[int] = mapped_column(BigInteger, nullable=False)  # paise
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    assumed_return_pct: Mapped[float] = mapped_column(Float, default=12.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    allocations: Mapped[list["GoalAllocation"]] = relationship(
        "GoalAllocation", back_populates="goal", cascade="all, delete-orphan"
    )


class GoalAllocation(Base):
    __tablename__ = "goal_allocations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    allocation_pct: Mapped[int] = mapped_column(Integer, nullable=False)

    goal: Mapped["Goal"] = relationship("Goal", back_populates="allocations")
    asset: Mapped["Asset"] = relationship("Asset", back_populates="goal_allocations")

    __table_args__ = (
        UniqueConstraint("goal_id", "asset_id", name="uq_goal_asset"),
    )

from datetime import date, datetime
from typing import Optional
from sqlalchemy import BigInteger, Date, Integer, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("members.id"), nullable=True, index=True)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    total_value_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    breakdown_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("member_id", "date", name="uq_snapshot_member_date"),
    )

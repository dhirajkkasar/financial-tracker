from datetime import date, datetime
from sqlalchemy import Date, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    total_value_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    breakdown_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

from datetime import datetime
from sqlalchemy import Integer, Boolean, ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PriceCache(Base):
    __tablename__ = "price_cache"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, unique=True, index=True)
    price_inr: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="price_cache")

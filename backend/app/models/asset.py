import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Text, Enum as SAEnum, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AssetType(str, enum.Enum):
    STOCK_IN = "STOCK_IN"
    STOCK_US = "STOCK_US"
    MF = "MF"
    FD = "FD"
    RD = "RD"
    PPF = "PPF"
    EPF = "EPF"
    NPS = "NPS"
    GOLD = "GOLD"
    SGB = "SGB"
    REAL_ESTATE = "REAL_ESTATE"
    RSU = "RSU"


class AssetClass(str, enum.Enum):
    EQUITY = "EQUITY"
    DEBT = "DEBT"
    GOLD = "GOLD"
    REAL_ESTATE = "REAL_ESTATE"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("members.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    identifier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mfapi_scheme_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scheme_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    asset_type: Mapped[AssetType] = mapped_column(SAEnum(AssetType), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(SAEnum(AssetClass), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    transactions: Mapped[list] = relationship("Transaction", back_populates="asset", cascade="all, delete-orphan")
    valuations: Mapped[list] = relationship("Valuation", back_populates="asset", cascade="all, delete-orphan")
    price_cache: Mapped["PriceCache | None"] = relationship("PriceCache", back_populates="asset", uselist=False, cascade="all, delete-orphan")
    fd_detail: Mapped["FDDetail | None"] = relationship("FDDetail", back_populates="asset", uselist=False, cascade="all, delete-orphan")
    goal_allocations: Mapped[list] = relationship("GoalAllocation", back_populates="asset", cascade="all, delete-orphan")
    cas_snapshots: Mapped[list] = relationship("CasSnapshot", back_populates="asset", cascade="all, delete-orphan")

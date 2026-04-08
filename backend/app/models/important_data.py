import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Enum as SAEnum, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ImportantDataCategory(str, enum.Enum):
    BANK = "BANK"
    MF_FOLIO = "MF_FOLIO"
    IDENTITY = "IDENTITY"
    INSURANCE = "INSURANCE"
    ACCOUNT = "ACCOUNT"
    OTHER = "OTHER"


class ImportantData(Base):
    __tablename__ = "important_data"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("members.id"), nullable=True, index=True)
    category: Mapped[ImportantDataCategory] = mapped_column(
        SAEnum(ImportantDataCategory), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

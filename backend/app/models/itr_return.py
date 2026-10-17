"""Per-member, per-Assessment-Year ITR return.

The persisted unit of work for one member's filing: the typed ``ReturnInput``
snapshot (so next year can be seeded from it), the assembled draft, and the
generated ITR JSON plus the schema version it validated against.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ItrReturn(Base):
    __tablename__ = "itr_returns"
    __table_args__ = (
        UniqueConstraint("member_id", "ay_label", name="uq_itr_return_member_ay"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id"), nullable=False, index=True
    )
    fy_label: Mapped[str] = mapped_column(String(10), nullable=False)
    ay_label: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    form_type: Mapped[str] = mapped_column(String(10), nullable=False, default="ITR2")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    input_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    schema_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

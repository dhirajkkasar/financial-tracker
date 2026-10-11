"""Member tax profile — per-member, per-FY total income for slab computation."""
from datetime import datetime
from sqlalchemy import String, Integer, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class MemberTaxProfile(Base):
    __tablename__ = "member_tax_profiles"
    __table_args__ = (
        UniqueConstraint("member_id", "fy_label", name="uq_member_tax_profile"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False, index=True)
    fy_label: Mapped[str] = mapped_column(String(10), nullable=False)
    total_income_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

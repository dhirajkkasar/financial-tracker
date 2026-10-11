from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from app.models.member_tax_profile import MemberTaxProfile


class MemberTaxProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, member_id: int, fy_label: str) -> Optional[MemberTaxProfile]:
        return self.db.query(MemberTaxProfile).filter(
            MemberTaxProfile.member_id == member_id,
            MemberTaxProfile.fy_label == fy_label,
        ).first()

    def upsert(self, member_id: int, fy_label: str, total_income_inr: float) -> MemberTaxProfile:
        profile = self.get(member_id, fy_label)
        if profile is None:
            profile = MemberTaxProfile(
                member_id=member_id,
                fy_label=fy_label,
                total_income_inr=total_income_inr,
            )
            self.db.add(profile)
        else:
            profile.total_income_inr = total_income_inr
        self.db.flush()
        self.db.refresh(profile)
        return profile

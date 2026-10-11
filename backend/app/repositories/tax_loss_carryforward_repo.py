from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from app.models.tax_loss_carryforward import TaxLossCarryForward, LossType


class TaxLossCarryForwardRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, member_id: int, fy_label: str, loss_type: LossType) -> Optional[TaxLossCarryForward]:
        return self.db.query(TaxLossCarryForward).filter(
            TaxLossCarryForward.member_id == member_id,
            TaxLossCarryForward.fy_label == fy_label,
            TaxLossCarryForward.loss_type == loss_type,
        ).first()

    def list_by_member(self, member_id: int) -> list[TaxLossCarryForward]:
        return self.db.query(TaxLossCarryForward).filter(
            TaxLossCarryForward.member_id == member_id,
        ).order_by(TaxLossCarryForward.fy_label).all()

    def upsert(
        self,
        member_id: int,
        fy_label: str,
        loss_type: LossType,
        amount_inr: float,
        expires_fy_label: str,
    ) -> TaxLossCarryForward:
        existing = self.get(member_id, fy_label, loss_type)
        if existing is None:
            record = TaxLossCarryForward(
                member_id=member_id,
                fy_label=fy_label,
                loss_type=loss_type,
                amount_inr=amount_inr,
                remaining_inr=amount_inr,
                expires_fy_label=expires_fy_label,
            )
            self.db.add(record)
        else:
            existing.amount_inr += amount_inr
            existing.remaining_inr += amount_inr
            existing.expires_fy_label = expires_fy_label
            record = existing
        self.db.flush()
        self.db.refresh(record)
        return record

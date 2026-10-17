from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.itr_return import ItrReturn


class ItrReturnRepository:
    """Persistence for per-member, per-AY ITR returns."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, return_id: int) -> Optional[ItrReturn]:
        return self.db.query(ItrReturn).filter(ItrReturn.id == return_id).first()

    def get_by_member_ay(self, member_id: int, ay_label: str) -> Optional[ItrReturn]:
        return self.db.query(ItrReturn).filter(
            ItrReturn.member_id == member_id,
            ItrReturn.ay_label == ay_label,
        ).first()

    def list_by_member(self, member_id: int) -> list[ItrReturn]:
        return self.db.query(ItrReturn).filter(
            ItrReturn.member_id == member_id,
        ).order_by(ItrReturn.ay_label).all()

    def get_or_create(self, member_id: int, fy_label: str, ay_label: str) -> ItrReturn:
        existing = self.get_by_member_ay(member_id, ay_label)
        if existing is not None:
            return existing
        record = ItrReturn(member_id=member_id, fy_label=fy_label, ay_label=ay_label)
        self.db.add(record)
        self.db.flush()
        self.db.refresh(record)
        return record

    def save_input(self, return_id: int, input_json: str) -> ItrReturn:
        record = self.get(return_id)
        if record is None:
            raise ValueError(f"ITR return {return_id} not found")
        record.input_json = input_json
        record.updated_at = datetime.utcnow()
        self.db.flush()
        self.db.refresh(record)
        return record

    def save_draft(
        self, return_id: int, draft_json: str, form_type: Optional[str] = None
    ) -> ItrReturn:
        record = self.get(return_id)
        if record is None:
            raise ValueError(f"ITR return {return_id} not found")
        record.draft_json = draft_json
        if form_type:
            record.form_type = form_type
        record.updated_at = datetime.utcnow()
        self.db.flush()
        self.db.refresh(record)
        return record

    def save_output(
        self, return_id: int, output_json: str, schema_version: Optional[str] = None
    ) -> ItrReturn:
        record = self.get(return_id)
        if record is None:
            raise ValueError(f"ITR return {return_id} not found")
        record.output_json = output_json
        record.schema_version = schema_version
        record.status = "generated"
        record.generated_at = datetime.utcnow()
        record.updated_at = datetime.utcnow()
        self.db.flush()
        self.db.refresh(record)
        return record

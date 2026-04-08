from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from app.models.member import Member


class MemberRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Member:
        member = Member(**kwargs)
        self.db.add(member)
        self.db.flush()
        self.db.refresh(member)
        return member

    def get_by_id(self, member_id: int) -> Optional[Member]:
        return self.db.query(Member).filter(Member.id == member_id).first()

    def get_by_pan(self, pan: str) -> Optional[Member]:
        return self.db.query(Member).filter(Member.pan == pan).first()

    def get_default(self) -> Optional[Member]:
        return self.db.query(Member).filter(Member.is_default == True).first()

    def list_all(self) -> list[Member]:
        return self.db.query(Member).order_by(Member.id).all()

from typing import Optional
from sqlalchemy.orm import Session
from app.models.valuation import Valuation


class ValuationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Valuation:
        val = Valuation(**kwargs)
        self.db.add(val)
        self.db.commit()
        self.db.refresh(val)
        return val

    def get_by_id(self, valuation_id: int) -> Optional[Valuation]:
        return self.db.query(Valuation).filter(Valuation.id == valuation_id).first()

    def list_by_asset(self, asset_id: int) -> list[Valuation]:
        return (
            self.db.query(Valuation)
            .filter(Valuation.asset_id == asset_id)
            .order_by(Valuation.date.desc())
            .all()
        )

    def delete(self, val: Valuation) -> None:
        self.db.delete(val)
        self.db.commit()

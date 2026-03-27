from typing import Optional
from sqlalchemy.orm import Session
from app.models.important_data import ImportantData, ImportantDataCategory


class ImportantDataRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> ImportantData:
        obj = ImportantData(**kwargs)
        self.db.add(obj)
        self.db.flush()
        self.db.refresh(obj)
        return obj

    def get_by_id(self, item_id: int) -> Optional[ImportantData]:
        return self.db.query(ImportantData).filter(ImportantData.id == item_id).first()

    def list_all(self, category: Optional[ImportantDataCategory] = None) -> list[ImportantData]:
        q = self.db.query(ImportantData)
        if category is not None:
            q = q.filter(ImportantData.category == category)
        return q.order_by(ImportantData.id).all()

    def update(self, obj: ImportantData, **kwargs) -> ImportantData:
        for key, value in kwargs.items():
            if value is not None:
                setattr(obj, key, value)
        self.db.flush()
        self.db.refresh(obj)
        return obj

    def delete(self, obj: ImportantData) -> None:
        self.db.delete(obj)
        self.db.flush()

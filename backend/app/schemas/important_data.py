from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
import json
from app.models.important_data import ImportantDataCategory


class ImportantDataCreate(BaseModel):
    category: ImportantDataCategory
    label: str
    fields: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class ImportantDataUpdate(BaseModel):
    category: Optional[ImportantDataCategory] = None
    label: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class ImportantDataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: ImportantDataCategory
    label: str
    fields: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    created_at: datetime

    @classmethod
    def from_orm_convert(cls, obj) -> "ImportantDataResponse":
        fields = None
        if obj.fields_json:
            try:
                fields = json.loads(obj.fields_json)
            except Exception:
                fields = None
        return cls(
            id=obj.id,
            category=obj.category,
            label=obj.label,
            fields=fields,
            notes=obj.notes,
            created_at=obj.created_at,
        )

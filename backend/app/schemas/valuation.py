from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ValuationCreate(BaseModel):
    date: date
    value_inr: float  # INR
    source: str = "manual"
    notes: Optional[str] = None


class ValuationUpdate(BaseModel):
    date: Optional[date] = None
    value_inr: Optional[float] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class ValuationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    date: date
    value_inr: float  # returned as INR decimal
    source: str
    notes: Optional[str] = None
    created_at: datetime

    @classmethod
    def from_orm_convert(cls, obj) -> "ValuationResponse":
        return cls(
            id=obj.id,
            asset_id=obj.asset_id,
            date=obj.date,
            value_inr=obj.value_inr / 100.0,
            source=obj.source,
            notes=obj.notes,
            created_at=obj.created_at,
        )

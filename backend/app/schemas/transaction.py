from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from app.models.transaction import TransactionType


class TransactionCreate(BaseModel):
    type: TransactionType
    date: date
    units: Optional[float] = None
    price_per_unit: Optional[float] = None
    forex_rate: Optional[float] = None
    # Accept INR decimal; will be stored as paise
    amount_inr: float  # INR
    charges_inr: float = 0.0  # INR
    txn_id: Optional[str] = None  # if provided by caller (e.g. import); auto-generated if None
    lot_id: Optional[str] = None
    notes: Optional[str] = None


class TransactionUpdate(BaseModel):
    type: Optional[TransactionType] = None
    date: Optional[date] = None
    units: Optional[float] = None
    price_per_unit: Optional[float] = None
    forex_rate: Optional[float] = None
    amount_inr: Optional[float] = None
    charges_inr: Optional[float] = None
    notes: Optional[str] = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    txn_id: str
    asset_id: int
    type: TransactionType
    date: date
    units: Optional[float] = None
    price_per_unit: Optional[float] = None
    forex_rate: Optional[float] = None
    amount_inr: float  # returned as INR decimal
    charges_inr: float  # returned as INR decimal
    lot_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    @classmethod
    def from_orm_convert(cls, obj) -> "TransactionResponse":
        """Convert paise amounts to INR."""
        data = {
            "id": obj.id,
            "txn_id": obj.txn_id,
            "asset_id": obj.asset_id,
            "type": obj.type,
            "date": obj.date,
            "units": obj.units,
            "price_per_unit": obj.price_per_unit,
            "forex_rate": obj.forex_rate,
            "amount_inr": obj.amount_inr / 100.0,
            "charges_inr": obj.charges_inr / 100.0,
            "lot_id": obj.lot_id,
            "notes": obj.notes,
            "created_at": obj.created_at,
        }
        return cls(**data)

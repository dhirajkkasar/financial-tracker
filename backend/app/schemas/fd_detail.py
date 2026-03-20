from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.fd_detail import FDType, CompoundingType


class FDDetailCreate(BaseModel):
    bank: str
    fd_type: FDType
    # For FD: lump-sum principal in INR. For RD: monthly installment in INR.
    principal_amount: float  # INR
    interest_rate_pct: float
    compounding: CompoundingType
    start_date: date
    maturity_date: date
    maturity_amount: Optional[float] = None  # INR; null means auto-compute
    is_matured: bool = False
    tds_applicable: bool = True
    notes: Optional[str] = None


class FDDetailUpdate(BaseModel):
    bank: Optional[str] = None
    fd_type: Optional[FDType] = None
    principal_amount: Optional[float] = None
    interest_rate_pct: Optional[float] = None
    compounding: Optional[CompoundingType] = None
    start_date: Optional[date] = None
    maturity_date: Optional[date] = None
    maturity_amount: Optional[float] = None
    is_matured: Optional[bool] = None
    tds_applicable: Optional[bool] = None
    notes: Optional[str] = None


class FDDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    bank: str
    fd_type: FDType
    principal_amount: float  # INR
    interest_rate_pct: float
    compounding: CompoundingType
    start_date: date
    maturity_date: date
    maturity_amount: Optional[float] = None  # INR
    is_matured: bool
    tds_applicable: bool
    notes: Optional[str] = None
    created_at: datetime

    @classmethod
    def from_orm_convert(cls, obj) -> "FDDetailResponse":
        return cls(
            id=obj.id,
            asset_id=obj.asset_id,
            bank=obj.bank,
            fd_type=obj.fd_type,
            principal_amount=obj.principal_amount / 100.0,
            interest_rate_pct=obj.interest_rate_pct,
            compounding=obj.compounding,
            start_date=obj.start_date,
            maturity_date=obj.maturity_date,
            maturity_amount=obj.maturity_amount / 100.0 if obj.maturity_amount is not None else None,
            is_matured=obj.is_matured,
            tds_applicable=obj.tds_applicable,
            notes=obj.notes,
            created_at=obj.created_at,
        )

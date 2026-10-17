from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.itr_models import ReturnInput


class ItrPrepareRequest(BaseModel):
    member_id: int
    fy: str


class ItrFiscalYearsResponse(BaseModel):
    fiscal_years: list[str]


class ItrReturnSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    fy_label: str
    ay_label: str
    form_type: str
    status: str
    schema_version: Optional[str] = None
    generated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ItrReturnListResponse(BaseModel):
    returns: list[ItrReturnSummary]


class ItrReturnDetail(ItrReturnSummary):
    input: ReturnInput


class ItrForm16UploadResponse(BaseModel):
    input: ReturnInput
    warnings: list[str]

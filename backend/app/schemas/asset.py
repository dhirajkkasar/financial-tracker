from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.asset import AssetType, AssetClass


class GoalRef(BaseModel):
    id: int
    name: str


class AssetCreate(BaseModel):
    name: str
    identifier: Optional[str] = None
    mfapi_scheme_code: Optional[str] = None
    asset_type: AssetType
    asset_class: AssetClass
    currency: str = "INR"
    is_active: bool = True
    notes: Optional[str] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    identifier: Optional[str] = None
    mfapi_scheme_code: Optional[str] = None
    asset_type: Optional[AssetType] = None
    asset_class: Optional[AssetClass] = None
    currency: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    identifier: Optional[str] = None
    mfapi_scheme_code: Optional[str] = None
    asset_type: AssetType
    asset_class: AssetClass
    currency: str
    is_active: bool
    notes: Optional[str] = None
    scheme_category: Optional[str] = None
    created_at: datetime
    # Goal tracking (populated only by GET /assets/{id})
    goals: list[GoalRef] = []

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class GoalCreate(BaseModel):
    name: str
    target_amount_inr: float  # INR
    target_date: date
    notes: Optional[str] = None


class GoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount_inr: Optional[float] = None
    target_date: Optional[date] = None
    notes: Optional[str] = None


class GoalAllocationCreate(BaseModel):
    asset_id: int
    allocation_pct: int


class GoalAllocationUpdate(BaseModel):
    allocation_pct: int


class GoalAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_id: int
    asset_id: int
    allocation_pct: int


class GoalAllocationWithAsset(BaseModel):
    id: int
    goal_id: int
    asset_id: int
    asset_name: str
    asset_type: str
    allocation_pct: int
    current_value_inr: Optional[float] = None
    value_toward_goal: Optional[float] = None


class GoalResponse(BaseModel):
    id: int
    name: str
    target_amount_inr: float  # INR
    target_date: date
    notes: Optional[str] = None
    created_at: datetime
    current_value_inr: float = 0.0
    remaining_inr: float = 0.0
    progress_pct: float = 0.0
    allocations: List[GoalAllocationWithAsset] = []

import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import NotFoundError, ValidationError
from app.models.goal import GoalAllocation
from app.repositories.asset_repo import AssetRepository
from app.repositories.goal_repo import GoalRepository
from app.schemas.goal import (
    GoalCreate, GoalUpdate, GoalResponse,
    GoalAllocationCreate, GoalAllocationUpdate, GoalAllocationResponse,
    GoalAllocationWithAsset,
)
from app.services.returns.portfolio_returns_service import PortfolioReturnsService
from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/goals", tags=["goals"])


def _validate_pct(pct: int):
    if pct <= 0 or pct > 100 or pct % 10 != 0:
        raise ValidationError(
            f"allocation_pct must be a positive multiple of 10 (10–100), got {pct}"
        )


def _sum_allocations(db: Session, asset_id: int, exclude_allocation_id: int | None = None) -> int:
    q = db.query(GoalAllocation).filter(GoalAllocation.asset_id == asset_id)
    if exclude_allocation_id is not None:
        q = q.filter(GoalAllocation.id != exclude_allocation_id)
    return sum(a.allocation_pct for a in q.all())


def _validate_create_sum(db: Session, asset_id: int, new_pct: int):
    """On CREATE: new total must not exceed 100."""
    current = _sum_allocations(db, asset_id)
    if current + new_pct > 100:
        raise ValidationError(
            f"Allocation for asset {asset_id} would exceed 100% "
            f"(current={current}%, adding={new_pct}%)"
        )


def _validate_final_sum(db: Session, asset_id: int, exclude_allocation_id: int | None = None):
    """On UPDATE/DELETE: final total must be exactly 100 or 0 (fully unlinked)."""
    total = _sum_allocations(db, asset_id, exclude_allocation_id)
    if total != 0 and total != 100:
        raise ValidationError(
            f"Allocations for asset {asset_id} must sum to exactly 100% or 0% "
            f"(got {total}% after change). Adjust other goal allocations first."
        )


def _compute_goal_response(goal, db: Session) -> GoalResponse:
    """Build GoalResponse with live progress fields."""
    strategy_registry = DefaultReturnsStrategyRegistry()
    svc = PortfolioReturnsService(db, strategy_registry)

    allocs_out: list[GoalAllocationWithAsset] = []
    total_current = 0.0

    for alloc in goal.allocations:
        asset = alloc.asset
        try:
            ret = svc.get_asset_returns(alloc.asset_id)
            cv = ret.get("current_value") or 0.0
        except Exception:
            cv = 0.0

        value_toward = cv * alloc.allocation_pct / 100.0
        total_current += value_toward

        allocs_out.append(GoalAllocationWithAsset(
            id=alloc.id,
            goal_id=alloc.goal_id,
            asset_id=alloc.asset_id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            allocation_pct=alloc.allocation_pct,
            current_value_inr=cv,
            value_toward_goal=value_toward,
        ))

    target = goal.target_amount_inr / 100.0
    remaining = max(0.0, target - total_current)
    progress_pct = min(100.0, (total_current / target * 100.0) if target > 0 else 0.0)

    return GoalResponse(
        id=goal.id,
        name=goal.name,
        target_amount_inr=target,
        target_date=goal.target_date,
        notes=goal.notes,
        created_at=goal.created_at,
        current_value_inr=round(total_current, 2),
        remaining_inr=round(remaining, 2),
        progress_pct=round(progress_pct, 2),
        allocations=allocs_out,
    )


@router.get("", response_model=list[GoalResponse])
def list_goals(db: Session = Depends(get_db)):
    repo = GoalRepository(db)
    goals = repo.list_all()
    return [_compute_goal_response(g, db) for g in goals]


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalCreate, db: Session = Depends(get_db)):
    repo = GoalRepository(db)
    data = body.model_dump()
    data["target_amount_inr"] = round(data["target_amount_inr"] * 100)
    # assumed_return_pct not used for display but keep default in model
    goal = repo.create(**data)
    return _compute_goal_response(goal, db)


@router.get("/{goal_id}", response_model=GoalResponse)
def get_goal(goal_id: int, db: Session = Depends(get_db)):
    repo = GoalRepository(db)
    goal = repo.get_by_id(goal_id)
    if not goal:
        raise NotFoundError(f"Goal {goal_id} not found")
    return _compute_goal_response(goal, db)


@router.put("/{goal_id}", response_model=GoalResponse)
def update_goal(goal_id: int, body: GoalUpdate, db: Session = Depends(get_db)):
    repo = GoalRepository(db)
    goal = repo.get_by_id(goal_id)
    if not goal:
        raise NotFoundError(f"Goal {goal_id} not found")
    update_data = body.model_dump(exclude_none=True)
    if "target_amount_inr" in update_data:
        update_data["target_amount_inr"] = round(update_data["target_amount_inr"] * 100)
    goal = repo.update(goal, **update_data)
    return _compute_goal_response(goal, db)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    repo = GoalRepository(db)
    goal = repo.get_by_id(goal_id)
    if not goal:
        raise NotFoundError(f"Goal {goal_id} not found")
    repo.delete(goal)


# ---------- Allocation sub-resource ----------

@router.get("/{goal_id}/allocations", response_model=list[GoalAllocationResponse])
def list_allocations(goal_id: int, db: Session = Depends(get_db)):
    repo = GoalRepository(db)
    if not repo.get_by_id(goal_id):
        raise NotFoundError(f"Goal {goal_id} not found")
    return db.query(GoalAllocation).filter(GoalAllocation.goal_id == goal_id).all()


@router.post("/{goal_id}/allocations", response_model=GoalAllocationResponse,
             status_code=status.HTTP_201_CREATED)
def add_allocation(goal_id: int, body: GoalAllocationCreate, db: Session = Depends(get_db)):
    repo = GoalRepository(db)
    if not repo.get_by_id(goal_id):
        raise NotFoundError(f"Goal {goal_id} not found")
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(body.asset_id):
        raise NotFoundError(f"Asset {body.asset_id} not found")

    _validate_pct(body.allocation_pct)
    _validate_create_sum(db, body.asset_id, body.allocation_pct)

    return repo.create_allocation(
        goal_id=goal_id,
        asset_id=body.asset_id,
        allocation_pct=body.allocation_pct,
    )


@router.put("/{goal_id}/allocations/{allocation_id}", response_model=GoalAllocationResponse)
def update_allocation(goal_id: int, allocation_id: int, body: GoalAllocationUpdate,
                      db: Session = Depends(get_db)):
    repo = GoalRepository(db)
    if not repo.get_by_id(goal_id):
        raise NotFoundError(f"Goal {goal_id} not found")
    alloc = repo.get_allocation(allocation_id)
    if not alloc or alloc.goal_id != goal_id:
        raise NotFoundError(f"Allocation {allocation_id} not found")

    _validate_pct(body.allocation_pct)
    # projected total = sum of all OTHER allocations + the new value
    others = _sum_allocations(db, alloc.asset_id, exclude_allocation_id=allocation_id)
    projected = others + body.allocation_pct
    if projected != 0 and projected != 100:
        raise ValidationError(
            f"Allocations for asset {alloc.asset_id} must sum to exactly 100% or 0% "
            f"(would be {projected}% after change)."
        )

    return repo.update_allocation(alloc, body.allocation_pct)


@router.delete("/{goal_id}/allocations/{allocation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_allocation(goal_id: int, allocation_id: int, db: Session = Depends(get_db)):
    repo = GoalRepository(db)
    if not repo.get_by_id(goal_id):
        raise NotFoundError(f"Goal {goal_id} not found")
    alloc = repo.get_allocation(allocation_id)
    if not alloc or alloc.goal_id != goal_id:
        raise NotFoundError(f"Allocation {allocation_id} not found")
    _validate_final_sum(db, alloc.asset_id, exclude_allocation_id=allocation_id)
    repo.delete_allocation(alloc)

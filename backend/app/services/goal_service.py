import logging
from app.middleware.error_handler import NotFoundError, ValidationError
from app.models.goal import GoalAllocation
from app.repositories.unit_of_work import IUnitOfWorkFactory
from app.schemas.goal import (
    GoalCreate, GoalUpdate, GoalResponse,
    GoalAllocationCreate, GoalAllocationUpdate,
    GoalAllocationWithAsset,
)
from app.services.returns.portfolio_returns_service import PortfolioReturnsService

logger = logging.getLogger(__name__)


class GoalService:
    def __init__(self, uow_factory: IUnitOfWorkFactory, returns_service: PortfolioReturnsService):
        self._uow_factory = uow_factory
        self._returns_service = returns_service

    def _validate_pct(self, pct: int):
        if pct <= 0 or pct > 100 or pct % 10 != 0:
            raise ValidationError(
                f"allocation_pct must be a positive multiple of 10 (10–100), got {pct}"
            )

    def _sum_allocations(self, uow, asset_id: int, exclude_allocation_id: int | None = None) -> int:
        allocs = uow.goals.list_allocations_for_asset(asset_id)
        return sum(
            a.allocation_pct for a in allocs
            if exclude_allocation_id is None or a.id != exclude_allocation_id
        )

    def _build_goal_response(self, goal, uow) -> GoalResponse:
        allocs_out: list[GoalAllocationWithAsset] = []
        total_current = 0.0

        for alloc in goal.allocations:
            asset = alloc.asset
            try:
                ret = self._returns_service.get_asset_returns(alloc.asset_id)
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

    def list_goals(self) -> list[GoalResponse]:
        with self._uow_factory() as uow:
            goals = uow.goals.list_all()
            return [self._build_goal_response(g, uow) for g in goals]

    def create_goal(self, body: GoalCreate) -> GoalResponse:
        with self._uow_factory() as uow:
            data = body.model_dump()
            data["target_amount_inr"] = round(data["target_amount_inr"] * 100)
            goal = uow.goals.create(**data)
            return self._build_goal_response(goal, uow)

    def get_goal(self, goal_id: int) -> GoalResponse:
        with self._uow_factory() as uow:
            goal = uow.goals.get_by_id(goal_id)
            if not goal:
                raise NotFoundError(f"Goal {goal_id} not found")
            return self._build_goal_response(goal, uow)

    def update_goal(self, goal_id: int, body: GoalUpdate) -> GoalResponse:
        with self._uow_factory() as uow:
            goal = uow.goals.get_by_id(goal_id)
            if not goal:
                raise NotFoundError(f"Goal {goal_id} not found")
            update_data = body.model_dump(exclude_none=True)
            if "target_amount_inr" in update_data:
                update_data["target_amount_inr"] = round(update_data["target_amount_inr"] * 100)
            goal = uow.goals.update(goal, **update_data)
            return self._build_goal_response(goal, uow)

    def delete_goal(self, goal_id: int) -> None:
        with self._uow_factory() as uow:
            goal = uow.goals.get_by_id(goal_id)
            if not goal:
                raise NotFoundError(f"Goal {goal_id} not found")
            uow.goals.delete(goal)

    def list_allocations(self, goal_id: int) -> list[GoalAllocation]:
        with self._uow_factory() as uow:
            goal = uow.goals.get_by_id(goal_id)
            if not goal:
                raise NotFoundError(f"Goal {goal_id} not found")
            return list(goal.allocations)

    def add_allocation(self, goal_id: int, body: GoalAllocationCreate) -> GoalAllocation:
        with self._uow_factory() as uow:
            if not uow.goals.get_by_id(goal_id):
                raise NotFoundError(f"Goal {goal_id} not found")
            if not uow.assets.get_by_id(body.asset_id):
                raise NotFoundError(f"Asset {body.asset_id} not found")
            self._validate_pct(body.allocation_pct)
            current = self._sum_allocations(uow, body.asset_id)
            if current + body.allocation_pct > 100:
                raise ValidationError(
                    f"Allocation for asset {body.asset_id} would exceed 100% "
                    f"(current={current}%, adding={body.allocation_pct}%)"
                )
            return uow.goals.create_allocation(
                goal_id=goal_id,
                asset_id=body.asset_id,
                allocation_pct=body.allocation_pct,
            )

    def update_allocation(
        self, goal_id: int, allocation_id: int, body: GoalAllocationUpdate
    ) -> GoalAllocation:
        with self._uow_factory() as uow:
            if not uow.goals.get_by_id(goal_id):
                raise NotFoundError(f"Goal {goal_id} not found")
            alloc = uow.goals.get_allocation(allocation_id)
            if not alloc or alloc.goal_id != goal_id:
                raise NotFoundError(f"Allocation {allocation_id} not found")
            self._validate_pct(body.allocation_pct)
            others = self._sum_allocations(uow, alloc.asset_id, exclude_allocation_id=allocation_id)
            projected = others + body.allocation_pct
            if projected != 0 and projected != 100:
                raise ValidationError(
                    f"Allocations for asset {alloc.asset_id} must sum to exactly 100% or 0% "
                    f"(would be {projected}% after change)."
                )
            return uow.goals.update_allocation(alloc, body.allocation_pct)

    def delete_allocation(self, goal_id: int, allocation_id: int) -> None:
        with self._uow_factory() as uow:
            if not uow.goals.get_by_id(goal_id):
                raise NotFoundError(f"Goal {goal_id} not found")
            alloc = uow.goals.get_allocation(allocation_id)
            if not alloc or alloc.goal_id != goal_id:
                raise NotFoundError(f"Allocation {allocation_id} not found")
            total = self._sum_allocations(uow, alloc.asset_id, exclude_allocation_id=allocation_id)
            if total != 0 and total != 100:
                raise ValidationError(
                    f"Allocations for asset {alloc.asset_id} must sum to exactly 100% or 0% "
                    f"(got {total}% after change). Adjust other goal allocations first."
                )
            uow.goals.delete_allocation(alloc)

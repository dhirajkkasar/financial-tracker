from typing import Optional
from sqlalchemy.orm import Session
from app.models.goal import Goal, GoalAllocation


class GoalRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Goal:
        goal = Goal(**kwargs)
        self.db.add(goal)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def get_by_id(self, goal_id: int) -> Optional[Goal]:
        return self.db.query(Goal).filter(Goal.id == goal_id).first()

    def list_all(self) -> list[Goal]:
        return self.db.query(Goal).order_by(Goal.id).all()

    def update(self, goal: Goal, **kwargs) -> Goal:
        for key, value in kwargs.items():
            if value is not None:
                setattr(goal, key, value)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def delete(self, goal: Goal) -> None:
        self.db.delete(goal)
        self.db.commit()

    # Allocation methods
    def create_allocation(self, **kwargs) -> GoalAllocation:
        alloc = GoalAllocation(**kwargs)
        self.db.add(alloc)
        self.db.commit()
        self.db.refresh(alloc)
        return alloc

    def get_allocation(self, allocation_id: int) -> Optional[GoalAllocation]:
        return self.db.query(GoalAllocation).filter(GoalAllocation.id == allocation_id).first()

    def get_allocation_by_goal_asset(self, goal_id: int, asset_id: int) -> Optional[GoalAllocation]:
        return (
            self.db.query(GoalAllocation)
            .filter(GoalAllocation.goal_id == goal_id, GoalAllocation.asset_id == asset_id)
            .first()
        )

    def list_allocations_for_asset(self, asset_id: int) -> list[GoalAllocation]:
        """Return all allocations for an asset across all goals."""
        return self.db.query(GoalAllocation).filter(GoalAllocation.asset_id == asset_id).all()

    def update_allocation(self, alloc: GoalAllocation, allocation_pct: int) -> GoalAllocation:
        alloc.allocation_pct = allocation_pct
        self.db.commit()
        self.db.refresh(alloc)
        return alloc

    def delete_allocation(self, alloc: GoalAllocation) -> None:
        self.db.delete(alloc)
        self.db.commit()

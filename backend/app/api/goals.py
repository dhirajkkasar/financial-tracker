from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_goal_service
from app.schemas.goal import (
    GoalCreate, GoalUpdate, GoalResponse,
    GoalAllocationCreate, GoalAllocationUpdate, GoalAllocationResponse,
)
from app.services.goal_service import GoalService

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=list[GoalResponse])
def list_goals(svc: GoalService = Depends(get_goal_service)):
    return svc.list_goals()


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalCreate, svc: GoalService = Depends(get_goal_service)):
    return svc.create_goal(body)


@router.get("/{goal_id}", response_model=GoalResponse)
def get_goal(goal_id: int, svc: GoalService = Depends(get_goal_service)):
    return svc.get_goal(goal_id)


@router.put("/{goal_id}", response_model=GoalResponse)
def update_goal(goal_id: int, body: GoalUpdate, svc: GoalService = Depends(get_goal_service)):
    return svc.update_goal(goal_id, body)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, svc: GoalService = Depends(get_goal_service)):
    svc.delete_goal(goal_id)


@router.get("/{goal_id}/allocations", response_model=list[GoalAllocationResponse])
def list_allocations(goal_id: int, svc: GoalService = Depends(get_goal_service)):
    return svc.list_allocations(goal_id)


@router.post("/{goal_id}/allocations", response_model=GoalAllocationResponse,
             status_code=status.HTTP_201_CREATED)
def add_allocation(goal_id: int, body: GoalAllocationCreate, svc: GoalService = Depends(get_goal_service)):
    return svc.add_allocation(goal_id, body)


@router.put("/{goal_id}/allocations/{allocation_id}", response_model=GoalAllocationResponse)
def update_allocation(
    goal_id: int, allocation_id: int, body: GoalAllocationUpdate,
    svc: GoalService = Depends(get_goal_service),
):
    return svc.update_allocation(goal_id, allocation_id, body)


@router.delete("/{goal_id}/allocations/{allocation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_allocation(
    goal_id: int, allocation_id: int,
    svc: GoalService = Depends(get_goal_service),
):
    svc.delete_allocation(goal_id, allocation_id)

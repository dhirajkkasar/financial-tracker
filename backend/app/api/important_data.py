from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_important_data_service
from app.models.important_data import ImportantDataCategory
from app.schemas.important_data import ImportantDataCreate, ImportantDataUpdate, ImportantDataResponse
from app.services.important_data_service import ImportantDataService

router = APIRouter(prefix="/important-data", tags=["important-data"])


@router.get("", response_model=list[ImportantDataResponse])
def list_important_data(
    category: Optional[ImportantDataCategory] = Query(None),
    member_ids: Optional[str] = Query(None, description="Comma-separated member IDs"),
    svc: ImportantDataService = Depends(get_important_data_service),
):
    parsed_member_ids = [int(x.strip()) for x in member_ids.split(",") if x.strip()] if member_ids else None
    return svc.list_all(category=category, member_ids=parsed_member_ids)


@router.post("", response_model=ImportantDataResponse, status_code=status.HTTP_201_CREATED)
def create_important_data(body: ImportantDataCreate, svc: ImportantDataService = Depends(get_important_data_service)):
    return svc.create(body)


@router.get("/{item_id}", response_model=ImportantDataResponse)
def get_important_data(item_id: int, svc: ImportantDataService = Depends(get_important_data_service)):
    return svc.get_by_id(item_id)


@router.put("/{item_id}", response_model=ImportantDataResponse)
def update_important_data(item_id: int, body: ImportantDataUpdate, svc: ImportantDataService = Depends(get_important_data_service)):
    return svc.update(item_id, body)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_important_data(item_id: int, svc: ImportantDataService = Depends(get_important_data_service)):
    svc.delete(item_id)

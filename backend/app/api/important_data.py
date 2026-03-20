import json
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import NotFoundError
from app.models.important_data import ImportantDataCategory
from app.repositories.important_data_repo import ImportantDataRepository
from app.schemas.important_data import ImportantDataCreate, ImportantDataUpdate, ImportantDataResponse

router = APIRouter(prefix="/important-data", tags=["important-data"])


@router.get("", response_model=list[ImportantDataResponse])
def list_important_data(
    category: Optional[ImportantDataCategory] = Query(None),
    db: Session = Depends(get_db),
):
    repo = ImportantDataRepository(db)
    items = repo.list_all(category=category)
    return [ImportantDataResponse.from_orm_convert(i) for i in items]


@router.post("", response_model=ImportantDataResponse, status_code=status.HTTP_201_CREATED)
def create_important_data(body: ImportantDataCreate, db: Session = Depends(get_db)):
    repo = ImportantDataRepository(db)
    data = body.model_dump()
    fields = data.pop("fields", None)
    data["fields_json"] = json.dumps(fields) if fields is not None else None
    obj = repo.create(**data)
    return ImportantDataResponse.from_orm_convert(obj)


@router.get("/{item_id}", response_model=ImportantDataResponse)
def get_important_data(item_id: int, db: Session = Depends(get_db)):
    repo = ImportantDataRepository(db)
    obj = repo.get_by_id(item_id)
    if not obj:
        raise NotFoundError(f"ImportantData {item_id} not found")
    return ImportantDataResponse.from_orm_convert(obj)


@router.put("/{item_id}", response_model=ImportantDataResponse)
def update_important_data(item_id: int, body: ImportantDataUpdate, db: Session = Depends(get_db)):
    repo = ImportantDataRepository(db)
    obj = repo.get_by_id(item_id)
    if not obj:
        raise NotFoundError(f"ImportantData {item_id} not found")
    update_data = body.model_dump(exclude_none=True)
    if "fields" in update_data:
        update_data["fields_json"] = json.dumps(update_data.pop("fields"))
    repo.update(obj, **update_data)
    return ImportantDataResponse.from_orm_convert(obj)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_important_data(item_id: int, db: Session = Depends(get_db)):
    repo = ImportantDataRepository(db)
    obj = repo.get_by_id(item_id)
    if not obj:
        raise NotFoundError(f"ImportantData {item_id} not found")
    repo.delete(obj)

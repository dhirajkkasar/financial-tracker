import json
from typing import Optional
from app.middleware.error_handler import NotFoundError
from app.models.important_data import ImportantDataCategory
from app.repositories.unit_of_work import IUnitOfWorkFactory
from app.schemas.important_data import ImportantDataCreate, ImportantDataUpdate, ImportantDataResponse


class ImportantDataService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def list_all(self, category: Optional[ImportantDataCategory] = None) -> list[ImportantDataResponse]:
        with self._uow_factory() as uow:
            items = uow.important_data.list_all(category=category)
            return [ImportantDataResponse.from_orm_convert(i) for i in items]

    def create(self, body: ImportantDataCreate) -> ImportantDataResponse:
        with self._uow_factory() as uow:
            data = body.model_dump()
            fields = data.pop("fields", None)
            data["fields_json"] = json.dumps(fields) if fields is not None else None
            obj = uow.important_data.create(**data)
            return ImportantDataResponse.from_orm_convert(obj)

    def get_by_id(self, item_id: int) -> ImportantDataResponse:
        with self._uow_factory() as uow:
            obj = uow.important_data.get_by_id(item_id)
            if not obj:
                raise NotFoundError(f"ImportantData {item_id} not found")
            return ImportantDataResponse.from_orm_convert(obj)

    def update(self, item_id: int, body: ImportantDataUpdate) -> ImportantDataResponse:
        with self._uow_factory() as uow:
            obj = uow.important_data.get_by_id(item_id)
            if not obj:
                raise NotFoundError(f"ImportantData {item_id} not found")
            update_data = body.model_dump(exclude_none=True)
            if "fields" in update_data:
                update_data["fields_json"] = json.dumps(update_data.pop("fields"))
            uow.important_data.update(obj, **update_data)
            return ImportantDataResponse.from_orm_convert(obj)

    def delete(self, item_id: int) -> None:
        with self._uow_factory() as uow:
            obj = uow.important_data.get_by_id(item_id)
            if not obj:
                raise NotFoundError(f"ImportantData {item_id} not found")
            uow.important_data.delete(obj)

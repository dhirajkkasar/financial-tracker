from app.middleware.error_handler import NotFoundError, DuplicateError
from app.repositories.unit_of_work import IUnitOfWorkFactory
from app.schemas.fd_detail import FDDetailCreate, FDDetailUpdate, FDDetailResponse


class FDDetailService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def get(self, asset_id: int) -> FDDetailResponse:
        with self._uow_factory() as uow:
            if not uow.assets.get_by_id(asset_id):
                raise NotFoundError(f"Asset {asset_id} not found")
            fd = uow.fd.get_by_asset_id(asset_id)
            if not fd:
                raise NotFoundError(f"FD detail for asset {asset_id} not found")
            return FDDetailResponse.from_orm_convert(fd)

    def create(self, asset_id: int, body: FDDetailCreate) -> FDDetailResponse:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            if uow.fd.get_by_asset_id(asset_id):
                raise DuplicateError(f"FD detail already exists for asset {asset_id}")

            data = body.model_dump()
            data["principal_amount"] = round(data["principal_amount"] * 100)
            if data.get("maturity_amount") is not None:
                data["maturity_amount"] = round(data["maturity_amount"] * 100)
            data["asset_id"] = asset_id

            fd = uow.fd.create(**data)

            if body.is_matured:
                asset.is_active = False

            return FDDetailResponse.from_orm_convert(fd)

    def update(self, asset_id: int, body: FDDetailUpdate) -> FDDetailResponse:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            fd = uow.fd.get_by_asset_id(asset_id)
            if not fd:
                raise NotFoundError(f"FD detail for asset {asset_id} not found")

            update_data = body.model_dump(exclude_none=True)
            if "principal_amount" in update_data:
                update_data["principal_amount"] = round(update_data["principal_amount"] * 100)
            if "maturity_amount" in update_data:
                update_data["maturity_amount"] = round(update_data["maturity_amount"] * 100)

            fd = uow.fd.update(fd, **update_data)

            if body.is_matured is not None:
                asset.is_active = not body.is_matured

            return FDDetailResponse.from_orm_convert(fd)

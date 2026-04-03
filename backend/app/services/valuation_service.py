from app.middleware.error_handler import NotFoundError
from app.repositories.unit_of_work import IUnitOfWorkFactory
from app.schemas.valuation import ValuationCreate, ValuationResponse


class ValuationService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def list(self, asset_id: int) -> list[ValuationResponse]:
        with self._uow_factory() as uow:
            if not uow.assets.get_by_id(asset_id):
                raise NotFoundError(f"Asset {asset_id} not found")
            valuations = uow.valuations.list_by_asset(asset_id)
            return [ValuationResponse.from_orm_convert(v) for v in valuations]

    def create(self, asset_id: int, body: ValuationCreate) -> ValuationResponse:
        with self._uow_factory() as uow:
            if not uow.assets.get_by_id(asset_id):
                raise NotFoundError(f"Asset {asset_id} not found")
            data = body.model_dump()
            data["value_inr"] = round(data["value_inr"] * 100)
            data["asset_id"] = asset_id
            val = uow.valuations.create(**data)
            return ValuationResponse.from_orm_convert(val)

    def delete(self, asset_id: int, valuation_id: int) -> None:
        with self._uow_factory() as uow:
            if not uow.assets.get_by_id(asset_id):
                raise NotFoundError(f"Asset {asset_id} not found")
            val = uow.valuations.get_by_id(valuation_id)
            if not val or val.asset_id != asset_id:
                raise NotFoundError(f"Valuation {valuation_id} not found")
            uow.valuations.delete(val)

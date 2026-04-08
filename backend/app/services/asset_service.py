"""
AssetService — thin wrapper over AssetRepository + GoalRepository.
All business logic for asset CRUD lives here; routes call service methods only.
"""
from __future__ import annotations

from typing import Optional

from app.middleware.error_handler import NotFoundError
from app.models.asset import Asset, AssetType, AssetClass
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory
from app.schemas.asset import AssetCreate, AssetUpdate


class AssetService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def create(self, body: AssetCreate) -> Asset:
        with self._uow_factory() as uow:
            return uow.assets.create(**body.model_dump())

    def list(
        self,
        asset_type: Optional[AssetType] = None,
        asset_class: Optional[AssetClass] = None,
        active: Optional[bool] = None,
        member_ids: Optional[list[int]] = None,
    ) -> list[Asset]:
        with self._uow_factory() as uow:
            return uow.assets.list(asset_type=asset_type, asset_class=asset_class, active=active, member_ids=member_ids)

    def get_by_id(self, asset_id: int) -> Asset:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            allocations = uow.goals.list_allocations_for_asset(asset_id)
            asset.goals = [{"id": a.goal.id, "name": a.goal.name} for a in allocations]
            return asset

    def update(self, asset_id: int, body: AssetUpdate) -> Asset:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            return uow.assets.update(asset, **body.model_dump(exclude_none=True))

    def delete(self, asset_id: int) -> Asset:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            return uow.assets.soft_delete(asset)

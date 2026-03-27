"""
ReturnsService — thin coordinator. Delegates all computation to the strategy registry.
"""
from __future__ import annotations

from app.middleware.error_handler import NotFoundError
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory
from app.schemas.responses.returns import AssetReturnsResponse, LotComputedResponse, LotsPageResponse
from app.services.returns.strategies.registry import IReturnsStrategyRegistry


class ReturnsService:
    def __init__(
        self,
        uow_factory: IUnitOfWorkFactory,
        strategy_registry: IReturnsStrategyRegistry,
    ):
        self._uow_factory = uow_factory
        self._registry = strategy_registry

    def get_asset_returns(self, asset_id: int) -> AssetReturnsResponse:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            strategy = self._registry.get(asset.asset_type.value)
            return strategy.compute(asset, uow)

    def get_all_returns(self) -> list[AssetReturnsResponse]:
        with self._uow_factory() as uow:
            assets = uow.assets.list(active=None)
            results = []
            for asset in assets:
                try:
                    strategy = self._registry.get(asset.asset_type.value)
                    results.append(strategy.compute(asset, uow))
                except Exception:
                    # Skip assets that fail computation (e.g., missing snapshots)
                    pass
            return results

    def get_asset_lots(
        self, asset_id: int, page: int = 1, size: int = 50
    ) -> LotsPageResponse:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            strategy = self._registry.get(asset.asset_type.value)
            all_lots = strategy.compute_lots(asset, uow)
            start = (page - 1) * size
            end = start + size
            return LotsPageResponse(
                items=all_lots[start:end],
                total=len(all_lots),
                page=page,
                size=size,
            )

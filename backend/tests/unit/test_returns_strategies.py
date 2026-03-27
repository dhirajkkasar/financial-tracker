import pytest
from datetime import date, datetime
from unittest.mock import MagicMock
from app.schemas.responses.returns import AssetReturnsResponse


def _make_asset(asset_id=1, name="Test", asset_type="STOCK_IN", is_active=True):
    asset = MagicMock()
    asset.id = asset_id
    asset.name = name
    asset.asset_type = MagicMock()
    asset.asset_type.value = asset_type
    asset.is_active = is_active
    return asset


def _make_uow(transactions=None, price=None, valuations=None):
    uow = MagicMock()
    uow.transactions.list_by_asset.return_value = transactions or []
    uow.price_cache.get_by_asset_id.return_value = price
    uow.valuations.list_by_asset.return_value = valuations or []
    return uow


def test_strategy_registry_raises_for_unknown_type():
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry
    from app.models.asset import AssetType

    registry = DefaultReturnsStrategyRegistry()
    with pytest.raises(ValueError, match="No returns strategy"):
        registry.get("UNKNOWN_TYPE")


def test_strategy_registry_has_all_asset_types():
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry

    registry = DefaultReturnsStrategyRegistry()
    expected_types = [
        "STOCK_IN", "STOCK_US", "RSU", "MF", "NPS",
        "GOLD", "SGB", "FD", "RD", "PPF", "REAL_ESTATE", "EPF",
    ]
    for at in expected_types:
        strategy = registry.get(at)
        assert strategy is not None, f"No strategy for {at}"


def test_returns_service_get_asset_returns_dispatches_to_strategy():
    from app.services.returns.returns_service import ReturnsService
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry
    from app.middleware.error_handler import NotFoundError

    class FakeUoW:
        class FakeAssets:
            def get_by_id(self, id):
                return None  # simulate not found
        assets = FakeAssets()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    service = ReturnsService(
        uow_factory=lambda: FakeUoW(),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )
    with pytest.raises(NotFoundError):
        service.get_asset_returns(999)

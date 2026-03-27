from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.services.returns.strategies.base import AssetReturnsStrategy


class IReturnsStrategyRegistry(Protocol):
    def get(self, asset_type: str) -> "AssetReturnsStrategy": ...


class DefaultReturnsStrategyRegistry:
    """
    Looks up the registered strategy for an asset type string.

    Importing all strategy modules triggers @register_strategy decorators,
    which populate _STRATEGY_REGISTRY. We import them lazily on first get().
    """

    def __init__(self):
        self._loaded = False
        self._map: dict[str, "AssetReturnsStrategy"] = {}

    def _ensure_loaded(self):
        if self._loaded:
            return
        # Import all strategy modules to trigger @register_strategy decorators
        import app.services.returns.strategies.asset_types.stock_in      # noqa: F401
        import app.services.returns.strategies.asset_types.stock_us      # noqa: F401
        import app.services.returns.strategies.asset_types.rsu           # noqa: F401
        import app.services.returns.strategies.asset_types.mf            # noqa: F401
        import app.services.returns.strategies.asset_types.nps           # noqa: F401
        import app.services.returns.strategies.asset_types.gold          # noqa: F401
        import app.services.returns.strategies.asset_types.sgb           # noqa: F401
        import app.services.returns.strategies.asset_types.fd            # noqa: F401
        import app.services.returns.strategies.asset_types.rd            # noqa: F401
        import app.services.returns.strategies.asset_types.ppf           # noqa: F401
        import app.services.returns.strategies.asset_types.real_estate   # noqa: F401
        import app.services.returns.strategies.asset_types.epf           # noqa: F401

        from app.services.returns.strategies.base import _STRATEGY_REGISTRY
        self._map = {at: cls() for at, cls in _STRATEGY_REGISTRY.items()}
        self._loaded = True

    def get(self, asset_type: str) -> "AssetReturnsStrategy":
        self._ensure_loaded()
        strategy = self._map.get(asset_type)
        if strategy is None:
            raise ValueError(
                f"No returns strategy for asset_type={asset_type!r}. "
                f"Registered: {sorted(self._map.keys())}"
            )
        return strategy

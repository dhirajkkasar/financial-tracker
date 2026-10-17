from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from app.repositories.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class AssetTaxGainsResult:
    asset_id: int
    asset_name: str
    asset_type: str
    asset_class: str
    st_gain: float
    lt_gain: float
    has_slab: bool                # True if STCG is slab-rated
    ltcg_exempt_eligible: bool    # True for STOCK_IN and equity MF (Section 112A)
    ltcg_slab: bool               # True if LTCG is slab-rated (Debt MF, FD/RD)
    # Per-lot long-term detail (for Schedule 112A). Each item:
    # {buy_date, sell_date, units, buy_price_per_unit, sell_price_per_unit,
    #  jan31_2018_price}. Empty for aggregate-only strategies.
    ltcg_lots: tuple = ()


class TaxGainsStrategy(ABC):
    @abstractmethod
    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy: str,
        fy_start: date,
        fy_end: date,
    ) -> AssetTaxGainsResult:
        ...


# Module-level registry: (asset_type, asset_class) → strategy instance
# "*" as asset_class means "any asset class"
_REGISTRY: dict[tuple[str, str], TaxGainsStrategy] = {}


def register_tax_strategy(*keys: tuple[str, str]):
    """
    Class decorator to register a strategy for one or more (asset_type, asset_class) keys.

    Usage:
        @register_tax_strategy(("STOCK_IN", "*"))
        class StockINTaxGainsStrategy(IndianEquityTaxGainsStrategy):
            pass

        @register_tax_strategy(("FD", "*"), ("RD", "*"))
        class AccruedInterestTaxGainsStrategy(TaxGainsStrategy):
            ...
    """
    def decorator(cls):
        instance = cls()
        for key in keys:
            _REGISTRY[key] = instance
        return cls
    return decorator


def register_tax_strategy_instance(key: tuple[str, str], instance: TaxGainsStrategy):
    """Register a pre-built strategy instance for a (asset_type, asset_class) key."""
    _REGISTRY[key] = instance


class TaxStrategyRegistry:
    """Look up a TaxGainsStrategy by (asset_type, asset_class).

    Lookup order:
      1. Exact match: (asset_type, asset_class)
      2. Wildcard:    (asset_type, "*")
      3. None if neither found
    """

    def get(self, asset_type: str, asset_class: str) -> TaxGainsStrategy | None:
        return _REGISTRY.get((asset_type, asset_class)) or _REGISTRY.get((asset_type, "*"))

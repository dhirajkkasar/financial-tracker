from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.repositories.unit_of_work import UnitOfWork


@dataclass
class AssetTaxGainsResult:
    asset_id: int
    asset_name: str
    asset_type: str
    asset_class: str
    st_gain: float
    lt_gain: float
    st_tax_estimate: float        # always numeric — slab items use injected slab_rate_pct
    lt_tax_estimate: float        # always numeric, pre-exemption for ltcg_exempt_eligible
    ltcg_exemption_used: float    # always 0.0 here — exemption applied at entry level
    has_slab: bool                # True if slab_rate_pct was used for any gain
    ltcg_exempt_eligible: bool    # True for STOCK_IN and equity MF (Section 112A)
    ltcg_slab: bool               # True if LTCG is slab-rated (Debt MF, FD/RD)


class TaxGainsStrategy(ABC):
    @abstractmethod
    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
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


class TaxStrategyRegistry:
    """Look up a TaxGainsStrategy by (asset_type, asset_class).

    Lookup order:
      1. Exact match: (asset_type, asset_class)
      2. Wildcard:    (asset_type, "*")
      3. None if neither found
    """

    def get(self, asset_type: str, asset_class: str) -> Optional[TaxGainsStrategy]:
        return _REGISTRY.get((asset_type, asset_class)) or _REGISTRY.get((asset_type, "*"))

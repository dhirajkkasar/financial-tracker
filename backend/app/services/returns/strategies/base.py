"""
AssetReturnsStrategy — template method pattern.

compute() orchestrates the calculation. Subclasses override only the hooks
that differ from the default. This keeps each leaf class to ~3 lines.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import ClassVar, Optional

from app.engine.returns import (
    compute_xirr, compute_cagr, compute_absolute_return,
    OUTFLOW_TYPES, INFLOW_TYPES, EXCLUDED_TYPES,
)
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse

# Registry for @register_strategy decorator
_STRATEGY_REGISTRY: dict[str, type["AssetReturnsStrategy"]] = {}


def register_strategy(asset_type: str):
    """Class decorator: register a strategy class for an asset type string."""
    def decorator(cls):
        _STRATEGY_REGISTRY[asset_type] = cls
        return cls
    return decorator


class AssetReturnsStrategy(ABC):
    """
    Template method: compute() orchestrates, hooks are overridden by subclasses.

    Default implementations:
        get_invested_value() → sum of outflow transaction amounts
        build_cashflows()    → standard inflow/outflow list for XIRR
        compute_lots()       → [] (not supported; override in MarketBasedStrategy)
    """

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        invested = self.get_invested_value(asset, uow)
        current = self.get_current_value(asset, uow)
        cashflows = self.build_cashflows(asset, uow)
        xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None
        pnl = (current - invested) if (current is not None and invested is not None) else None
        pnl_pct = (pnl / invested * 100) if (pnl is not None and invested and invested > 0) else None
        return AssetReturnsResponse(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            is_active=asset.is_active,
            invested=invested,
            current_value=current,
            current_pnl=pnl,
            current_pnl_pct=pnl_pct,
            xirr=xirr,
        )

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """Default: sum of outflow transaction amounts (in INR, converted from paise)."""
        txns = uow.transactions.list_by_asset(asset.id)
        outflows = [abs(t.amount_inr / 100) for t in txns if t.type.value in OUTFLOW_TYPES]
        return sum(outflows) if outflows else 0.0

    @abstractmethod
    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """Must be implemented by each strategy."""
        ...

    def build_cashflows(self, asset, uow: UnitOfWork) -> list[tuple[date, float]]:
        """Default: standard signed cashflows for XIRR computation."""
        txns = uow.transactions.list_by_asset(asset.id)
        cashflows = []
        for t in txns:
            if t.type.value in EXCLUDED_TYPES:
                continue
            amount_inr = t.amount_inr / 100  # paise → INR
            cashflows.append((t.date, -amount_inr))  # negative = outflow for XIRR
        return cashflows

    def compute_lots(self, asset, uow: UnitOfWork) -> list:
        """Default: lots not supported. Override in MarketBasedStrategy."""
        return []

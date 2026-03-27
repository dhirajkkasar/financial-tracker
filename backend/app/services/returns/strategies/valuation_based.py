"""
ValuationBasedStrategy — current_value = latest Valuation entry (manual passbook).

Used for PPF and REAL_ESTATE. Subclasses override get_current_value() for FD/RD.
"""
from __future__ import annotations

from typing import Optional

from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import AssetReturnsStrategy


class ValuationBasedStrategy(AssetReturnsStrategy):
    """
    Intermediate: current_value = latest Valuation.value_inr.

    If no Valuation exists, current_value is None and xirr is None.
    """

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        valuations = uow.valuations.list_by_asset(asset.id)
        if not valuations:
            return None
        latest = sorted(valuations, key=lambda v: v.date, reverse=True)[0]
        return latest.value_inr / 100  # paise → INR

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        base = super().compute(asset, uow)
        if base.current_value is None:
            return AssetReturnsResponse(
                **base.model_dump(),
                message="No valuation entry found. Add one via /assets/{id}/valuations.",
            )
        return base

"""
FDStrategy — current_value = fd_engine formula (not latest valuation).
"""
from typing import Optional

from app.engine.fd_engine import compute_fd_current_value
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("FD")
class FDStrategy(ValuationBasedStrategy):

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail is None:
            return None
        result = compute_fd_current_value(fd_detail)
        return result.get("accrued_value_today")

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        base = super().compute(asset, uow)
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail:
            from app.engine.fd_engine import compute_fd_maturity
            maturity = compute_fd_maturity(fd_detail)
            txns = uow.transactions.list_by_asset(asset.id)
            interest_txns = [t for t in txns if t.type.value == "INTEREST"]
            taxable_interest = sum(abs(t.amount_inr / 100) for t in interest_txns)
            return AssetReturnsResponse(
                **base.model_dump(),
                maturity_amount=maturity.get("maturity_amount"),
                taxable_interest=taxable_interest,
                potential_tax_30pct=round(taxable_interest * 0.30, 2),
            )
        return base

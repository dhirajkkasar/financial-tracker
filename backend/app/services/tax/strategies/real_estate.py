from __future__ import annotations

from datetime import date

from app.engine.tax_engine import TaxRuleResolver
from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import (
    AssetTaxGainsResult,
    TaxGainsStrategy,
)

BUY_TXNS = {"BUY", "CONTRIBUTION"}
SELL_TXNS = {"SELL", "WITHDRAWAL"}


def _zero_result(asset) -> AssetTaxGainsResult:
    return AssetTaxGainsResult(
        asset_id=asset.id, asset_name=asset.name,
        asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
        st_gain=0.0, lt_gain=0.0,
        st_tax_estimate=0.0, lt_tax_estimate=0.0,
        ltcg_exemption_used=0.0, has_slab=False,
        ltcg_exempt_eligible=False, ltcg_slab=False,
    )


class RealEstateTaxGainsStrategy(TaxGainsStrategy):
    """
    Real estate: SELL/WITHDRAWAL transactions in FY → gain = FY proceeds − pro-rata cost.

    Not FIFO — real estate is not unit-tracked. Cost is allocated pro-rata:
    cost_basis_for_FY = total_invested × (FY_proceeds / lifetime_proceeds_all_time).
    Holding is checked per FY sale against the earliest buy: if ANY sale in the FY
    is long-term (sale_date − earliest_buy ≥ stcg_days) its pro-rata gain is treated
    as LT, otherwise ST.

    Limitation: with multiple buys at different dates, the earliest-buy reference
    may classify a sale as LT even though some cost tranches are short-term.
    Per-tranche FIFO matching would require unit tracking, which real estate lacks.
    """

    def __init__(self, resolver: TaxRuleResolver | None = None):
        self._resolver = resolver

    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy: str,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        txns = uow.transactions.list_by_asset(asset.id)

        buy_txns = [
            t for t in txns
            if (t.type.value if hasattr(t.type, "value") else str(t.type)) in BUY_TXNS
        ]
        sell_txns_in_fy = [
            t for t in txns
            if (t.type.value if hasattr(t.type, "value") else str(t.type)) in SELL_TXNS
            and fy_start <= t.date <= fy_end
        ]

        if not buy_txns or not sell_txns_in_fy:
            return _zero_result(asset)

        total_invested = sum(abs(t.amount_inr / 100.0) for t in buy_txns)
        if total_invested == 0:
            return _zero_result(asset)

        fy_proceeds = sum(abs(t.amount_inr / 100.0) for t in sell_txns_in_fy)
        lifetime_proceeds = sum(
            abs(t.amount_inr / 100.0)
            for t in txns
            if (t.type.value if hasattr(t.type, "value") else str(t.type)) in SELL_TXNS
        )
        if lifetime_proceeds > 0:
            allocated_cost = total_invested * (fy_proceeds / lifetime_proceeds)
        else:
            allocated_cost = total_invested
        gain = fy_proceeds - allocated_cost

        earliest_buy_date = min(t.date for t in buy_txns)

        # Resolve rule from config or use fallback defaults
        if self._resolver is not None:
            rule = self._resolver.resolve(fy, "REAL_ESTATE")
            stcg_days = rule.stcg_days
            ltcg_rate = rule.ltcg_rate_pct if rule.ltcg_rate_pct is not None else slab_rate_pct
        else:
            stcg_days = 730
            ltcg_rate = 12.5

        # Per-sale holding check: each FY sale's pro-rata gain is classified by
        # (sale_date − earliest_buy). If ANY sale in the FY is LT, LT gain results.
        st_gain, lt_gain = 0.0, 0.0
        for t in sell_txns_in_fy:
            proceeds = abs(t.amount_inr / 100.0)
            share = proceeds / fy_proceeds if fy_proceeds else 0.0
            sale_gain = proceeds - allocated_cost * share
            if (t.date - earliest_buy_date).days < stcg_days:
                st_gain += sale_gain
            else:
                lt_gain += sale_gain

        st_tax = max(0.0, st_gain) * slab_rate_pct / 100.0
        lt_tax = max(0.0, lt_gain) * ltcg_rate / 100.0
        has_slab = st_gain > 0

        return AssetTaxGainsResult(
            asset_id=asset.id, asset_name=asset.name,
            asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
            st_gain=st_gain, lt_gain=lt_gain,
            st_tax_estimate=st_tax, lt_tax_estimate=lt_tax,
            ltcg_exemption_used=0.0, has_slab=has_slab,
            ltcg_exempt_eligible=False, ltcg_slab=False,
        )

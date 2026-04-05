from __future__ import annotations

from datetime import date

from app.engine.lot_engine import match_lots_fifo
from app.engine.lot_helper import LotHelper
from app.engine.tax_engine import TaxRuleResolver
from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxGainsStrategy


class FifoTaxGainsStrategy(TaxGainsStrategy):
    """
    Config-driven FIFO lot-matched tax strategy.

    Resolves tax rules per-lot using TaxRuleResolver — no hardcoded rates.
    Handles epoch splits (e.g., debt MF pre/post 2023) and ISIN overrides
    automatically via the YAML config.
    """

    def __init__(self, resolver: TaxRuleResolver | None = None):
        self._resolver = resolver

    def _zero_result(self, asset) -> AssetTaxGainsResult:
        return AssetTaxGainsResult(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            asset_class=asset.asset_class.value,
            st_gain=0.0, lt_gain=0.0,
            st_tax_estimate=0.0, lt_tax_estimate=0.0,
            ltcg_exemption_used=0.0,
            has_slab=False,
            ltcg_exempt_eligible=False,
            ltcg_slab=False,
        )

    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy: str,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        if self._resolver is None:
            raise RuntimeError(
                "FifoTaxGainsStrategy requires a TaxRuleResolver. "
                "Use register_tax_strategy_instance() with an injected resolver."
            )
        asset_type = asset.asset_type.value
        asset_class = asset.asset_class.value
        isin = asset.identifier

        # Default rule (no buy_date) for stcg_days used in lot matching
        default_rule = self._resolver.resolve(
            fy, asset_type, asset_class=asset_class, isin=isin,
        )

        txns = uow.transactions.list_by_asset(asset.id)
        lots, sells = LotHelper(stcg_days=default_rule.stcg_days).build_lots_sells(txns)

        if not lots or not sells:
            return self._zero_result(asset)

        matched = match_lots_fifo(lots, sells, stcg_days=default_rule.stcg_days)

        st_gain, lt_gain = 0.0, 0.0
        st_tax, lt_tax = 0.0, 0.0
        has_slab = False
        ltcg_exempt_eligible = False

        for m in matched:
            sell_date = m["sell_date"]
            buy_date = m["buy_date"]
            if isinstance(sell_date, str):
                sell_date = date.fromisoformat(sell_date)
            if isinstance(buy_date, str):
                buy_date = date.fromisoformat(buy_date)
            if not (fy_start <= sell_date <= fy_end):
                continue

            # Resolve rule for THIS lot's buy_date
            rule = self._resolver.resolve(
                fy, asset_type, asset_class=asset_class,
                isin=isin, buy_date=buy_date,
            )

            holding_days = (sell_date - buy_date).days
            gain = m["realised_gain_inr"]

            if holding_days < rule.stcg_days:
                st_gain += gain
                rate = rule.stcg_rate_pct if rule.stcg_rate_pct is not None else slab_rate_pct
                if gain > 0:
                    st_tax += gain * rate / 100.0
                if rule.stcg_rate_pct is None:
                    has_slab = True
            else:
                lt_gain += gain
                rate = rule.ltcg_rate_pct if rule.ltcg_rate_pct is not None else slab_rate_pct
                if gain > 0:
                    lt_tax += gain * rate / 100.0
                if rule.ltcg_rate_pct is None:
                    has_slab = True

            if rule.ltcg_exempt_eligible:
                ltcg_exempt_eligible = True

        return AssetTaxGainsResult(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset_type,
            asset_class=asset_class,
            st_gain=st_gain,
            lt_gain=lt_gain,
            st_tax_estimate=st_tax,
            lt_tax_estimate=lt_tax,
            ltcg_exemption_used=0.0,
            has_slab=has_slab,
            ltcg_exempt_eligible=ltcg_exempt_eligible,
            ltcg_slab=False,
        )

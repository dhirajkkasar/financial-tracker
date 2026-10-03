"""
MFStrategy — current value = units × price_cache NAV (same as all market-based assets).

Active fund:   invested = open lot cost basis; current = units × NAV; alltime_pnl = unrealised + realised.
Inactive fund: invested = 0 (no open lots); current = 0; alltime_pnl = st_realised + lt_realised from lot engine.
XIRR is computed from transaction cashflows for both states.

ST/LT classification is per-lot via TaxRuleResolver (not the 365-day class
default): debt funds use 730 days, specified funds (<=35% equity) bought
on/after 01-Apr-2023 are slab-rated, and ISIN overrides apply. The FY used
for resolution is derived from the sell/as-of date.
"""
from datetime import date
from pathlib import Path
from typing import ClassVar, Optional

from app.engine.tax_engine import TaxRuleResolver
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy

_RESOLVER = TaxRuleResolver(Path("app/config/tax_rates"))
_FALLBACK_STCG_DAYS = 365


def _fy_label_for(d: date) -> str:
    if d.month >= 4:
        return f"{d.year}-{str(d.year + 1)[-2:]}"
    return f"{d.year - 1}-{str(d.year)[-2:]}"


def _rule_stcg_days(asset, buy_date: date, ref_date: date) -> int:
    try:
        rule = _RESOLVER.resolve(
            _fy_label_for(ref_date), "MF",
            asset_class=asset.asset_class.value,
            isin=asset.identifier,
            buy_date=buy_date,
        )
        return rule.stcg_days
    except Exception:
        return _FALLBACK_STCG_DAYS


@register_strategy("MF")
class MFStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 365

    def _match_and_get_open_lots(self, lots, sells,
                                 current_price: Optional[float],
                                 as_of: Optional[date] = None):
        # Match with the class default, then re-derive every ST/LT flag
        # per-lot so debt / specified-fund / ISIN rules apply.
        asset = getattr(self, "_mf_asset", None)
        open_lots, matched = super()._match_and_get_open_lots(
            lots, sells, current_price, as_of=as_of,
        )
        if asset is None:
            return open_lots, matched
        ref = as_of or date.today()
        for ol in open_lots:
            stcg_days = _rule_stcg_days(asset, ol.lot.buy_date, ref)
            ol.is_short_term = ((ref - ol.lot.buy_date).days < stcg_days)
        for m in matched:
            buy_date = m["buy_date"]
            sell_date = m["sell_date"]
            if isinstance(buy_date, str):
                buy_date = date.fromisoformat(buy_date)
            if isinstance(sell_date, str):
                sell_date = date.fromisoformat(sell_date)
            stcg_days = _rule_stcg_days(asset, buy_date, sell_date)
            m["is_short_term"] = ((sell_date - buy_date).days < stcg_days)
        return open_lots, matched

    def compute(self, asset, uow):
        self._mf_asset = asset
        try:
            return super().compute(asset, uow)
        finally:
            self._mf_asset = None

    def compute_lots(self, asset, uow):
        self._mf_asset = asset
        try:
            return super().compute_lots(asset, uow)
        finally:
            self._mf_asset = None

"""RSU tax strategy — two-stage taxation (AY 2026-27 / FY 2025-26 onwards).

Stage 1 (salary, employer-TDS'd): VEST FMV taxed as perquisite at slab.
  Reported here in st_gain (slab-rated, has_slab=True) so the FY tax
  estimate is complete in one place. NOTE: st_gain for RSU therefore bundles
  perquisite (salary) + short-term capital gains — both slab-rated, so the
  tax number is correct; a future UI change should split the labels.
Stage 2 (capital gains on post-vest appreciation, cost = vest FMV):
  foreign/unlisted shares — <=24m slab, >24m 12.5% without indexation,
  no Rs 1.25L exemption (Section 112, not 112A — no STT paid).
  Indian-listed employer shares would follow 12m/20%/12.5%+exemption;
  this tracker treats RSU assets as foreign (730-day) per the common
  Fidelity/NASDAQ case. Tag Indian-listed RSUs separately if needed.
"""
from __future__ import annotations

from datetime import date

from app.engine.lot_engine import match_lots
from app.engine.lot_helper import LotHelper
from app.engine.tax_engine import TaxRuleResolver
from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxGainsStrategy


def _ttype(t) -> str:
    return t.type.value if hasattr(t.type, "value") else str(t.type)


class RSUTaxGainsStrategy(TaxGainsStrategy):
    def __init__(self, resolver: TaxRuleResolver | None = None):
        self._resolver = resolver

    def _zero(self, asset) -> AssetTaxGainsResult:
        return AssetTaxGainsResult(
            asset_id=asset.id, asset_name=asset.name,
            asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
            st_gain=0.0, lt_gain=0.0,
            st_tax_estimate=0.0, lt_tax_estimate=0.0,
            ltcg_exemption_used=0.0, has_slab=False,
            ltcg_exempt_eligible=False, ltcg_slab=False,
        )

    def compute(self, asset, uow: UnitOfWork, fy: str,
                fy_start: date, fy_end: date, slab_rate_pct: float) -> AssetTaxGainsResult:
        if self._resolver is None:
            raise RuntimeError("RSUTaxGainsStrategy requires a TaxRuleResolver.")
        txns = uow.transactions.list_by_asset(asset.id)

        # Stage 1: perquisite on VEST in FY (salary, slab)
        perquisite = sum(
            abs(t.amount_inr / 100.0) for t in txns
            if _ttype(t) == "VEST" and fy_start <= t.date <= fy_end
        )

        lots, sells = LotHelper(stcg_days=730).build_lots_sells(txns)
        st_gain, lt_gain, st_tax, lt_tax = perquisite, 0.0, 0.0, 0.0
        has_slab = perquisite > 0
        if perquisite > 0:
            st_tax += perquisite * slab_rate_pct / 100.0

        if lots and sells:
            matched = match_lots(lots, sells, stcg_days=730)
            for m in matched:
                sell_date = m["sell_date"]
                buy_date = m["buy_date"]
                if isinstance(sell_date, str):
                    sell_date = date.fromisoformat(sell_date)
                if isinstance(buy_date, str):
                    buy_date = date.fromisoformat(buy_date)
                if not (fy_start <= sell_date <= fy_end):
                    continue
                rule = self._resolver.resolve(
                    fy, "RSU", asset_class=asset.asset_class.value,
                    isin=asset.identifier, buy_date=buy_date,
                )
                holding = (sell_date - buy_date).days
                gain = m["realised_gain_inr"]
                if holding < rule.stcg_days:
                    st_gain += gain
                    if gain > 0:
                        rate = rule.stcg_rate_pct if rule.stcg_rate_pct is not None else slab_rate_pct
                        st_tax += gain * rate / 100.0
                        if rule.stcg_rate_pct is None:
                            has_slab = True
                else:
                    lt_gain += gain
                    if gain > 0:
                        rate = rule.ltcg_rate_pct if rule.ltcg_rate_pct is not None else slab_rate_pct
                        lt_tax += gain * rate / 100.0

        if st_gain == 0 and lt_gain == 0:
            return self._zero(asset)
        return AssetTaxGainsResult(
            asset_id=asset.id, asset_name=asset.name,
            asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
            st_gain=st_gain, lt_gain=lt_gain,
            st_tax_estimate=st_tax if st_gain > 0 else 0.0,
            lt_tax_estimate=lt_tax if lt_gain > 0 else 0.0,
            ltcg_exemption_used=0.0, has_slab=has_slab,
            ltcg_exempt_eligible=False, ltcg_slab=False,
        )

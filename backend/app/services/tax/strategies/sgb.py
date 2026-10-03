"""SGB tax strategy — secondary-market sales + RBI redemptions + interest coupon.

Rules applied (Finance Act 2024 + Budget 2026 amendment w.e.f. 01-Apr-2026):
  * Secondary-market sale: <=12m slab, >12m 12.5% without indexation
    (listed SGBs use the 12-month threshold; SGB YAML block holds 365 days).
  * RBI redemption at ~8-year maturity: exempt ONLY for bonds subscribed at
    primary issuance and held continuously to maturity. From FY 2026-27 this
    primary-only rule applies (Budget 2026 amendment to Section 70 of the
    Income-tax Act, 2025). For earlier FYs any RBI redemption at maturity
    is exempt (pre-amendment Section 47 treatment).
  * Primary vs secondary is detected via a "secondary" marker in the asset
    notes (case-insensitive). Assets without the marker are treated as
    primary issuance. Tag secondary-market purchases in notes with
    "secondary" for correct post-2026 treatment.
  * SGB interest coupon (2.5% p.a., INTEREST txns) is Income from Other
    Sources taxed at slab — reported here in st_gain with has_slab=True.

Maturity is approximated as holding >= 2920 days (8 x 365).
"""
from __future__ import annotations

from datetime import date

from app.engine.lot_engine import match_lots
from app.engine.lot_helper import LotHelper
from app.engine.tax_engine import TaxRuleResolver
from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxGainsStrategy

SGB_MATURITY_DAYS = 2920  # ~8 years
# FYs from which the Budget 2026 primary-only exemption rule applies
NEW_SGB_RULE_FROM_FY_START = 2026


def _fy_start_year(fy_label: str) -> int:
    return int(fy_label.split("-")[0])


def _is_secondary(asset) -> bool:
    notes = (getattr(asset, "notes", None) or "")
    identifier = (getattr(asset, "identifier", None) or "")
    return "secondary" in f"{notes} {identifier}".lower()


class SGBTaxGainsStrategy(TaxGainsStrategy):
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
            raise RuntimeError("SGBTaxGainsStrategy requires a TaxRuleResolver.")
        txns = uow.transactions.list_by_asset(asset.id)
        lots, sells = LotHelper(stcg_days=365).build_lots_sells(txns)
        if not lots or not sells:
            # No sales — but the interest coupon may still be taxable
            return self._with_interest_only(asset, uow, fy_start, fy_end, slab_rate_pct)

        matched = match_lots(lots, sells, stcg_days=365)
        secondary = _is_secondary(asset)
        new_rule = _fy_start_year(fy) >= NEW_SGB_RULE_FROM_FY_START

        st_gain, lt_gain, st_tax, lt_tax = 0.0, 0.0, 0.0, 0.0
        has_slab = False
        for m in matched:
            sell_date = m["sell_date"]
            buy_date = m["buy_date"]
            if isinstance(sell_date, str):
                sell_date = date.fromisoformat(sell_date)
            if isinstance(buy_date, str):
                buy_date = date.fromisoformat(buy_date)
            if not (fy_start <= sell_date <= fy_end):
                continue
            holding = (sell_date - buy_date).days
            gain = m["realised_gain_inr"]

            # RBI-redemption-at-maturity exemption
            if holding >= SGB_MATURITY_DAYS and (not new_rule or not secondary):
                continue  # exempt — pre-2026 any RBI redemption; post-2026 primary only

            rule = self._resolver.resolve(
                fy, "SGB", asset_class=asset.asset_class.value,
                isin=asset.identifier, buy_date=buy_date,
            )
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

        interest, interest_tax = self._fy_interest(txns, fy_start, fy_end, slab_rate_pct)
        st_gain += interest
        st_tax += interest_tax
        if interest > 0:
            has_slab = True

        return AssetTaxGainsResult(
            asset_id=asset.id, asset_name=asset.name,
            asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
            st_gain=st_gain, lt_gain=lt_gain,
            st_tax_estimate=st_tax if st_gain > 0 else 0.0,
            lt_tax_estimate=lt_tax if lt_gain > 0 else 0.0,
            ltcg_exemption_used=0.0, has_slab=has_slab,
            ltcg_exempt_eligible=False, ltcg_slab=False,
        )

    def _fy_interest(self, txns, fy_start: date, fy_end: date,
                     slab_rate_pct: float) -> tuple[float, float]:
        total = sum(
            abs(t.amount_inr / 100.0) for t in txns
            if (t.type.value if hasattr(t.type, "value") else str(t.type)) == "INTEREST"
            and fy_start <= t.date <= fy_end
        )
        return total, total * slab_rate_pct / 100.0

    def _with_interest_only(self, asset, uow: UnitOfWork,
                            fy_start: date, fy_end: date,
                            slab_rate_pct: float) -> AssetTaxGainsResult:
        txns = uow.transactions.list_by_asset(asset.id)
        interest, interest_tax = self._fy_interest(txns, fy_start, fy_end, slab_rate_pct)
        if interest == 0:
            return self._zero(asset)
        return AssetTaxGainsResult(
            asset_id=asset.id, asset_name=asset.name,
            asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
            st_gain=interest, lt_gain=0.0,
            st_tax_estimate=interest_tax, lt_tax_estimate=0.0,
            ltcg_exemption_used=0.0, has_slab=True,
            ltcg_exempt_eligible=False, ltcg_slab=False,
        )

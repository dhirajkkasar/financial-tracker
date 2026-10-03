"""NPS tax strategy — Tier I vs Tier II (PFRDA 2025 withdrawal rules + Sec 10(12A)).

Tier detection: transaction notes carry "Tier I" / "Tier II" (see
nps_csv_importer._build_notes). An asset is Tier II if ANY txn note mentions
Tier II; otherwise Tier I.

Tier II (no lock-in, no exemption): withdrawals in FY are taxed at slab.
  Gain proxy = FY withdrawals minus pro-rata contributions:
    taxable = max(0, fy_withdrawals - fy_contributions) + min(fy_withdrawals, fy_contributions) * 0
  i.e. only the gains slice is taxable; contributions returned are capital.
  Pro-rata: taxable = fy_wd * (1 - total_contrib / max(total_contrib + accrued, fy_wd)).
  Simplified to FIFO-free pro-rata using lifetime totals. Reported slab.

Tier I (retirement account): at normal exit up to 80% lump sum permitted
(PFRDA 2025), but only 60% is exempt under Section 10(12A); the extra 20%
is taxable at slab; the remaining 20% annuity purchase is deferred (pension
taxed yearly on payout, not at withdrawal). Per-withdrawal approximation:
  taxable = 25% of each FY withdrawal (20/80), exempt/deferred = 75%.
  NOTE: pre-exit partial withdrawals (up to 25% of own contributions for
  specified purposes) are separately exempt u/s 10(12B); the importer does
  not distinguish them, so this strategy conservatively treats all Tier I
  withdrawals as exit lump sums. Tag partials in notes with "partial" to
  exempt them — notes containing "partial" are excluded from taxable.
"""
from __future__ import annotations

from datetime import date

from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxGainsStrategy


def _ttype(t) -> str:
    return t.type.value if hasattr(t.type, "value") else str(t.type)


def _notes(t) -> str:
    return str(getattr(t, "notes", None) or "")


def _is_tier_ii(txns) -> bool:
    for t in txns:
        if "tier ii" in _notes(t).lower() or "tier 2" in _notes(t).lower():
            return True
    return False


class NPSTaxGainsStrategy(TaxGainsStrategy):
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
        txns = uow.transactions.list_by_asset(asset.id)
        if _is_tier_ii(txns):
            taxable = self._tier_ii_taxable(txns, fy_start, fy_end)
        else:
            taxable = self._tier_i_taxable(txns, fy_start, fy_end)
        if taxable <= 0:
            return self._zero(asset)
        return AssetTaxGainsResult(
            asset_id=asset.id, asset_name=asset.name,
            asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
            st_gain=taxable, lt_gain=0.0,
            st_tax_estimate=taxable * slab_rate_pct / 100.0, lt_tax_estimate=0.0,
            ltcg_exemption_used=0.0, has_slab=True,
            ltcg_exempt_eligible=False, ltcg_slab=True,
        )

    def _fy(self, txns, types: set[str], fy_start: date, fy_end: date) -> float:
        return sum(
            abs(t.amount_inr / 100.0) for t in txns
            if _ttype(t) in types and fy_start <= t.date <= fy_end
        )

    def _tier_ii_taxable(self, txns, fy_start: date, fy_end: date) -> float:
        fy_wd = self._fy(txns, {"WITHDRAWAL", "REDEMPTION", "SELL"}, fy_start, fy_end)
        if fy_wd <= 0:
            return 0.0
        total_contrib = sum(
            abs(t.amount_inr / 100.0) for t in txns if _ttype(t) == "CONTRIBUTION"
        )
        total_in = total_contrib + sum(
            abs(t.amount_inr / 100.0) for t in txns
            if _ttype(t) in {"CONTRIBUTION", "INTEREST", "DIVIDEND"}
        )
        if total_in <= 0:
            return fy_wd
        principal_ratio = min(1.0, total_contrib / total_in)
        return max(0.0, fy_wd * (1.0 - principal_ratio))

    def _tier_i_taxable(self, txns, fy_start: date, fy_end: date) -> float:
        total = 0.0
        for t in txns:
            if _ttype(t) not in {"WITHDRAWAL", "REDEMPTION", "SELL"}:
                continue
            if not (fy_start <= t.date <= fy_end):
                continue
            if "partial" in _notes(t).lower():
                continue  # 10(12B) exempt partial — tagged in notes
            total += abs(t.amount_inr / 100.0) * 0.25  # 20/80 taxable slice
        return total

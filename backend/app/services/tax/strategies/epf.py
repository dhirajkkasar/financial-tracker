"""EPF tax strategy — taxable interest on excess employee contributions (Rule 9D).

CBDT Notification 95/2021 w.e.f. FY 2021-22: interest on an employee's own
contribution above Rs 2.5L in a FY is taxable at slab. Threshold is Rs 5L
where the employer makes no contribution (no Employer Share txn in the FY).
Only the Employee Interest slice is apportioned:
  taxable = employee_interest_FY * max(0, emp_contrib_FY - threshold) / emp_contrib_FY
Transfer-in contributions (notes "Transfer In - ...") are excluded from the
FY contribution count (they are not fresh contributions). EPS interest and
employer-share interest are out of scope here (withdrawal taxation applies
separately on premature closure before 5 years of continuous service).
Gross interest is used (TDS u/s 194A is advance tax, not a deduction).
"""
from __future__ import annotations

from datetime import date

from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxGainsStrategy

BASE_THRESHOLD = 250_000.0
NO_EMPLOYER_THRESHOLD = 500_000.0


def _ttype(t) -> str:
    return t.type.value if hasattr(t.type, "value") else str(t.type)


def _notes(t) -> str:
    return str(getattr(t, "notes", None) or "")


class EPFTaxGainsStrategy(TaxGainsStrategy):
    def _zero(self, asset) -> AssetTaxGainsResult:
        return AssetTaxGainsResult(
            asset_id=asset.id, asset_name=asset.name,
            asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
            st_gain=0.0, lt_gain=0.0,
            st_tax_estimate=0.0, lt_tax_estimate=0.0,
            ltcg_exemption_used=0.0, has_slab=False,
            ltcg_exempt_eligible=False, ltcg_slab=True,
        )

    def compute(self, asset, uow: UnitOfWork, fy: str,
                fy_start: date, fy_end: date, slab_rate_pct: float) -> AssetTaxGainsResult:
        txns = uow.transactions.list_by_asset(asset.id)
        emp_contrib = 0.0
        has_employer = False
        emp_interest = 0.0
        for t in txns:
            if not (fy_start <= t.date <= fy_end):
                continue
            tt, notes = _ttype(t), _notes(t)
            if tt == "CONTRIBUTION" and notes == "Employee Share":
                emp_contrib += abs(t.amount_inr / 100.0)
            elif tt == "CONTRIBUTION" and "Employer Share" in notes:
                has_employer = True
            elif tt == "INTEREST" and "Employee Interest" in notes:
                emp_interest += abs(t.amount_inr / 100.0)

        threshold = BASE_THRESHOLD if has_employer else NO_EMPLOYER_THRESHOLD
        if emp_contrib <= 0 or emp_interest <= 0:
            return self._zero(asset)
        excess_ratio = max(0.0, emp_contrib - threshold) / emp_contrib
        taxable = emp_interest * excess_ratio
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

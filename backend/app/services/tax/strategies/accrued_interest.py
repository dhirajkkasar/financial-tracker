from __future__ import annotations

from datetime import date, timedelta

from app.engine.fd_engine import compute_fd_current_value, compute_rd_maturity
from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import (
    AssetTaxGainsResult,
    TaxGainsStrategy,
    register_tax_strategy,
)


def _fd_value_at(fd, as_of: date) -> float:
    """Current value of an FD (in INR) at a given date using compound interest."""
    principal_inr = fd.principal_amount / 100.0
    return compute_fd_current_value(
        principal_inr,
        fd.interest_rate_pct,
        fd.compounding.value,
        fd.start_date,
        fd.maturity_date,
        as_of=as_of,
    )


def _rd_interest_in_window(fd, window_start: date, window_end: date) -> float:
    """
    RD interest accrued in [window_start, window_end] using linear proration
    of total interest across the RD tenure.
    """
    total_months = round((fd.maturity_date - fd.start_date).days / 30.44)
    if total_months == 0:
        return 0.0
    monthly_inr = fd.principal_amount / 100.0
    maturity_inr = compute_rd_maturity(monthly_inr, fd.interest_rate_pct, total_months)
    total_principal = monthly_inr * total_months
    total_interest = max(0.0, maturity_inr - total_principal)
    total_days = (fd.maturity_date - fd.start_date).days
    if total_days == 0:
        return 0.0
    window_days = (window_end - window_start).days
    return total_interest * (window_days / total_days)


def _zero_result(asset) -> AssetTaxGainsResult:
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
        ltcg_slab=True,
    )


@register_tax_strategy(("FD", "*"), ("RD", "*"))
class AccruedInterestTaxGainsStrategy(TaxGainsStrategy):
    """
    FD/RD: interest accrued in the FY is taxed at slab rate.

    FD: exact compound interest using compute_fd_current_value.
    RD: linear proration of total interest across tenure (approximation).
    """

    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy: str,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        fd = uow.fd.get_by_asset_id(asset.id)
        if fd is None:
            return _zero_result(asset)

        # No overlap between FD tenure and FY
        if fd.start_date > fy_end or fd.maturity_date < fy_start:
            return _zero_result(asset)

        effective_end = min(fy_end, fd.maturity_date)
        # Value at end of previous FY (or FD start if it began this FY)
        prior_date = max(fd.start_date, fy_start - timedelta(days=1))

        if prior_date >= effective_end:
            return _zero_result(asset)

        fd_type = fd.fd_type.value
        if fd_type == "FD":
            value_end = _fd_value_at(fd, effective_end)
            value_prior = _fd_value_at(fd, prior_date)
            interest = max(0.0, value_end - value_prior)
        else:  # RD
            window_start = max(fd.start_date, fy_start)
            window_end = min(fy_end, fd.maturity_date)
            interest = _rd_interest_in_window(fd, window_start, window_end)

        st_tax = interest * slab_rate_pct / 100.0

        return AssetTaxGainsResult(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            asset_class=asset.asset_class.value,
            st_gain=interest,
            lt_gain=0.0,
            st_tax_estimate=st_tax,
            lt_tax_estimate=0.0,
            ltcg_exemption_used=0.0,
            has_slab=True,
            ltcg_exempt_eligible=False,
            ltcg_slab=True,
        )

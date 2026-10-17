"""New-regime whole-return tax computation (FY 2025-26 onwards). Pure, no DB.

Composes ``engine.income_tax`` (slabs, surcharge, cess) with the special rates:

* STCG on listed equity u/s 111A @ 20%
* LTCG u/s 112A @ 12.5% on the gain above the Rs 1.25L exemption
* other LTCG @ 12.5%

Two rules the slab engine cannot express on its own, both from Finance Act 2025:

* Section 87A rebate (new regime) is computed on income *other than* gains taxed
  at special rates — salary/interest/dividends/STCG-at-slab only.
* The rebate has **marginal relief**: just above the Rs 12L threshold the rebate
  is clawed back only to the extent tax exceeds (income - Rs 12L).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.engine.income_tax import IncomeTaxConfig, load_income_tax_config

DEFAULT_CONFIG_DIR = Path("app/config/tax_rates")


# ── Inputs / outputs ──────────────────────────────────────────────────────────

@dataclass
class IncomeBuckets:
    """Taxable income grouped by how it is charged."""

    salary: float = 0.0            # net of exemptions/standard deduction/prof. tax
    other_interest: float = 0.0    # FD/RD/savings interest — slab
    dividends: float = 0.0         # slab
    stcg_slab: float = 0.0         # short-term gains not taxed at a special rate
    stcg_111a: float = 0.0         # listed-equity STCG @ 20%
    ltcg_112a: float = 0.0         # listed-equity LTCG, before the Rs 1.25L exemption
    ltcg_other_12_5: float = 0.0   # other LTCG @ 12.5%


@dataclass
class ItrTaxComputation:
    normal_income: float = 0.0
    ltcg_112a_taxable: float = 0.0
    normal_tax_inr: float = 0.0
    stcg_111a_tax_inr: float = 0.0
    ltcg_112a_tax_inr: float = 0.0
    ltcg_other_tax_inr: float = 0.0
    rebate_87a_inr: float = 0.0
    surcharge_inr: float = 0.0
    cess_inr: float = 0.0
    total_tax_inr: float = 0.0


@dataclass(frozen=True)
class ItrRates:
    """Special rates + limits, config-driven per FY (defaults = FY 2025-26)."""

    stcg_111a_rate_pct: float = 20.0
    ltcg_112a_rate_pct: float = 12.5
    ltcg_other_rate_pct: float = 12.5
    ltcg_112a_exemption_inr: float = 125000.0


def load_itr_rates(fy_label: str, config_dir: Path = DEFAULT_CONFIG_DIR) -> ItrRates:
    """Read the optional ``income_tax.itr_rates`` block; fall back to defaults."""
    path = config_dir / f"{fy_label}.yaml"
    raw = yaml.safe_load(path.read_text()) if path.exists() else {}
    block = ((raw or {}).get("income_tax") or {}).get("itr_rates") or {}
    known = ItrRates.__dataclass_fields__
    return ItrRates(**{k: float(v) for k, v in block.items() if k in known})


# ── Surcharge helpers ─────────────────────────────────────────────────────────

def _surcharge_rate_and_cap(total_income: float, config: IncomeTaxConfig) -> tuple[float, float]:
    """(rate_pct, cap_pct) for the band this total income falls in."""
    rate, cap = 0.0, 15.0
    for band in config.surcharge_bands:
        if total_income > band.income_above_inr:
            rate = band.rate_pct
            cap = band.cap_pct_for_capital_gains if band.cap_pct_for_capital_gains is not None else 15.0
        else:
            break
    return rate, cap


def _rebate_87a(eligible_income: float, eligible_tax: float, config: IncomeTaxConfig) -> float:
    """New-regime 87A rebate including marginal relief (Finance Act 2025)."""
    if config.rebate_87a is None:
        return 0.0
    threshold = config.rebate_87a.income_threshold_inr
    maximum = config.rebate_87a.max_rebate_inr
    if eligible_income <= threshold:
        return min(eligible_tax, maximum)
    # Marginal relief: tax cannot exceed the amount by which income exceeds the
    # threshold, so the rebate claws back only the excess.
    excess = eligible_income - threshold
    if eligible_tax > excess:
        return min(eligible_tax - excess, eligible_tax)
    return 0.0


# ── Main computation ──────────────────────────────────────────────────────────

def compute_return_tax(
    buckets: IncomeBuckets,
    fy_label: str,
    regime: str = "new",
    config_dir: Path = DEFAULT_CONFIG_DIR,
) -> ItrTaxComputation:
    if regime != "new":
        raise ValueError("Only the new regime (s.115BAC(1A)) is supported")

    config = load_income_tax_config(fy_label, config_dir)
    rates = load_itr_rates(fy_label, config_dir)

    normal_income = (
        buckets.salary + buckets.other_interest + buckets.dividends + buckets.stcg_slab
    )
    ltcg_112a_taxable = max(0.0, buckets.ltcg_112a - rates.ltcg_112a_exemption_inr)

    # Slab tax on normal income (special-rate gains are excluded from slabs).
    from app.engine.income_tax import compute_slab_tax

    normal_tax, _ = compute_slab_tax(normal_income, config)

    stcg_111a_tax = buckets.stcg_111a * rates.stcg_111a_rate_pct / 100.0
    ltcg_112a_tax = ltcg_112a_taxable * rates.ltcg_112a_rate_pct / 100.0
    ltcg_other_tax = buckets.ltcg_other_12_5 * rates.ltcg_other_rate_pct / 100.0
    special_tax = stcg_111a_tax + ltcg_112a_tax + ltcg_other_tax

    # 87A applies only to the non-special-rate slice of income/tax.
    rebate = _rebate_87a(normal_income, normal_tax, config)
    normal_tax_after_rebate = normal_tax - rebate

    total_income = normal_income + buckets.stcg_111a + buckets.ltcg_112a + buckets.ltcg_other_12_5
    rate, cap = _surcharge_rate_and_cap(total_income, config)
    surcharge = (
        normal_tax_after_rebate * rate / 100.0
        + special_tax * min(rate, cap) / 100.0
    )

    tax_before_cess = normal_tax_after_rebate + special_tax + surcharge
    cess = tax_before_cess * config.cess_pct / 100.0

    return ItrTaxComputation(
        normal_income=normal_income,
        ltcg_112a_taxable=ltcg_112a_taxable,
        normal_tax_inr=normal_tax,
        stcg_111a_tax_inr=stcg_111a_tax,
        ltcg_112a_tax_inr=ltcg_112a_tax,
        ltcg_other_tax_inr=ltcg_other_tax,
        rebate_87a_inr=rebate,
        surcharge_inr=surcharge,
        cess_inr=cess,
        total_tax_inr=tax_before_cess + cess,
    )

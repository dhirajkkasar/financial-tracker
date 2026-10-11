"""
Income tax engine — slab calculation, surcharge, cess, Section 87A rebate.

Config-driven per FY via config/tax_rates/{FY}.yaml `income_tax:` block.
Pure functions, no DB access.

FY 2025-26 new regime:
  0–4L nil, 4–8L 5%, 8–12L 10%, 12–16L 15%, 16–20L 20%, 20–24L 25%, >24L 30%
  Surcharge 10/15/25/37% above ₹50L/₹1Cr/₹2Cr/₹5Cr (capped 15% for capital gains)
  Cess 4%. 87A rebate up to ₹15,000 (income ≤ ₹7L).

FY 2024-25 new regime:
  0–3L nil, 3–7L 5%, 7–10L 10%, 10–12L 15%, 12–15L 20%, >15L 30%
  87A rebate up to ₹12,500 (income ≤ ₹5L).
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


# ── Config dataclasses ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SlabBand:
    up_to_inr: Optional[float]  # None = no upper limit
    rate_pct: float


@dataclass(frozen=True)
class SurchargeBand:
    income_above_inr: float
    rate_pct: float
    cap_pct_for_capital_gains: Optional[float]  # None = no cap


@dataclass(frozen=True)
class Rebate87A:
    income_threshold_inr: float
    max_rebate_inr: float


@dataclass(frozen=True)
class IncomeTaxConfig:
    slabs: list[SlabBand]
    surcharge_bands: list[SurchargeBand]
    cess_pct: float
    rebate_87a: Optional[Rebate87A]


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TaxComputation:
    taxable_income_inr: float
    tax_before_rebate_inr: float
    rebate_87a_inr: float
    tax_after_rebate_inr: float
    surcharge_inr: float
    cess_inr: float
    total_tax_inr: float
    marginal_rate_pct: float


# ── Slab calculation ───────────────────────────────────────────────────────────

def compute_slab_tax(taxable_income: float, config: IncomeTaxConfig) -> tuple[float, float]:
    """
    Compute (tax, marginal_rate_pct) using progressive slabs.
    Marginal rate = rate of the band containing the top of income.
    """
    tax = 0.0
    marginal_rate = 0.0
    prev_cap = 0.0

    for band in config.slabs:
        if band.up_to_inr is None:
            # Top band — no upper limit
            if taxable_income > prev_cap:
                tax += (taxable_income - prev_cap) * band.rate_pct / 100.0
                marginal_rate = band.rate_pct
            break
        if taxable_income <= prev_cap:
            break
        band_top = min(taxable_income, band.up_to_inr)
        tax += (band_top - prev_cap) * band.rate_pct / 100.0
        if taxable_income > prev_cap:
            marginal_rate = band.rate_pct
        prev_cap = band.up_to_inr

    return tax, marginal_rate


# ── Surcharge ──────────────────────────────────────────────────────────────────

def compute_surcharge(
    tax_after_rebate: float,
    total_income: float,
    config: IncomeTaxConfig,
    is_capital_gains: bool = False,
) -> float:
    """
    Compute surcharge on tax.

    is_capital_gains=True caps surcharge at 15% (Section 112A/111A rule).
    """
    applicable_rate = 0.0
    for band in config.surcharge_bands:
        if total_income > band.income_above_inr:
            applicable_rate = band.rate_pct
        else:
            break

    if is_capital_gains and applicable_rate > 0.0:
        # Find the cap for capital gains
        cap = None
        for band in config.surcharge_bands:
            if total_income > band.income_above_inr:
                cap = band.cap_pct_for_capital_gains
            else:
                break
        if cap is not None:
            applicable_rate = min(applicable_rate, cap)

    return tax_after_rebate * applicable_rate / 100.0


# ── Section 87A rebate ────────────────────────────────────────────────────────

def compute_rebate_87a(
    total_income: float,
    tax_before_rebate: float,
    config: IncomeTaxConfig,
) -> float:
    """
    Section 87A rebate: reduces tax to zero if total income ≤ threshold.
    Rebate = min(tax_before_rebate, max_rebate_inr).
    """
    if config.rebate_87a is None:
        return 0.0
    if total_income > config.rebate_87a.income_threshold_inr:
        return 0.0
    return min(tax_before_rebate, config.rebate_87a.max_rebate_inr)


# ── Full computation ───────────────────────────────────────────────────────────

def compute_income_tax(
    total_income_inr: float,
    config: IncomeTaxConfig,
) -> TaxComputation:
    """
    Full income tax computation: slab → 87A rebate → surcharge → cess.
    """
    tax_before_rebate, marginal_rate = compute_slab_tax(total_income_inr, config)
    rebate = compute_rebate_87a(total_income_inr, tax_before_rebate, config)
    tax_after_rebate = tax_before_rebate - rebate
    surcharge = compute_surcharge(tax_after_rebate, total_income_inr, config)
    cess = (tax_after_rebate + surcharge) * config.cess_pct / 100.0
    total_tax = tax_after_rebate + surcharge + cess

    return TaxComputation(
        taxable_income_inr=total_income_inr,
        tax_before_rebate_inr=tax_before_rebate,
        rebate_87a_inr=rebate,
        tax_after_rebate_inr=tax_after_rebate,
        surcharge_inr=surcharge,
        cess_inr=cess,
        total_tax_inr=total_tax,
        marginal_rate_pct=marginal_rate,
    )


def compute_capital_gains_tax(
    cg_tax: float,
    total_income_inr: float,
    config: IncomeTaxConfig,
) -> tuple[float, float, float]:
    """
    Surcharge + cess on capital gains tax (surcharge capped at 15%).

    Returns (surcharge, cess, total_cg_tax).
    """
    surcharge = compute_surcharge(cg_tax, total_income_inr, config, is_capital_gains=True)
    cess = (cg_tax + surcharge) * config.cess_pct / 100.0
    return surcharge, cess, cg_tax + surcharge + cess


# ── Config loading ─────────────────────────────────────────────────────────────

def load_income_tax_config(fy: str, config_dir: Path) -> IncomeTaxConfig:
    """Load income_tax block from config/tax_rates/{FY}.yaml."""
    path = config_dir / f"{fy}.yaml"
    if not path.exists():
        raise ValueError(f"No tax config for FY {fy!r}. Expected file: {path}")
    with open(path) as f:
        raw = yaml.safe_load(f)

    block = raw.get("income_tax")
    if block is None:
        # Fallback: no income tax config — return zero-tax config
        return IncomeTaxConfig(
            slabs=[SlabBand(up_to_inr=None, rate_pct=0.0)],
            surcharge_bands=[],
            cess_pct=0.0,
            rebate_87a=None,
        )

    slabs = [
        SlabBand(
            up_to_inr=s.get("up_to_inr"),
            rate_pct=s["rate_pct"],
        )
        for s in block["slabs"]
    ]
    surcharge_bands = [
        SurchargeBand(
            income_above_inr=s["income_above_inr"],
            rate_pct=s["rate_pct"],
            cap_pct_for_capital_gains=s.get("cap_pct_for_capital_gains"),
        )
        for s in block.get("surcharge", [])
    ]
    rebate_block = block.get("rebate_87a")
    rebate = Rebate87A(
        income_threshold_inr=rebate_block["income_threshold_inr"],
        max_rebate_inr=rebate_block["max_rebate_inr"],
    ) if rebate_block else None

    return IncomeTaxConfig(
        slabs=slabs,
        surcharge_bands=surcharge_bands,
        cess_pct=block.get("cess_pct", 4.0),
        rebate_87a=rebate,
    )

"""Hand-derived new-regime tax computation for FY 2025-26.

Every expected value is computed by hand from the FY slabs in
``app/config/tax_rates/2025-26.yaml`` and the section 87A / 111A / 112A rules.
"""
from pathlib import Path

import pytest

from app.engine.income_tax import load_income_tax_config
from app.engine.itr.tax_compute import IncomeBuckets, compute_return_tax, load_itr_rates

CFG = Path("app/config/tax_rates")


# ── Config pins (the values these computations depend on) ─────────────────────

def test_fy2025_26_new_regime_rebate_is_12L_60k():
    # Finance Act 2025: 87A threshold raised to Rs 12L, max rebate Rs 60,000.
    cfg = load_income_tax_config("2025-26", CFG)
    assert cfg.rebate_87a.income_threshold_inr == 1_200_000
    assert cfg.rebate_87a.max_rebate_inr == 60_000


def test_fy2024_25_new_regime_rebate_is_7L_25k():
    # New-regime rebate for FY 2024-25 was Rs 7L / Rs 25,000 (not the old-regime
    # Rs 5L / Rs 12,500).
    cfg = load_income_tax_config("2024-25", CFG)
    assert cfg.rebate_87a.income_threshold_inr == 700_000
    assert cfg.rebate_87a.max_rebate_inr == 25_000


def test_itr_rates_defaults_cover_112a_exemption():
    rates = load_itr_rates("2025-26", CFG)
    assert rates.stcg_111a_rate_pct == 20.0
    assert rates.ltcg_112a_rate_pct == 12.5
    assert rates.ltcg_112a_exemption_inr == 125_000


# ── Slab + rebate ─────────────────────────────────────────────────────────────

def test_salary_at_the_rebate_ceiling_pays_nothing():
    # Rs 12L normal income → slab tax 20k (4-8L) + 40k (8-12L) = 60k; rebate 60k.
    tax = compute_return_tax(IncomeBuckets(salary=1_200_000), fy_label="2025-26")
    assert tax.normal_tax_inr == 60_000
    assert tax.rebate_87a_inr == 60_000
    assert tax.total_tax_inr == 0.0


def test_salary_above_rebate_pays_slab_tax_plus_cess():
    # Rs 16L: 20k + 40k + 60k (12-16L @15%) = 120k; no rebate; +4% cess.
    tax = compute_return_tax(IncomeBuckets(salary=1_600_000), fy_label="2025-26")
    assert tax.rebate_87a_inr == 0.0
    assert tax.total_tax_inr == 124_800


def test_87a_marginal_relief_just_above_threshold():
    # Rs 12.5L: slab tax 67.5k; marginal relief caps tax at 50k (income - 12L),
    # so the clawed-back rebate is 17.5k; +4% cess on 50k = 2k.
    tax = compute_return_tax(IncomeBuckets(salary=1_250_000), fy_label="2025-26")
    assert tax.rebate_87a_inr == 17_500
    assert tax.total_tax_inr == 52_000


def test_stcg_at_slab_counts_as_normal_income():
    tax = compute_return_tax(IncomeBuckets(stcg_slab=500_000), fy_label="2025-26")
    assert tax.normal_income == 500_000
    assert tax.rebate_87a_inr == 5_000  # wipes the 5% slab tax
    assert tax.total_tax_inr == 0.0


# ── Special rates ─────────────────────────────────────────────────────────────

def test_112a_exemption_and_rate():
    tax = compute_return_tax(IncomeBuckets(ltcg_112a=300_000), fy_label="2025-26")
    assert tax.ltcg_112a_taxable == 175_000
    assert tax.ltcg_112a_tax_inr == 21_875
    assert tax.total_tax_inr == 22_750  # +4% cess


def test_87a_does_not_offset_112a_tax():
    tax = compute_return_tax(
        IncomeBuckets(salary=200_000, ltcg_112a=300_000), fy_label="2025-26"
    )
    assert tax.rebate_87a_inr == 0.0
    assert tax.total_tax_inr == 22_750


def test_rebate_offsets_only_normal_income_not_special_rates():
    # Normal tax 50k is fully rebated (income <= 12L); the 112A tax survives.
    tax = compute_return_tax(
        IncomeBuckets(salary=1_100_000, ltcg_112a=300_000), fy_label="2025-26"
    )
    assert tax.rebate_87a_inr == 50_000
    assert tax.ltcg_112a_tax_inr == 21_875
    assert tax.total_tax_inr == 22_750


def test_stcg_111a_rate():
    tax = compute_return_tax(IncomeBuckets(stcg_111a=100_000), fy_label="2025-26")
    assert tax.stcg_111a_tax_inr == 20_000
    assert tax.total_tax_inr == 20_800


# ── Surcharge ─────────────────────────────────────────────────────────────────

def test_surcharge_10pct_on_normal_income_above_50L():
    # Rs 60L normal: slab tax 13.8L; 10% surcharge (not capped for slab income).
    tax = compute_return_tax(IncomeBuckets(other_interest=6_000_000), fy_label="2025-26")
    assert tax.normal_tax_inr == 1_380_000
    assert tax.rebate_87a_inr == 0.0
    assert tax.surcharge_inr == 138_000
    assert tax.total_tax_inr == 1_578_720  # +4% cess on 15.18L


def test_surcharge_on_capital_gains_capped_at_15pct():
    # Rs 2.5Cr of 12.5% LTCG: band rate is 25% but gains are capped at 15%.
    tax = compute_return_tax(IncomeBuckets(ltcg_other_12_5=25_000_000), fy_label="2025-26")
    assert tax.ltcg_other_tax_inr == 3_125_000
    assert tax.surcharge_inr == 468_750  # 15% of 31.25L
    assert tax.total_tax_inr == 3_737_500


# ── Guard rails ───────────────────────────────────────────────────────────────

def test_old_regime_is_not_supported():
    with pytest.raises(ValueError):
        compute_return_tax(IncomeBuckets(salary=1_000_000), fy_label="2025-26", regime="old")

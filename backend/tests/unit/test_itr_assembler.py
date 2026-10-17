"""Draft assembly: buckets, set-off, tax, 112A tie-out, form selection."""
from app.schemas.itr_models import Form16SummaryIn, ReturnInput
from app.services.itr_assembler import assemble_draft, taxable_salary


def _input(**kw):
    base = dict(
        member_id=1, fy_label="2025-26", ay_label="2026-27",
        salary=[Form16SummaryIn(total_taxable_income=1_200_000.0)],
        other_income={"savings_interest": 10_000.0},
    )
    base.update(kw)
    return ReturnInput(**base)


def _summary(**kw):
    base = {
        "stcg": {"assets": [{"gain": 500_000.0, "is_slab": False}]},
        "ltcg": {"assets": [{
            "gain": 300_000.0, "ltcg_exempt_eligible": True,
            "asset_name": "Reliance", "isin": "INE002A01018",
            "ltcg_lots": [{
                "buy_date": "2023-01-01", "sell_date": "2025-06-01",
                "units": 100.0, "buy_price_per_unit": 500.0,
                "sell_price_per_unit": 800.0, "jan31_2018_price": None,
            }],
        }]},
        "interest": {"assets": [{"interest": 40_000.0}]},
        "carryforward_balances": {"stcl": [], "ltcl": []},
    }
    base.update(kw)
    return base


# ── composition ───────────────────────────────────────────────────────────────

def test_taxable_salary_prefers_total_and_derives_otherwise():
    assert taxable_salary(_input()) == 1_200_000.0
    derived = taxable_salary(_input(salary=[Form16SummaryIn(
        gross_salary=2_000_000.0, exemptions_10=50_000.0,
        standard_deduction=75_000.0, professional_tax=2_500.0,
    )]))
    assert derived == 1_872_500.0


def test_buckets_split_by_rate_class():
    d = assemble_draft(_input(), _summary())
    assert d.buckets["stcg_111a"] == 500_000.0
    assert d.buckets["ltcg_112a"] == 300_000.0
    assert d.buckets["other_interest"] == 50_000.0  # 10k savings + 40k FD
    assert d.buckets["salary"] == 1_200_000.0
    assert d.salary_taxable == 1_200_000.0


def test_tax_is_computed_on_the_buckets():
    d = assemble_draft(_input(), _summary())
    # normal 12.5L -> slab 67.5k, marginal-relief rebate 17.5k -> 50k;
    # 111A 500k @20% = 100k; 112A 175k taxable @12.5% = 21.875k; cess 4% of 171.875k.
    assert d.tax["normal_income"] == 1_250_000.0
    assert d.tax["rebate_87a_inr"] == 17_500.0
    assert d.tax["stcg_111a_tax_inr"] == 100_000.0
    assert d.tax["ltcg_112a_taxable"] == 175_000.0
    assert d.tax["total_tax_inr"] == 178_750.0


def test_112a_schedule_is_built_from_lots():
    d = assemble_draft(_input(), _summary())
    assert len(d.schedule_112a["rows"]) == 1
    row = d.schedule_112a["rows"][0]
    assert row["isin"] == "INNOTREQUIRD"
    assert row["tot_sale_value"] == 80_000
    assert row["cost_acq_without_indx"] == 50_000
    assert row["balance"] == 30_000
    assert d.schedule_112a["balance"] == 30_000


def test_foreign_assets_force_itr2():
    d = assemble_draft(
        _input(foreign={"dividends": 1_000.0, "fa_asset_overrides": [{"country": "US"}]}),
        _summary(),
    )
    assert d.form == "ITR2"
    assert any("Foreign" in r for r in d.form_reasons)


# ── set-off ───────────────────────────────────────────────────────────────────

def test_current_year_stcl_offsets_stcg():
    summary = _summary(stcg={"assets": [
        {"gain": -200_000.0, "is_slab": False},
        {"gain": 500_000.0, "is_slab": False},
    ]})
    d = assemble_draft(_input(), summary)
    assert d.buckets["stcg_111a"] == 300_000.0
    assert d.setoff["stcl_on_stcg"] == 200_000.0
    assert d.carryforward["created_this_year"]["stcl"] == 0.0


def test_unabsorbed_loss_becomes_carry_forward():
    summary = _summary(
        stcg={"assets": [{"gain": -200_000.0, "is_slab": False}]},
        ltcg={"assets": []},
    )
    d = assemble_draft(_input(), summary)
    assert d.buckets["stcg_111a"] == 0.0
    assert d.carryforward["created_this_year"]["stcl"] == 200_000.0
    assert d.form == "ITR2"   # carry-forward forces ITR-2


def test_brought_forward_loss_is_applied():
    summary = _summary(carryforward_balances={
        "stcl": [{"fy_label": "2024-25", "remaining_inr": 100_000.0,
                  "expires_fy_label": "2031-32"}],
        "ltcl": [],
    })
    d = assemble_draft(_input(), summary)
    assert d.setoff["cf_stcl_used"] == 100_000.0
    assert d.buckets["stcg_111a"] == 400_000.0
    assert d.carryforward["brought_forward"]["stcl"] == 100_000.0


# ── warnings ──────────────────────────────────────────────────────────────────

def test_missing_fmv_for_pre_2018_lot_warns():
    summary = _summary(ltcg={"assets": [{
        "gain": 100_000.0, "ltcg_exempt_eligible": True,
        "asset_name": "Old Co", "isin": "INE002A01018",
        "ltcg_lots": [{
            "buy_date": "2017-01-01", "sell_date": "2025-06-01",
            "units": 100.0, "buy_price_per_unit": 100.0,
            "sell_price_per_unit": 200.0, "jan31_2018_price": None,
        }],
    }]})
    d = assemble_draft(_input(), summary)
    assert any("FMV" in w for w in d.warnings)


def test_no_form16_warns():
    d = assemble_draft(_input(salary=[]), _summary())
    assert any("Form 16" in w for w in d.warnings)


def test_plain_salary_is_itr1():
    d = assemble_draft(
        _input(),
        {"stcg": {"assets": []}, "ltcg": {"assets": []},
         "interest": {"assets": []}, "carryforward_balances": {"stcl": [], "ltcl": []}},
    )
    assert d.form == "ITR1"

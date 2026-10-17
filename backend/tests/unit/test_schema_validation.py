"""Validation module: structural (schema) + semantic (tie-out) checks."""
import copy
from dataclasses import asdict
from datetime import date

from app.engine.itr.builders import get_builder
from app.engine.itr.schedule_112a import Schedule112ALot, build_schedule_112a
from app.engine.itr.schema_validation import validate_itr_json
from app.engine.itr.tax_compute import IncomeBuckets, compute_return_tax
from app.schemas.itr_models import Form16SummaryIn, ReturnInput
from app.services.itr_assembler import ReturnDraft


def _valid_doc() -> dict:
    lots = [Schedule112ALot(
        isin="INE002A01018", name="Reliance Industries", units=100.0,
        buy_date=date(2023, 1, 10), cost_per_unit=1500.0, sale_price_per_unit=2000.0,
    )]
    schedule = build_schedule_112a(lots)
    buckets = IncomeBuckets(
        salary=1_000_000.0, other_interest=10_000.0, dividends=5_000.0,
        stcg_111a=50_000.0, ltcg_112a=float(schedule.balance),
    )
    tax = compute_return_tax(buckets, "2025-26")
    draft = ReturnDraft(
        member_id=1, fy_label="2025-26", ay_label="2026-27", form="ITR2",
        form_reasons=[], salary_taxable=1_000_000.0,
        buckets=asdict(buckets),
        gross={
            "stcg_111a": 50_000.0, "stcg_slab": 0.0, "ltcg_112a": float(schedule.balance),
            "ltcg_other_12_5": 0.0, "stcg_loss": 0.0, "ltcg_loss": 0.0,
        },
        tax=asdict(tax), schedule_112a=asdict(schedule),
        setoff={}, carryforward={}, warnings=[],
    )
    inp = ReturnInput(
        member_id=1, fy_label="2025-26", ay_label="2026-27",
        pan="ABCPE1234F", name="Test Taxpayer", dob="1990-01-01",
        salary=[Form16SummaryIn(
            employer_name="Acme", gross_salary=1_000_000.0,
            standard_deduction=0.0, total_taxable_income=1_000_000.0,
        )],
        other_income={"savings_interest": 10_000.0, "dividends": 5_000.0},
    )
    return get_builder("ITR-2", "2026-27").build(draft, inp)


def _body(doc: dict) -> dict:
    return doc["ITR"]["ITR2"]


def test_valid_builder_document_passes():
    report = validate_itr_json(_valid_doc(), "2026-27")
    assert report.ok, report.render()


def test_report_exposes_ok_and_renders_issues():
    report = validate_itr_json(_valid_doc(), "2026-27")
    assert report.ok
    assert report.render() == ""


def test_camel_case_hp_block_fails_schema():
    doc = _valid_doc()
    _body(doc)["ScheduleHP"] = {"rentalIncome": 1}
    report = validate_itr_json(doc, "2026-27")
    assert not report.ok
    assert any(i.rule == "schema" for i in report.issues)


def test_totals_only_schedule_fails_semantic_audit():
    doc = _valid_doc()
    del _body(doc)["ScheduleS"]["Salaries"]   # keep the non-zero salary total
    report = validate_itr_json(doc, "2026-27")
    assert not report.ok
    assert any(
        i.rule == "semantic" and i.path == "ScheduleS.TotIncUnderHeadSalaries"
        for i in report.issues
    )


def test_cg_b3a_tie_break_fails():
    doc = _valid_doc()
    b3a = _body(doc)["ScheduleCGFor23"]["LongTermCapGain23"]["SaleOfEquityShareUs112A"]
    b3a["BalanceCG"] = b3a["BalanceCG"] + 1
    report = validate_itr_json(doc, "2026-27")
    assert not report.ok
    assert any("rule 134" in i.message for i in report.issues)


def test_cfl_bfla_tie_break_fails():
    doc = _valid_doc()
    detail = _body(doc)["ScheduleCFL"]["TotalOfBFLossesEarlierYrs"]["LossSummaryDetail"]
    detail["TotalSTCGPTILossCF"] = 5_000          # Schedule BFLA still zero
    report = validate_itr_json(doc, "2026-27")
    assert not report.ok
    assert any("rules 234/235" in i.message for i in report.issues)


def test_schedule_fa_required_when_assets_outside_india():
    doc = _valid_doc()
    _body(doc)["PartB_TTI"]["AssetOutIndiaFlag"] = "YES"
    report = validate_itr_json(doc, "2026-27")
    assert not report.ok
    assert any("ScheduleFA" in i.message for i in report.issues)

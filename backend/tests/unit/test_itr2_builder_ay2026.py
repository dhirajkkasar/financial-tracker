"""ITR-2 AY 2026-27 builder — metadata, personal info, salary, other income."""
from datetime import date

import pytest
from jsonschema import Draft4Validator

from app.engine.itr.builders import UnsupportedFormError, get_builder
from app.engine.itr.schema_loader import load_itr_schema
from app.schemas.itr_models import Form16SummaryIn, ReturnInput
from app.services.itr_assembler import ReturnDraft


def _draft(**kw):
    base = dict(
        member_id=1, fy_label="2025-26", ay_label="2026-27", form="ITR2",
        form_reasons=[], salary_taxable=0.0,
        buckets={"other_interest": 10_000.0, "dividends": 5_000.0},
        gross={}, tax={},
        schedule_112a={}, setoff={}, carryforward={}, warnings=[],
    )
    base.update(kw)
    return ReturnDraft(**base)


def _input(**kw):
    base = dict(
        member_id=1, fy_label="2025-26", ay_label="2026-27",
        pan="ABCPE1234F", name="Test Taxpayer", dob="1990-01-01",
        address={
            "line1": "1 Example Road", "line2": "Example Area", "city": "Pune",
            "state_code": "27", "email": "taxpayer@example.com", "mobile": "9876543210",
        },
        salary=[Form16SummaryIn(
            employer_name="Acme Technologies", employer_tan="ZZZZ00000Z",
            employer_address="Acme Park, Pune", gross_salary=2_000_000.0,
            exemptions_10=50_000.0, standard_deduction=75_000.0,
            professional_tax=2_500.0,
        )],
        other_income={"savings_interest": 10_000.0, "dividends": 5_000.0},
        verification={"name": "Test Taxpayer", "father_name": "Test Father", "capacity": "S"},
    )
    base.update(kw)
    return ReturnInput(**base)


def _build(doc_input=None, draft=None, generated_on=None):
    builder = get_builder("ITR-2", "2026-27")
    return builder.build(draft or _draft(), doc_input or _input(), generated_on=generated_on)


def _assert_schema_valid(doc):
    schema = load_itr_schema("2026-27", "ITR-2")
    errors = sorted(Draft4Validator(schema).iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors[:10])


# ── registry ──────────────────────────────────────────────────────────────────

def test_registry_resolves_itr2_ay2026():
    builder = get_builder("ITR-2", "2026-27")
    assert builder.form == "ITR-2"
    assert builder.ay_label == "2026-27"


def test_unknown_form_raises():
    with pytest.raises(UnsupportedFormError):
        get_builder("ITR-9", "2026-27")


# ── document shape ────────────────────────────────────────────────────────────

def test_document_is_schema_valid():
    doc = _build()
    assert set(doc.keys()) == {"ITR"}
    assert set(doc["ITR"].keys()) == {"ITR2"}
    _assert_schema_valid(doc)


def test_form_constants_are_the_literal_schema_values():
    f = _build()["ITR"]["ITR2"]["Form_ITR2"]
    assert f["FormName"] == "ITR-2"
    assert f["AssessmentYear"] == "2026"
    assert f["SchemaVer"] == "Ver1.0"
    assert f["FormVer"] == "Ver1.0"


def test_creation_info_is_pattern_valid_and_dated_after_ay_open():
    body = _build(generated_on=date(2026, 2, 1))["ITR"]["ITR2"]
    ci = body["CreationInfo"]
    assert ci["SWCreatedBy"] == "SW00000000"
    # A date before 2026-04-01 is clamped forward to the AY's opening date.
    assert ci["JSONCreationDate"] >= "2026-04-01"


def test_personal_info_carries_identity():
    pi = _build()["ITR"]["ITR2"]["PartA_GEN1"]["PersonalInfo"]
    assert pi["PAN"] == "ABCPE1234F"
    assert pi["AssesseeName"]["SurNameOrOrgName"] == "Test Taxpayer"
    assert pi["Address"]["StateCode"] == "27"
    assert pi["Address"]["EmailAddress"] == "taxpayer@example.com"


def test_filing_status_defaults_to_new_regime():
    fs = _build()["ITR"]["ITR2"]["PartA_GEN1"]["FilingStatus"]
    assert fs["OptOutNewTaxRegime"] == "N"
    assert fs["ResidentialStatus"] == "RES"


def test_verification_declaration_has_name_and_pan():
    decl = _build()["ITR"]["ITR2"]["Verification"]["Declaration"]
    assert decl["AssesseeVerName"] == "Test Taxpayer"
    assert decl["FatherName"] == "Test Father"
    assert decl["AssesseeVerPAN"] == "ABCPE1234F"


# ── Schedule S ────────────────────────────────────────────────────────────────

def test_schedule_s_is_itemised_not_totals_only():
    s = _build()["ITR"]["ITR2"]["ScheduleS"]
    assert len(s["Salaries"]) == 1
    row = s["Salaries"][0]
    assert row["NameOfEmployer"] == "Acme Technologies"
    assert row["Salarys"]["GrossSalary"] == 2_000_000
    assert s["TotalGrossSalary"] == 2_000_000
    assert s["AllwncExtentExemptUs10"] == 50_000
    assert s["NetSalary"] == 1_950_000
    assert s["DeductionUnderSection16ia"] == 75_000
    assert s["ProfessionalTaxUs16iii"] == 2_500
    assert s["TotIncUnderHeadSalaries"] == 1_872_500


def test_no_salary_omits_schedule_s_but_stays_valid():
    doc = _build(_input(salary=[]))
    assert "ScheduleS" not in doc["ITR"]["ITR2"]
    _assert_schema_valid(doc)


# ── Schedule OS ───────────────────────────────────────────────────────────────

def test_schedule_os_carries_interest_and_dividends():
    os_sched = _build()["ITR"]["ITR2"]["ScheduleOS"]
    other = os_sched["IncOthThanOwnRaceHorse"]
    assert other["IntrstFrmSavingBank"] == 10_000
    assert other["DividendGross"] == 5_000
    assert other["BalanceNoRaceHorse"] == 15_000
    assert os_sched["IncChargeable"] == 15_000


# ── capital gains, 112A, SI, Part B, CFL ──────────────────────────────────────

def _rich_draft(**overrides):
    from dataclasses import asdict

    from app.engine.itr.schedule_112a import Schedule112ALot, build_schedule_112a
    from app.engine.itr.tax_compute import IncomeBuckets, compute_return_tax

    lots = [Schedule112ALot(
        isin="INE002A01018", name="Reliance Industries", units=100.0,
        buy_date=date(2023, 1, 10), cost_per_unit=1500.0, sale_price_per_unit=2000.0,
    )]
    schedule = build_schedule_112a(lots)  # balance = 100 x (2000 - 1500) = 50,000
    buckets = IncomeBuckets(
        salary=1_872_500.0, other_interest=10_000.0, dividends=5_000.0,
        stcg_111a=100_000.0, ltcg_112a=float(schedule.balance),
    )
    tax = compute_return_tax(buckets, "2025-26")
    base = dict(
        salary_taxable=1_872_500.0,
        buckets=asdict(buckets),
        gross={
            "stcg_111a": 100_000.0, "stcg_slab": 0.0,
            "ltcg_112a": float(schedule.balance), "ltcg_other_12_5": 0.0,
            "stcg_loss": 0.0, "ltcg_loss": 0.0,
        },
        tax=asdict(tax),
        schedule_112a=asdict(schedule),
        setoff={"stcl_on_stcg": 0.0, "stcl_on_ltcg": 0.0, "ltcl_on_ltcg": 0.0,
                "cf_stcl_used": 0.0, "cf_ltcl_used": 0.0},
        carryforward={"brought_forward": {"stcl": 0.0, "ltcl": 0.0},
                      "created_this_year": {"stcl": 0.0, "ltcl": 0.0}},
    )
    base.update(overrides)
    return _draft(**base), tax


def test_schedule_cg_is_itemised_with_stcg_111a_and_ltcg_112a():
    draft, _ = _rich_draft()
    cg = _build(draft=draft)["ITR"]["ITR2"]["ScheduleCGFor23"]

    stcg_row = cg["ShortTermCapGainFor23"]["EquityMFonSTT"][0]
    assert stcg_row["MFSectionCode"] == "1A"
    assert stcg_row["EquityMFonSTTDtls"]["BalanceCG"] == 100_000
    assert cg["ShortTermCapGainFor23"]["TotalSTCG"] == 100_000

    lt = cg["LongTermCapGain23"]
    assert lt["SaleOfEquityShareUs112A"]["BalanceCG"] == 50_000
    assert lt["TotalLTCG"] == 50_000
    assert cg["SumOfCGIncm"] == 150_000
    assert cg["TotScheduleCGFor23"] == 150_000


def test_cg_b3a_ties_to_schedule_112a_col14_total():
    draft, _ = _rich_draft()
    body = _build(draft=draft)["ITR"]["ITR2"]
    b3a = body["ScheduleCGFor23"]["LongTermCapGain23"]["SaleOfEquityShareUs112A"]["BalanceCG"]
    assert b3a == body["Schedule112A"]["Balance112A"] == body["Schedule112A"]["TotalBalance112A"]


def test_schedule_112a_rows_and_totals_sum():
    draft, _ = _rich_draft()
    s = _build(draft=draft)["ITR"]["ITR2"]["Schedule112A"]
    assert len(s["Schedule112ADtls"]) == 1
    row = s["Schedule112ADtls"][0]
    assert row["ShareOnOrBefore"] == "AE"
    assert row["ISINCode"] == "INNOTREQUIRD"
    assert row["TotSaleValue"] == 200_000
    assert row["Balance"] == 50_000
    assert s["Balance112A"] == sum(r["Balance"] for r in s["Schedule112ADtls"])


def test_schedule_si_carries_special_rate_income():
    draft, _ = _rich_draft()
    si = _build(draft=draft)["ITR"]["ITR2"]["ScheduleSI"]
    by_code = {l["SecCode"]: l for l in si["SplCodeRateTax"]}
    assert by_code["1A"]["SplRateInc"] == 100_000
    assert by_code["1A"]["SplRateIncTax"] == 20_000
    assert si["TotSplRateInc"] == 100_000
    assert si["TotSplRateIncTax"] == 20_000


def test_part_b_ti_carries_gross_gains_and_ties_to_net():
    draft, _ = _rich_draft()
    ti = _build(draft=draft)["ITR"]["ITR2"]["PartB-TI"]
    assert ti["CapGain"]["TotalCapGains"] == 150_000          # gross, before set-off
    assert ti["CurrentYearLoss"] == 0
    assert ti["GrossTotalIncome"] == 1_872_500 + 15_000 + 150_000
    assert ti["TotalIncome"] == ti["GrossTotalIncome"]
    assert ti["IncChargeTaxSplRate111A112"] == 100_000        # 112A below the 1.25L exemption


def test_part_b_tti_recomputes_to_the_same_total_as_tax_compute():
    draft, tax = _rich_draft()
    tti = _build(draft=draft)["ITR"]["ITR2"]["PartB_TTI"]
    assert tti["TotalTaxPayablDeemedTotInc"] == round(tax.total_tax_inr)
    ctl = tti["ComputationOfTaxLiability"]
    assert ctl["TaxPayableOnTI"]["TaxPayableOnTotInc"] == round(tax.normal_tax_inr) + round(
        tax.stcg_111a_tax_inr + tax.ltcg_112a_tax_inr + tax.ltcg_other_tax_inr
    )
    assert tti["AssetOutIndiaFlag"] == "NO"


def test_part_b_ti_current_year_loss_reduces_gross_total_income():
    draft, _ = _rich_draft(
        setoff={"stcl_on_stcg": 30_000.0, "stcl_on_ltcg": 0.0, "ltcl_on_ltcg": 0.0,
                "cf_stcl_used": 0.0, "cf_ltcl_used": 0.0},
    )
    ti = _build(draft=draft)["ITR"]["ITR2"]["PartB-TI"]
    assert ti["CurrentYearLoss"] == 30_000
    assert ti["BalanceAfterSetoffLosses"] == ti["TotalTI"] - 30_000
    assert ti["GrossTotalIncome"] == ti["BalanceAfterSetoffLosses"]


def test_schedule_cfl_reports_carried_forward_losses():
    draft, _ = _rich_draft(
        carryforward={"brought_forward": {"stcl": 5_000.0, "ltcl": 0.0},
                      "created_this_year": {"stcl": 20_000.0, "ltcl": 7_000.0}},
    )
    cfl = _build(draft=draft)["ITR"]["ITR2"]["ScheduleCFL"]
    assert cfl["TotalLossCFSummary"]["LossSummaryDetail"]["TotalSTCGPTILossCF"] == 20_000
    assert cfl["TotalLossCFSummary"]["LossSummaryDetail"]["TotalLTCGPTILossCF"] == 7_000
    assert cfl["TotalOfBFLossesEarlierYrs"]["LossSummaryDetail"]["TotalSTCGPTILossCF"] == 5_000


def test_full_cg_document_is_schema_valid():
    draft, _ = _rich_draft()
    _assert_schema_valid(_build(draft=draft))


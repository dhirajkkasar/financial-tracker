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
        form_reasons=[], salary_taxable=0.0, buckets={}, tax={},
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

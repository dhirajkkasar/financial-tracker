"""Golden end-to-end: seed portfolio + Form 16 -> assemble -> generate -> JSON.

This is the milestone-1 acceptance test. It drives the whole flow over HTTP and
then asserts the *generated ITR-2 JSON* — not an intermediate draft — against
hand-derived figures (``tests/fixtures/itr_golden_portfolio.py``). If any stage
drifts, the numbers stop tying.
"""
import pytest

from app.engine.itr.schema_validation import validate_itr_json
from tests.factories import make_member
from tests.fixtures import itr_golden_portfolio as golden

FY = golden.FY


def _member(db):
    return make_member(db, pan=golden.PAN, name=golden.NAME)


def _prepared(client, member_id):
    return client.post(
        "/itr/returns", json={"member_id": member_id, "fy": FY}
    ).json()


def _upload_form16(client, return_id):
    resp = client.post(
        f"/itr/returns/{return_id}/form16",
        files={"file": ("form16.pdf", golden.form16_pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _update_input(client, return_id):
    resp = client.put(f"/itr/returns/{return_id}/input", json={
        "other_income": {"savings_interest": golden.SAVINGS_INTEREST},
        "address": {
            "line1": "1 Example Road", "city": "Pune", "state_code": "27",
            "pin": 411002, "mobile": "9876543210", "email": "taxpayer@example.com",
        },
        "dob": "1990-05-15",
        "verification": {"father_name": "Test Father", "capacity": "S"},
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def _prepare_and_assemble(client, db):
    m = _member(db)
    golden.seed(db, m.id)
    r = _prepared(client, m.id)
    assert _upload_form16(client, r["id"])["warnings"] == []
    _update_input(client, r["id"])
    draft = client.post(f"/itr/returns/{r['id']}/assemble")
    assert draft.status_code == 200, draft.text
    return r["id"], draft.json()


def test_form16_and_portfolio_assemble_to_the_hand_derived_draft(client, db):
    _, draft = _prepare_and_assemble(client, db)

    assert draft["form"] == "ITR2"  # STCG 111A / LTCG force ITR-2
    assert draft["warnings"] == []

    assert draft["salary_taxable"] == pytest.approx(golden.TAXABLE_SALARY)
    assert draft["buckets"]["other_interest"] == pytest.approx(golden.OTHER_INTEREST)
    assert draft["buckets"]["stcg_111a"] == pytest.approx(golden.STCG_111A)
    assert draft["buckets"]["ltcg_112a"] == pytest.approx(golden.LTCG_112A)
    assert draft["buckets"]["ltcg_other_12_5"] == pytest.approx(golden.LTCG_OTHER)

    assert draft["gross"]["stcg_111a"] == pytest.approx(golden.STCG_111A)
    assert draft["gross"]["ltcg_112a"] == pytest.approx(golden.LTCG_112A)
    assert draft["gross"]["ltcg_other_12_5"] == pytest.approx(golden.LTCG_OTHER)

    assert draft["tax"]["normal_income"] == pytest.approx(golden.NORMAL_INCOME)
    assert draft["tax"]["ltcg_112a_taxable"] == pytest.approx(golden.LTCG_112A_TAXABLE)
    assert draft["tax"]["normal_tax_inr"] == pytest.approx(golden.NORMAL_TAX)
    assert draft["tax"]["stcg_111a_tax_inr"] == pytest.approx(golden.STCG_111A_TAX)
    assert draft["tax"]["ltcg_112a_tax_inr"] == pytest.approx(golden.LTCG_112A_TAX)
    assert draft["tax"]["ltcg_other_tax_inr"] == pytest.approx(golden.LTCG_OTHER_TAX)
    assert draft["tax"]["rebate_87a_inr"] == 0.0  # income is far above Rs 12L
    assert draft["tax"]["cess_inr"] == pytest.approx(golden.CESS)
    assert draft["tax"]["total_tax_inr"] == pytest.approx(golden.TOTAL_TAX)

    assert draft["schedule_112a"]["balance"] == golden.LTCG_112A


def test_generated_json_is_schema_valid_and_carries_the_hand_derived_figures(client, db):
    return_id, _ = _prepare_and_assemble(client, db)

    report = client.get(f"/itr/returns/{return_id}/validation").json()
    assert report["ok"] is True, report
    assert report["issues"] == []

    generated = client.post(f"/itr/returns/{return_id}/generate")
    assert generated.status_code == 200, generated.text
    assert generated.json()["status"] == "generated"

    download = client.get(f"/itr/returns/{return_id}/json")
    assert download.status_code == 200
    assert "Common Offline Utility" in download.headers["x-import-with"]
    doc = download.json()

    # Belt and braces: the very same validator the generator used, re-run here.
    assert validate_itr_json(doc, "2026-27", "ITR-2").ok is True

    body = doc["ITR"]["ITR2"]
    assert body["Form_ITR2"]["FormName"] == "ITR-2"
    assert body["Form_ITR2"]["AssessmentYear"] == "2026"

    # ── Schedule S (salary) ───────────────────────────────────────────────────
    sal = body["ScheduleS"]
    assert sal["TotalGrossSalary"] == golden.GROSS_SALARY
    assert sal["AllwncExtentExemptUs10"] == golden.EXEMPTIONS_10
    assert sal["DeductionUnderSection16ia"] == golden.STANDARD_DEDUCTION
    assert sal["TotIncUnderHeadSalaries"] == golden.TAXABLE_SALARY

    # ── Schedule OS (other source) ────────────────────────────────────────────
    oth = body["ScheduleOS"]["IncOthThanOwnRaceHorse"]
    assert oth["IntrstFrmSavingBank"] == golden.SAVINGS_INTEREST
    assert oth["IntrstFrmTermDeposit"] == golden.FD_INTEREST
    assert oth["InterestGross"] == golden.OTHER_INTEREST
    assert body["ScheduleOS"]["TotOthSrcNoRaceHorse"] == golden.OTHER_INTEREST

    # ── Schedule CG ───────────────────────────────────────────────────────────
    cg = body["ScheduleCGFor23"]
    assert cg["ShortTermCapGainFor23"]["EquityMFonSTT"][0]["EquityMFonSTTDtls"]["BalanceCG"] \
        == golden.STCG_111A
    assert cg["ShortTermCapGainFor23"]["TotalSTCG"] == golden.STCG_111A
    assert cg["LongTermCapGain23"]["SaleOfEquityShareUs112A"]["BalanceCG"] \
        == golden.LTCG_112A
    assert cg["LongTermCapGain23"]["SaleofAssetNADtls"]["SaleofAssetNA"]["BalanceCG"] \
        == golden.LTCG_OTHER
    assert cg["LongTermCapGain23"]["TotalLTCG"] == golden.LTCG_TOTAL
    assert cg["SumOfCGIncm"] == golden.CG_GROSS

    # ── Schedule 112A (scrip-wise, bought after 31-Jan-2018 -> one "AE" row) ──
    rows = body["Schedule112A"]["Schedule112ADtls"]
    assert len(rows) == 1
    row = rows[0]
    assert row["ShareOnOrBefore"] == "AE"
    assert row["NumSharesUnits"] == golden.LTCG_112A_UNITS
    assert row["TotSaleValue"] == golden.LTCG_112A_SALE_VALUE
    assert row["AcquisitionCost"] == golden.LTCG_112A_COST
    assert row["Balance"] == golden.LTCG_112A
    assert body["Schedule112A"]["TotalBalance112A"] == golden.LTCG_112A

    # ── Schedule SI (special rates; the 1.25L exemption is claimed here) ──────
    si = {l["SecCode"]: l for l in body["ScheduleSI"]["SplCodeRateTax"]}
    assert si["1A"]["SplRateInc"] == golden.STCG_111A               # 111A @ 20%
    assert si["2A"]["SplRateInc"] == golden.LTCG_112A_TAXABLE       # 112A @ 12.5%
    assert si["21"]["SplRateInc"] == golden.LTCG_OTHER              # other LTCG @ 12.5%
    assert body["ScheduleSI"]["TotSplRateIncTax"] == golden.SPECIAL_TAX

    # ── Part B-TI / Part B-TTI ────────────────────────────────────────────────
    ti = body["PartB-TI"]
    assert ti["Salaries"] == golden.TAXABLE_SALARY
    assert ti["CapGain"]["ShortTermLongTermTotal"] == golden.CG_GROSS
    assert ti["IncFromOS"]["TotIncFromOS"] == golden.OTHER_INTEREST
    assert ti["TotalTI"] == golden.TOTAL_INCOME
    assert ti["TotalIncome"] == golden.TOTAL_INCOME
    assert ti["IncChargeTaxSplRate111A112"] == golden.STCG_111A + golden.LTCG_112A_TAXABLE
    assert ti["LossesOfCurrentYearCarriedFwd"] == 0

    tti = body["PartB_TTI"]
    assert tti["AssetOutIndiaFlag"] == "NO"  # no foreign-asset declaration this year
    tax_liability = tti["ComputationOfTaxLiability"]
    assert tax_liability["TaxPayableOnTI"]["TaxAtNormalRatesOnAggrInc"] == golden.NORMAL_TAX
    assert tax_liability["TaxPayableOnTI"]["TaxAtSpecialRates"] == golden.SPECIAL_TAX
    assert tax_liability["Rebate87A"] == 0
    assert tti["HealthEduCess"] == golden.CESS
    assert tti["TotalTaxPayablDeemedTotInc"] == golden.TOTAL_TAX
    assert tti["Refund"]["RefundDue"] == golden.REFUND

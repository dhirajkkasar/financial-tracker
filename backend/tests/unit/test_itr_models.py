"""Per-year ITR input document (ReturnInput) and its nested models."""
import pytest
from pydantic import ValidationError

from app.schemas.itr_models import Form16SummaryIn, ReturnInput


def test_return_input_minimal_defaults():
    ri = ReturnInput(member_id=1, fy_label="2025-26", ay_label="2026-27")
    assert ri.regime == "new"
    assert ri.residential_status == "RES"
    assert ri.salary == []
    assert ri.bank_accounts == []
    assert ri.other_income.savings_interest == 0.0


def test_return_input_rejects_bad_regime():
    with pytest.raises(ValidationError):
        ReturnInput(member_id=1, fy_label="2025-26", ay_label="2026-27", regime="flat")


def test_return_input_rejects_bad_residential_status():
    # The ITR-2 schema enum is RES/NRI/NOR — not "NR"/"RNOR".
    with pytest.raises(ValidationError):
        ReturnInput(
            member_id=1, fy_label="2025-26", ay_label="2026-27",
            residential_status="NR",
        )


def test_return_input_accepts_schema_residential_status():
    ri = ReturnInput(
        member_id=1, fy_label="2025-26", ay_label="2026-27",
        residential_status="NOR",
    )
    assert ri.residential_status == "NOR"


def test_form16_summary_roundtrip():
    f = Form16SummaryIn(
        employer_name="ACME", employer_tan="BLRA05499E",
        employee_pan="ABCDE1234F", gross_salary=1200000.0, tds=90000.0,
    )
    assert f.model_dump()["gross_salary"] == 1200000.0
    assert f.warnings == []


def test_return_input_serialises_and_reparses():
    ri = ReturnInput(
        member_id=1, fy_label="2025-26", ay_label="2026-27",
        other_income={"savings_interest": 5000.0},
    )
    again = ReturnInput.model_validate(ri.model_dump(mode="json"))
    assert again.other_income.savings_interest == 5000.0


def test_bank_account_refund_flag_defaults_false():
    ri = ReturnInput(
        member_id=1, fy_label="2025-26", ay_label="2026-27",
        bank_accounts=[{"bank_name": "HDFC", "account_number": "123", "ifsc": "HDFC0001"}],
    )
    assert ri.bank_accounts[0].is_refund_account is False

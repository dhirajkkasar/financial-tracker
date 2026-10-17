"""Deterministic Form 16 text parser (Part A identity + Part B salary)."""
from pathlib import Path

from app.engine.form16_parser import parse_form16_text

FIX = Path(__file__).parent.parent / "fixtures" / "form16_sample.txt"


def test_parses_identity():
    summary = parse_form16_text(FIX.read_text())
    assert summary.employer_tan == "ZZZZ00000Z"
    assert summary.employee_pan == "ABCDE1234F"


def test_parses_salary_and_tds():
    summary = parse_form16_text(FIX.read_text())
    assert summary.gross_salary == 2000000.0
    assert summary.tds == 250000.0


def test_parses_part_b_components():
    summary = parse_form16_text(FIX.read_text())
    assert summary.exemptions_10 == 50000.0
    assert summary.standard_deduction == 75000.0
    assert summary.professional_tax == 2500.0
    assert summary.total_taxable_income == 1872500.0


def test_parses_period():
    summary = parse_form16_text(FIX.read_text())
    assert summary.period_from == "2025-04-01"
    assert summary.period_to == "2026-03-31"


def test_missing_fields_are_warned_not_silently_zeroed():
    summary = parse_form16_text("employer name: ACME\n")
    assert summary.warnings
    assert summary.gross_salary == 0.0


def test_parse_is_deterministic():
    text = FIX.read_text()
    assert parse_form16_text(text).model_dump() == parse_form16_text(text).model_dump()


def test_handles_blank_and_zero_values():
    summary = parse_form16_text("Perquisites\n0\nGross Salary\n1,00,000.00\n")
    assert summary.perquisites == 0.0
    assert summary.gross_salary == 100000.0


def test_clean_form_has_no_salary_warnings():
    summary = parse_form16_text(FIX.read_text())
    assert summary.warnings == []

"""Form 16 PDF extraction — the PDF path must agree with the text path."""
from pathlib import Path

from fpdf import FPDF

from app.engine.form16_parser import parse_form16_pdf

FIX = Path(__file__).parent.parent / "fixtures" / "form16_sample.txt"


def _pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in text.splitlines():
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_parse_pdf_matches_text_path():
    summary = parse_form16_pdf(_pdf_bytes(FIX.read_text()))
    assert summary.employer_tan == "ZZZZ00000Z"
    assert summary.employee_pan == "ABCDE1234F"
    assert summary.gross_salary == 2000000.0
    assert summary.tds == 250000.0


def test_parse_pdf_has_no_warnings_for_complete_form():
    summary = parse_form16_pdf(_pdf_bytes(FIX.read_text()))
    assert summary.warnings == []


def test_parse_pdf_is_total_on_junk_bytes():
    # A non-PDF payload must fail loudly rather than yield a bogus summary.
    import pytest

    with pytest.raises(Exception):
        parse_form16_pdf(b"not a pdf at all")

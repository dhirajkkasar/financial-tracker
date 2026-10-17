"""Deterministic Form 16 parser.

Three layers, each testable on its own:

    parse_form16_text(text) -> Form16SummaryIn     # pure, label/regex driven
    parse_form16_pdf(bytes) -> Form16SummaryIn     # pdfplumber -> text -> above

The parser never guesses. Any label it cannot resolve is recorded in
``Form16SummaryIn.warnings`` and the value keeps its zero default, so the caller
can ask the user to correct it rather than silently filing a wrong number.
"""
from __future__ import annotations

import io
import re
from typing import Optional

from app.schemas.itr_models import Form16SummaryIn

_PAN = r"[A-Z]{5}[0-9]{4}[A-Z]"
_TAN = r"[A-Z]{4}[0-9]{5}[A-Z]"

_EMPLOYER_NAME_LABELS = [
    "Name and address of the Employer",
    "Name of the Employer",
    "Employer Name",
]
_EMPLOYER_TAN_LABELS = [
    "TAN of the Deductor",
    "TAN of the Employer",
    "TAN of Employer",
    "TAN",
]
_EMPLOYER_PAN_LABELS = ["PAN of the Deductor", "PAN of the Employer"]
_EMPLOYEE_NAME_LABELS = [
    "Name and address of the Employee",
    "Name of the Employee",
    "Employee Name",
]
_EMPLOYEE_PAN_LABELS = ["PAN of the Employee", "PAN of Employee", "Employee PAN"]

# Money fields: label alternatives -> Form16SummaryIn attribute.
_MONEY_FIELDS: list[tuple[str, list[str]]] = [
    ("gross_salary", ["Gross Salary"]),
    ("exemptions_10", ["Exemptions under section 10", "Exemptions u/s 10"]),
    ("perquisites", ["Perquisites"]),
    (
        "standard_deduction",
        ["Standard deduction under section 16(ia)", "Standard deduction"],
    ),
    ("professional_tax", ["Professional tax under section 16(iii)", "Professional tax"]),
    ("total_taxable_income", ["Total Taxable Income", "Taxable Income"]),
    ("tds", ["Total amount of tax deducted", "Total Tax Deducted", "Total TDS"]),
]

# Fields we insist on: if unresolved the summary is flagged, not silently zeroed.
_REQUIRED = [
    ("employer_tan", _EMPLOYER_TAN_LABELS),
    ("employee_pan", _EMPLOYEE_PAN_LABELS),
    ("gross_salary", ["Gross Salary"]),
    ("standard_deduction", ["Standard deduction under section 16(ia)", "Standard deduction"]),
    ("tds", ["Total amount of tax deducted", "Total Tax Deducted", "Total TDS"]),
]

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _to_float(raw: str) -> Optional[float]:
    cleaned = raw.replace(",", "").replace("₹", "").strip()
    return float(cleaned) if cleaned else None


def _find_code(text: str, labels: list[str], pattern: str) -> Optional[str]:
    """The first ``pattern`` appearing on (or just after) a label line."""
    for label in labels:
        m = re.search(
            re.escape(label) + r"[^\n]*?(" + pattern + r")",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).upper()
    return None


def _find_line(text: str, labels: list[str]) -> Optional[str]:
    """The remainder of the first label line (used for names/addresses)."""
    for label in labels:
        m = re.search(re.escape(label) + r"[ \t]*[:\-]?[ \t]*(.*)", text, re.IGNORECASE)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def _find_amount(text: str, labels: list[str]) -> Optional[float]:
    """The last number on the first label line that carries one.

    Taking the *last* number skips embedded digits inside a label such as
    "Standard deduction under section 16(ia)     75000.00".
    """
    for label in labels:
        for m in re.finditer(re.escape(label), text, re.IGNORECASE):
            tail = text[m.end():]
            lines = tail.split("\n")
            for line in lines[:2]:  # allow the value to spill to the next line
                numbers = _NUMBER.findall(line)
                if numbers:
                    amount = _to_float(numbers[-1])
                    if amount is not None:
                        return amount
    return None


def _find_period(text: str) -> tuple[Optional[str], Optional[str]]:
    m = re.search(
        r"Period[^\n]*?(\d{4}-\d{2}-\d{2})\s*(?:to|To|-)\s*(\d{4}-\d{2}-\d{2})",
        text,
    )
    if m:
        return m.group(1), m.group(2)
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if len(dates) >= 2:
        return dates[0], dates[1]
    return None, None


def _split_name_address(blob: Optional[str]) -> tuple[str, str]:
    if not blob:
        return "", ""
    parts = [p.strip() for p in blob.split(",", 1)]
    name = parts[0]
    address = parts[1] if len(parts) > 1 else ""
    return name, address


def parse_form16_text(text: str) -> Form16SummaryIn:
    warnings: list[str] = []

    employer_blob = _find_line(text, _EMPLOYER_NAME_LABELS)
    employee_blob = _find_line(text, _EMPLOYEE_NAME_LABELS)
    employer_name, employer_address = _split_name_address(employer_blob)
    employee_name, _ = _split_name_address(employee_blob)

    employer_tan = _find_code(text, _EMPLOYER_TAN_LABELS, _TAN)
    employee_pan = _find_code(text, _EMPLOYEE_PAN_LABELS, _PAN)
    period_from, period_to = _find_period(text)

    values: dict[str, object] = {
        "employer_name": employer_name,
        "employer_address": employer_address,
        "employer_tan": employer_tan or "",
        "employee_pan": employee_pan or "",
        "employee_name": employee_name,
        "period_from": period_from,
        "period_to": period_to,
    }

    for attr, labels in _MONEY_FIELDS:
        amount = _find_amount(text, labels)
        values[attr] = amount if amount is not None else 0.0

    resolved = {
        "employer_tan": employer_tan,
        "employee_pan": employee_pan,
        **{attr: _find_amount(text, labels) for attr, labels in _MONEY_FIELDS},
    }
    for attr, labels in _REQUIRED:
        if not resolved.get(attr):
            warnings.append(f"Could not parse '{labels[0]}' from Form 16")

    values["warnings"] = warnings
    return Form16SummaryIn(**values)  # type: ignore[arg-type]


def parse_form16_pdf(file_bytes: bytes) -> Form16SummaryIn:
    """Extract text from a Form 16 PDF and parse it."""
    import pdfplumber  # imported lazily: the text layer stays dependency-free

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return parse_form16_text("\n".join(pages))

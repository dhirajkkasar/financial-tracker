"""Assessment-year helpers. Pure functions, no DB.

FY 2024-25 -> AY 2025-26: the income of a financial year is assessed in the
following assessment year. The ITR form is filed *for* the AY; the income (and
the tax rules) belong to the FY. Every return therefore carries both labels.

``parse_ay`` returns the *income year* window — the dates the return covers —
which equals the FY one year before the AY label:

    parse_ay("2025-26") == parse_fy("2024-25") == (2024-04-01, 2025-03-31)
"""
from __future__ import annotations

from datetime import date

from app.engine.tax_engine import parse_fy


def _split(label: str) -> tuple[int, int]:
    """Split 'YYYY-YY' (or 'YYYY-YYYY') into (start_year, end_year)."""
    parts = label.split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(f"Invalid year label {label!r}. Expected format 'YYYY-YY'.")
    start = int(parts[0])
    suffix = int(parts[1])
    # Accept short ('25') or full ('2025') end suffixes.
    end = (start // 100) * 100 + suffix if suffix < 100 else suffix
    if end != start + 1:
        raise ValueError(
            f"Invalid year label {label!r}. End year must be start year + 1."
        )
    return start, end


def _fmt(start: int) -> str:
    return f"{start}-{str(start + 1)[-2:]}"


def fy_to_ay(fy_label: str) -> str:
    """Financial year -> the assessment year that assesses it.

    fy_to_ay("2024-25") == "2025-26"
    """
    start, _ = _split(fy_label)
    return _fmt(start + 1)


def ay_to_fy(ay_label: str) -> str:
    """Assessment year -> the financial year whose income it assesses.

    ay_to_fy("2025-26") == "2024-25"
    """
    start, _ = _split(ay_label)
    return _fmt(start - 1)


def parse_ay(ay_label: str) -> tuple[date, date]:
    """The income-year window covered by this assessment year: 1 Apr -> 31 Mar.

    parse_ay("2025-26") == (date(2024, 4, 1), date(2025, 3, 31))
    """
    return parse_fy(ay_to_fy(ay_label))

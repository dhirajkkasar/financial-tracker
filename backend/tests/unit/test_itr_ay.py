"""Assessment-year helpers: FY<->AY mapping and the income-year window."""
from datetime import date

import pytest

from app.engine.itr.ay import fy_to_ay, ay_to_fy, parse_ay


def test_fy_to_ay_2024_25():
    assert fy_to_ay("2024-25") == "2025-26"


def test_fy_to_ay_2025_26():
    assert fy_to_ay("2025-26") == "2026-27"


def test_ay_to_fy_2026_27():
    assert ay_to_fy("2026-27") == "2025-26"


def test_fy_to_ay_rejects_bad_label():
    with pytest.raises(ValueError):
        fy_to_ay("2024/25")


def test_fy_to_ay_rejects_non_consecutive():
    with pytest.raises(ValueError):
        fy_to_ay("2024-27")


def test_parse_ay_returns_income_year_dates():
    # AY 2025-26 assesses the income of FY 2024-25.
    assert parse_ay("2025-26") == (date(2024, 4, 1), date(2025, 3, 31))


def test_parse_ay_matches_parse_fy_of_income_year():
    from app.engine.tax_engine import parse_fy

    assert parse_ay("2026-27") == parse_fy(ay_to_fy("2026-27"))

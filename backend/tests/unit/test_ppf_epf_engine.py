import pytest
from datetime import date
from app.engine.ppf_epf_engine import get_applicable_rate, get_latest_valuation
from dataclasses import dataclass
from typing import Optional


@dataclass
class RateData:
    instrument: str
    rate_pct: float
    effective_from: date
    effective_to: Optional[date]


@dataclass
class ValuationData:
    date: date
    value_inr: int  # paise


def test_get_applicable_rate_mid_fy():
    rates = [
        RateData("PPF", 7.1, date(2021, 4, 1), None),
        RateData("PPF", 7.9, date(2017, 4, 1), date(2019, 12, 31)),
    ]
    result = get_applicable_rate("PPF", date(2022, 6, 1), rates)
    assert result == 7.1


def test_get_applicable_rate_boundary_date():
    rates = [
        RateData("PPF", 7.1, date(2021, 4, 1), None),
        RateData("PPF", 7.9, date(2017, 4, 1), date(2021, 3, 31)),
    ]
    # exactly on effective_from of new rate
    result = get_applicable_rate("PPF", date(2021, 4, 1), rates)
    assert result == 7.1


def test_get_applicable_rate_unknown_raises():
    from app.middleware.error_handler import NotFoundError
    with pytest.raises(NotFoundError):
        get_applicable_rate("PPF", date(2022, 1, 1), [])


def test_get_latest_valuation_returns_most_recent():
    valuations = [
        ValuationData(date(2023, 3, 31), 500000_00),
        ValuationData(date(2024, 3, 31), 600000_00),
        ValuationData(date(2022, 3, 31), 400000_00),
    ]
    result = get_latest_valuation(valuations)
    assert result.date == date(2024, 3, 31)


def test_get_latest_valuation_no_entries_returns_none():
    assert get_latest_valuation([]) is None

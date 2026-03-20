import pytest
from datetime import date
from tests.factories import make_cashflow


@pytest.fixture
def sample_cashflows():
    return [
        make_cashflow(date(2020, 1, 1), -100000.0),
        make_cashflow(date(2021, 1, 1), -50000.0),
        make_cashflow(date(2024, 1, 1), +200000.0),
    ]

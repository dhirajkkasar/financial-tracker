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


@pytest.fixture
def tmp_path_cwd(tmp_path, monkeypatch):
    """Fixture that changes cwd to tmp_path for relative path tests."""
    monkeypatch.chdir(tmp_path)
    return tmp_path

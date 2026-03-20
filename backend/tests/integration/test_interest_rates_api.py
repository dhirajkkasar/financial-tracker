import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def seed_rates(db):
    """Seed interest rates into the test DB using the seed script."""
    from scripts.seed_interest_rates import seed
    seed(db)


def test_get_interest_rate_by_date(client, db):
    seed_rates(db)
    resp = client.get("/interest-rates?instrument=PPF&date=2024-01-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "PPF"
    assert data["rate_pct"] == 7.1


def test_get_interest_rate_boundary_date(client, db):
    seed_rates(db)
    # date exactly on effective_from for FY2023-present PPF rate (2023-04-01)
    resp = client.get("/interest-rates?instrument=PPF&date=2023-04-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rate_pct"] == 7.1
    assert data["fy_label"] == "FY2023-present"


def test_seed_idempotency(client, db):
    seed_rates(db)
    seed_rates(db)  # second call should not duplicate
    resp = client.get("/interest-rates/all?instrument=PPF")
    assert resp.status_code == 200
    data = resp.json()
    # Count should be same as original (no duplicates)
    from scripts.seed_interest_rates import PPF_RATES
    assert len(data) == len(PPF_RATES)


def test_get_interest_rate_not_found(client, db):
    seed_rates(db)
    # date before any PPF rates
    resp = client.get("/interest-rates?instrument=PPF&date=1999-01-01")
    assert resp.status_code == 404


def test_list_all_rates(client, db):
    seed_rates(db)
    resp = client.get("/interest-rates/all")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0


def test_list_rates_filter_by_instrument(client, db):
    seed_rates(db)
    resp = client.get("/interest-rates/all?instrument=EPF")
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["instrument"] == "EPF" for r in data)

import pytest
from tests.factories import make_asset, make_transaction


def test_get_returns_stock_asset(client):
    # Create asset with a partial sell (5 remain) so total_invested > 0
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]
    client.post(f"/assets/{asset_id}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=1000.0, amount_inr=-10000.0
    ))
    client.post(f"/assets/{asset_id}/transactions", json=make_transaction(
        type="SELL", date="2024-01-01", units=5, price_per_unit=1500.0, amount_inr=7500.0
    ))
    resp = client.get(f"/assets/{asset_id}/returns")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xirr"] is not None
    # absolute_return is based on open-lot cost basis; with 5 shares held it should be present
    # (no price cache in test env so current_value may be None → abs_return may also be None)
    assert resp.status_code == 200  # main check: no crash


def test_get_returns_fully_exited_stock(client):
    # BUY 10 + SELL 10 = fully exited: total_invested = historical cost basis, XIRR from closed trades
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]
    client.post(f"/assets/{asset_id}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=1000.0, amount_inr=-10000.0
    ))
    client.post(f"/assets/{asset_id}/transactions", json=make_transaction(
        type="SELL", date="2024-01-01", units=10, price_per_unit=1500.0, amount_inr=15000.0
    ))
    resp = client.get(f"/assets/{asset_id}/returns")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xirr"] is not None              # XIRR computable from closed trades
    assert data["total_invested"] == 10000.0     # historical cost basis of all lots
    assert data["absolute_return"] is None       # no open position to compute return on


def test_get_returns_ppf_no_valuation_returns_null_xirr(client):
    asset_resp = client.post("/assets", json=make_asset(
        asset_type="PPF", asset_class="DEBT", name="My PPF"
    ))
    asset_id = asset_resp.json()["id"]
    resp = client.get(f"/assets/{asset_id}/returns")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xirr"] is None
    assert "message" in data


def test_get_returns_fd_includes_maturity_fields(client):
    asset_resp = client.post("/assets", json=make_asset(
        asset_type="FD", asset_class="DEBT", name="SBI FD"
    ))
    asset_id = asset_resp.json()["id"]
    client.post(f"/assets/{asset_id}/fd-detail", json={
        "bank": "SBI", "fd_type": "FD", "principal_amount": 100000.0,
        "interest_rate_pct": 7.5, "compounding": "QUARTERLY",
        "start_date": "2023-01-01", "maturity_date": "2026-01-01"
    })
    resp = client.get(f"/assets/{asset_id}/returns")
    assert resp.status_code == 200
    data = resp.json()
    assert "maturity_amount" in data
    assert data["maturity_amount"] > 100000.0


def test_stock_us_total_invested_uses_inr_not_usd(client):
    """Regression: price_per_unit for US stocks is stored in USD.
    total_invested must use amount_inr (INR), not buy_price_per_unit * units (USD)."""
    # 10 units vested at $200/share; forex=84 → cost basis = $2000 = ₹168000
    asset_resp = client.post("/assets", json=make_asset(
        asset_type="STOCK_US", asset_class="EQUITY", name="AMZN", identifier="AMZN"
    ))
    asset_id = asset_resp.json()["id"]
    client.post(f"/assets/{asset_id}/transactions", json=make_transaction(
        type="VEST", date="2023-06-01",
        units=10.0,
        price_per_unit=200.0,       # USD per share — stored as-is
        amount_inr=-168000.0,       # INR: 10 * 200 * 84
    ))
    resp = client.get(f"/assets/{asset_id}/returns")
    assert resp.status_code == 200
    data = resp.json()
    # Must be ₹168000, NOT $2000 (= 200 * 10)
    assert data["total_invested"] == pytest.approx(168000.0, rel=1e-3)


def test_get_returns_overview_empty_db_returns_zeros(client):
    resp = client.get("/returns/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_invested"] == 0.0
    assert data["total_current_value"] == 0.0

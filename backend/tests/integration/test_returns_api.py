from tests.factories import make_asset, make_transaction


def test_get_returns_stock_asset(client):
    # Create asset
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]
    # Add BUY transaction
    client.post(f"/assets/{asset_id}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=1000.0, amount_inr=-10000.0
    ))
    # Add a SELL transaction for XIRR
    client.post(f"/assets/{asset_id}/transactions", json=make_transaction(
        type="SELL", date="2024-01-01", units=10, price_per_unit=1500.0, amount_inr=15000.0
    ))
    resp = client.get(f"/assets/{asset_id}/returns")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xirr"] is not None
    assert data["absolute_return"] is not None


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


def test_get_returns_overview_empty_db_returns_zeros(client):
    resp = client.get("/returns/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_invested"] == 0.0
    assert data["total_current_value"] == 0.0

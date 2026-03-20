"""Integration tests for GET /assets/{id}/returns/lots (Phase 3.1)."""
from tests.factories import make_asset, make_transaction


def test_lots_empty_when_no_transactions(client):
    asset = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY")).json()
    resp = client.get(f"/assets/{asset['id']}/returns/lots")
    assert resp.status_code == 200
    data = resp.json()
    # Paginated shape
    assert data["open_lots"]["items"] == []
    assert data["matched_sells"]["items"] == []


def test_lots_single_buy_shows_open_lot(client):
    asset = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY")).json()
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=100.0, amount_inr=-1000.0
    ))
    resp = client.get(f"/assets/{asset['id']}/returns/lots")
    assert resp.status_code == 200
    data = resp.json()
    assert data["open_lots"]["total"] == 1
    lot = data["open_lots"]["items"][0]
    assert lot["units_remaining"] == 10.0
    assert lot["buy_price_per_unit"] == 100.0
    assert "holding_days" in lot
    assert "is_short_term" in lot


def test_lots_fifo_sell_consumes_earliest_lot(client):
    asset = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY")).json()
    aid = asset["id"]
    # Two buys
    client.post(f"/assets/{aid}/transactions", json=make_transaction(
        type="BUY", date="2021-01-01", units=10, price_per_unit=100.0, amount_inr=-1000.0
    ))
    client.post(f"/assets/{aid}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=200.0, amount_inr=-2000.0
    ))
    # Sell 10 — should consume first lot entirely
    client.post(f"/assets/{aid}/transactions", json=make_transaction(
        type="SELL", date="2024-01-01", units=10, price_per_unit=300.0, amount_inr=3000.0
    ))
    resp = client.get(f"/assets/{aid}/returns/lots")
    assert resp.status_code == 200
    data = resp.json()
    # Second lot still open
    assert data["open_lots"]["total"] == 1
    assert data["open_lots"]["items"][0]["buy_price_per_unit"] == 200.0
    # One sell match recorded
    assert data["matched_sells"]["total"] == 1
    assert data["matched_sells"]["items"][0]["buy_price_per_unit"] == 100.0
    assert data["matched_sells"]["items"][0]["units_sold"] == 10.0


def test_lots_partial_sell_splits_lot(client):
    asset = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY")).json()
    aid = asset["id"]
    client.post(f"/assets/{aid}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=100.0, amount_inr=-1000.0
    ))
    client.post(f"/assets/{aid}/transactions", json=make_transaction(
        type="SELL", date="2024-01-01", units=4, price_per_unit=150.0, amount_inr=600.0
    ))
    resp = client.get(f"/assets/{aid}/returns/lots")
    assert resp.status_code == 200
    data = resp.json()
    assert data["open_lots"]["total"] == 1
    assert data["open_lots"]["items"][0]["units_remaining"] == 6.0
    assert data["matched_sells"]["items"][0]["realised_gain_inr"] == 200.0  # (150-100)*4


def test_lots_not_found_returns_404(client):
    resp = client.get("/assets/9999/returns/lots")
    assert resp.status_code == 404


def test_lots_short_term_flag_for_recent_buy(client):
    asset = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY")).json()
    # Buy very recently — must be short term
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="BUY", date="2026-01-01", units=5, price_per_unit=200.0, amount_inr=-1000.0
    ))
    resp = client.get(f"/assets/{asset['id']}/returns/lots")
    assert resp.json()["open_lots"]["items"][0]["is_short_term"] is True

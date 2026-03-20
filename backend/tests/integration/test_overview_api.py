"""Integration tests for GET /overview/allocation and GET /overview/gainers (Phase 3.2)."""
from datetime import datetime
from tests.factories import make_asset, make_transaction
from app.models.price_cache import PriceCache


def _seed_price(db, asset_id: int, price_inr: float):
    """Directly insert a PriceCache row (paise)."""
    pc = PriceCache(
        asset_id=asset_id,
        price_inr=int(price_inr * 100),
        fetched_at=datetime.utcnow(),
        source="test",
        is_stale=False,
    )
    db.add(pc)
    db.commit()


# ---------------------------------------------------------------------------
# GET /overview/allocation
# ---------------------------------------------------------------------------

def test_allocation_empty_db_returns_empty(client):
    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["allocations"] == []
    assert data["total_value"] == 0.0


def test_allocation_response_shape(client):
    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    assert "allocations" in data
    assert "total_value" in data


def test_allocation_groups_equity_by_asset_class(client, db):
    asset = client.post("/assets", json=make_asset(
        asset_type="STOCK_IN", asset_class="EQUITY", identifier="REL"
    )).json()
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=100.0, amount_inr=-1000.0
    ))
    _seed_price(db, asset["id"], 150.0)

    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_value"] > 0
    classes = [a["asset_class"] for a in data["allocations"]]
    assert "EQUITY" in classes


def test_allocation_pct_sums_to_100(client, db):
    # EQUITY asset with price
    a1 = client.post("/assets", json=make_asset(
        asset_type="STOCK_IN", asset_class="EQUITY", identifier="REL"
    )).json()
    client.post(f"/assets/{a1['id']}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=100.0, amount_inr=-1000.0
    ))
    _seed_price(db, a1["id"], 150.0)

    # DEBT asset (FD with accrued value)
    a2 = client.post("/assets", json=make_asset(
        asset_type="FD", asset_class="DEBT", name="SBI FD"
    )).json()
    client.post(f"/assets/{a2['id']}/fd-detail", json={
        "bank": "SBI", "fd_type": "FD", "principal_amount": 100000.0,
        "interest_rate_pct": 7.5, "compounding": "QUARTERLY",
        "start_date": "2023-01-01", "maturity_date": "2028-01-01"
    })

    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["allocations"]) >= 1
    total_pct = sum(a["pct_of_total"] for a in data["allocations"])
    assert abs(total_pct - 100.0) < 0.01


def test_allocation_entry_has_required_fields(client, db):
    asset = client.post("/assets", json=make_asset(
        asset_type="STOCK_IN", asset_class="EQUITY", identifier="INFY"
    )).json()
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=5, price_per_unit=200.0, amount_inr=-1000.0
    ))
    _seed_price(db, asset["id"], 300.0)

    resp = client.get("/overview/allocation")
    data = resp.json()
    for entry in data["allocations"]:
        assert "asset_class" in entry
        assert "value_inr" in entry
        assert "pct_of_total" in entry


# ---------------------------------------------------------------------------
# GET /overview/gainers
# ---------------------------------------------------------------------------

def test_gainers_empty_db_returns_empty(client):
    resp = client.get("/overview/gainers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["gainers"] == []
    assert data["losers"] == []


def test_gainers_response_shape(client):
    resp = client.get("/overview/gainers")
    assert resp.status_code == 200
    data = resp.json()
    assert "gainers" in data
    assert "losers" in data


def test_gainers_includes_assets_with_sell(client):
    asset = client.post("/assets", json=make_asset(
        asset_type="STOCK_IN", asset_class="EQUITY", identifier="TCS"
    )).json()
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=100.0, amount_inr=-1000.0
    ))
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="SELL", date="2024-01-01", units=10, price_per_unit=200.0, amount_inr=2000.0
    ))

    resp = client.get("/overview/gainers")
    assert resp.status_code == 200
    data = resp.json()
    # Asset fully sold — may appear in gainers
    all_ids = [g["asset_id"] for g in data["gainers"]] + [g["asset_id"] for g in data["losers"]]
    assert asset["id"] in all_ids


def test_gainers_limits_to_5_by_default(client):
    """Create 6 sold assets, gainers should be at most 5."""
    for i in range(6):
        asset = client.post("/assets", json=make_asset(
            asset_type="STOCK_IN", asset_class="EQUITY", identifier=f"TICK{i}"
        )).json()
        client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
            type="BUY", date="2022-01-01", units=10,
            price_per_unit=100.0, amount_inr=-1000.0
        ))
        client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
            type="SELL", date="2024-01-01", units=10,
            price_per_unit=float(150 + i * 10), amount_inr=float(1500 + i * 100)
        ))

    resp = client.get("/overview/gainers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["gainers"]) <= 5


def test_gainers_n_param(client):
    resp = client.get("/overview/gainers?n=3")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["gainers"]) <= 3
    assert len(data["losers"]) <= 3


def test_gainers_entry_has_required_fields(client):
    asset = client.post("/assets", json=make_asset(
        asset_type="STOCK_IN", asset_class="EQUITY", identifier="WIPRO"
    )).json()
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=100.0, amount_inr=-1000.0
    ))
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="SELL", date="2024-01-01", units=10, price_per_unit=150.0, amount_inr=1500.0
    ))

    resp = client.get("/overview/gainers")
    data = resp.json()
    for entry in data["gainers"] + data["losers"]:
        assert "asset_id" in entry
        assert "name" in entry
        assert "asset_type" in entry

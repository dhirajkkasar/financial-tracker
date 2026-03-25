"""Integration tests for GET /overview/allocation and GET /overview/gainers (Phase 3.2)."""
from datetime import datetime, date, timedelta
from tests.factories import make_asset, make_transaction
from app.models.price_cache import PriceCache
from app.models.cas_snapshot import CasSnapshot


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


def _seed_snapshot(db, asset_id: int, closing_units: float, market_value_inr: float, nav_inr: float, days_old: int = 0):
    """Directly insert a CasSnapshot row. market_value_inr and nav_inr are in rupees."""
    snap = CasSnapshot(
        asset_id=asset_id,
        date=date.today() - timedelta(days=days_old),
        closing_units=closing_units,
        nav_price_inr=int(nav_inr * 100),
        market_value_inr=int(market_value_inr * 100),
        total_cost_inr=int(market_value_inr * 80),
    )
    db.add(snap)
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


def test_allocation_mixed_mf_counts_as_equity(client, db):
    """Hybrid MF assets stored with MIXED class should appear as EQUITY in allocation."""
    mf = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="MIXED", name="HDFC Balanced Fund", identifier="INF179K"
    )).json()
    client.post(f"/assets/{mf['id']}/transactions", json=make_transaction(
        type="SIP", date="2022-01-01", units=100, price_per_unit=50.0, amount_inr=-5000.0
    ))
    _seed_price(db, mf["id"], 60.0)

    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    classes = [a["asset_class"] for a in data["allocations"]]
    assert "EQUITY" in classes
    assert "MIXED" not in classes


def test_allocation_nps_counts_as_debt(client, db):
    """NPS assets should appear as DEBT in allocation regardless of stored class."""
    nps = client.post("/assets", json=make_asset(
        asset_type="NPS", asset_class="MIXED", name="SBI NPS Tier I", identifier="SM007001"
    )).json()
    client.post(f"/assets/{nps['id']}/transactions", json=make_transaction(
        type="CONTRIBUTION", date="2022-01-01", units=100, price_per_unit=30.0, amount_inr=-3000.0
    ))
    _seed_price(db, nps["id"], 35.0)

    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    classes = [a["asset_class"] for a in data["allocations"]]
    assert "DEBT" in classes
    assert "MIXED" not in classes


def test_allocation_epf_uses_transaction_based_value(client, db):
    """EPF current value in allocation must use contributions+interest from transactions, not Valuation entries."""
    epf = client.post("/assets", json=make_asset(
        asset_type="EPF", asset_class="DEBT", name="My EPF", identifier="TN/12345"
    )).json()
    # Employee contribution: 5000 INR outflow
    client.post(f"/assets/{epf['id']}/transactions", json=make_transaction(
        type="CONTRIBUTION", date="2024-01-01", amount_inr=-5000.0
    ))
    # Interest: 350 INR inflow
    client.post(f"/assets/{epf['id']}/transactions", json=make_transaction(
        type="INTEREST", date="2024-03-31", amount_inr=350.0
    ))
    # No Valuation entry — EPF allocation must still show up
    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    classes = [a["asset_class"] for a in data["allocations"]]
    assert "DEBT" in classes
    debt = next(a for a in data["allocations"] if a["asset_class"] == "DEBT")
    # current_value = 5000 + 350 = 5350
    assert abs(debt["value_inr"] - 5350.0) < 1.0


def test_allocation_debt_mf_stays_as_debt(client, db):
    """MF assets classified as DEBT (liquid/debt funds) should remain in DEBT."""
    mf = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="DEBT", name="HDFC Liquid Fund", identifier="INF179L"
    )).json()
    client.post(f"/assets/{mf['id']}/transactions", json=make_transaction(
        type="SIP", date="2022-01-01", units=50, price_per_unit=100.0, amount_inr=-5000.0
    ))
    _seed_price(db, mf["id"], 110.0)

    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    classes = [a["asset_class"] for a in data["allocations"]]
    assert "DEBT" in classes
    assert "MIXED" not in classes


def test_allocation_mf_fresh_snapshot_uses_market_value_not_price_cache(client, db):
    """Fresh CAS snapshot (< 30 days) → allocation value comes from snapshot.market_value_inr, not price_cache × units."""
    mf = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="EQUITY", name="ICICI Bluechip Fund", identifier="INF109K01VQ5"
    )).json()
    client.post(f"/assets/{mf['id']}/transactions", json=make_transaction(
        type="SIP", date="2022-01-01", units=100, price_per_unit=50.0, amount_inr=-5000.0
    ))
    # Fresh snapshot: 100 units at NAV 80, market value = 8000 INR
    _seed_snapshot(db, mf["id"], closing_units=100, market_value_inr=8000.0, nav_inr=80.0, days_old=0)
    # Price cache: 100 INR/unit → 100 × 100 = 10000 INR if used (intentionally different)
    _seed_price(db, mf["id"], 100.0)

    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    equity = next(a for a in data["allocations"] if a["asset_class"] == "EQUITY")
    # Snapshot is fresh: must use market_value_inr = 8000, not price_cache × units = 10000
    assert abs(equity["value_inr"] - 8000.0) < 1.0


def test_allocation_mf_stale_snapshot_uses_closing_units_times_price_cache(client, db):
    """Stale CAS snapshot (>= 30 days) → allocation value comes from snapshot.closing_units × price_cache NAV."""
    mf = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="EQUITY", name="Axis Bluechip Fund", identifier="INF846K01DP8"
    )).json()
    client.post(f"/assets/{mf['id']}/transactions", json=make_transaction(
        type="SIP", date="2022-01-01", units=100, price_per_unit=50.0, amount_inr=-5000.0
    ))
    # Stale snapshot (31 days old): 100 units, market value = 5000 INR (outdated)
    _seed_snapshot(db, mf["id"], closing_units=100, market_value_inr=5000.0, nav_inr=50.0, days_old=31)
    # Price cache: 80 INR/unit → 100 × 80 = 8000 INR (the fresh value)
    _seed_price(db, mf["id"], 80.0)

    resp = client.get("/overview/allocation")
    assert resp.status_code == 200
    data = resp.json()
    equity = next(a for a in data["allocations"] if a["asset_class"] == "EQUITY")
    # Snapshot is stale: must use closing_units × price_cache = 100 × 80 = 8000, not stale market_value = 5000
    assert abs(equity["value_inr"] - 8000.0) < 1.0


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


def test_gainers_includes_assets_with_partial_sell(client):
    """Gainers endpoint handles assets with partial sells (open lots remain)."""
    asset = client.post("/assets", json=make_asset(
        asset_type="STOCK_IN", asset_class="EQUITY", identifier="TCS"
    )).json()
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="BUY", date="2022-01-01", units=10, price_per_unit=100.0, amount_inr=-1000.0
    ))
    # Partial sell — 5 shares remain, total_invested > 0
    client.post(f"/assets/{asset['id']}/transactions", json=make_transaction(
        type="SELL", date="2024-01-01", units=5, price_per_unit=200.0, amount_inr=1000.0
    ))

    resp = client.get("/overview/gainers")
    assert resp.status_code == 200
    assert "gainers" in resp.json()
    assert "losers" in resp.json()


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

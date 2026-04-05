import pytest
from tests.factories import make_asset


def test_fiscal_years_returns_200(client):
    resp = client.get("/tax/fiscal-years")
    assert resp.status_code == 200
    assert "fiscal_years" in resp.json()


def test_fiscal_years_returns_list(client):
    """Returns a non-empty list of FY labels loaded from config files."""
    resp = client.get("/tax/fiscal-years")
    fys = resp.json()["fiscal_years"]
    assert isinstance(fys, list)
    assert len(fys) > 0


def test_fiscal_years_are_sorted(client):
    """FY labels are returned in ascending order."""
    resp = client.get("/tax/fiscal-years")
    fys = resp.json()["fiscal_years"]
    assert fys == sorted(fys)


def test_fiscal_years_match_config_files(client):
    """Returned FY labels correspond exactly to yaml filenames in config/tax_rates/."""
    from pathlib import Path
    config_dir = Path("app/config/tax_rates")
    expected = sorted(p.stem for p in config_dir.glob("*.yaml") if p.stem != "__init__")

    resp = client.get("/tax/fiscal-years")
    assert resp.json()["fiscal_years"] == expected


def test_fiscal_years_format(client):
    """Each FY label matches the YYYY-YY pattern."""
    import re
    resp = client.get("/tax/fiscal-years")
    for fy in resp.json()["fiscal_years"]:
        assert re.match(r"^\d{4}-\d{2}$", fy), f"Unexpected FY format: {fy}"


def test_tax_summary_returns_200(client):
    resp = client.get("/tax/summary?fy=2024-25")
    assert resp.status_code == 200
    data = resp.json()
    assert "fy" in data
    assert "stcg" in data
    assert "ltcg" in data
    assert "interest" in data


def test_tax_summary_empty_db(client):
    resp = client.get("/tax/summary?fy=2024-25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stcg"]["assets"] == []
    assert data["ltcg"]["assets"] == []
    assert data["interest"]["assets"] == []
    assert data["stcg"]["total_gain"] == 0.0
    assert data["ltcg"]["total_gain"] == 0.0
    assert data["interest"]["total_interest"] == 0.0


def test_tax_summary_invalid_fy_returns_422(client):
    resp = client.get("/tax/summary?fy=bad")
    assert resp.status_code == 422


def test_tax_summary_missing_fy_returns_422(client):
    resp = client.get("/tax/summary")
    assert resp.status_code == 422


def test_tax_summary_stock_lt_gain(client):
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    # BUY Jan 2023, SELL Jun 2024 → 517 days → LT for equity
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2023-01-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-06-01", "units": 10,
        "price_per_unit": 1500.0, "amount_inr": 15000.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    assert resp.status_code == 200
    data = resp.json()

    # Should appear in ltcg section
    ltcg_assets = data["ltcg"]["assets"]
    entry = next((a for a in ltcg_assets if a["asset_id"] == asset_id), None)
    assert entry is not None
    assert entry["gain"] == pytest.approx(5000.0)
    assert entry["ltcg_exempt_eligible"] is True

    # LTCG exemption: 5000 < 125000 → fully exempt → total_tax = 0
    assert data["ltcg"]["total_tax"] == pytest.approx(0.0)
    assert data["ltcg"]["ltcg_exemption_used"] == pytest.approx(5000.0)

    # No ST gain
    stcg_assets = data["stcg"]["assets"]
    assert not any(a["asset_id"] == asset_id for a in stcg_assets)


def test_tax_summary_stock_st_gain(client):
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    # BUY Jun 2024, SELL Sep 2024 → 92 days → ST at 20%
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-06-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-09-01", "units": 10,
        "price_per_unit": 1200.0, "amount_inr": 12000.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    data = resp.json()
    stcg_assets = data["stcg"]["assets"]
    entry = next((a for a in stcg_assets if a["asset_id"] == asset_id), None)
    assert entry is not None
    assert entry["gain"] == pytest.approx(2000.0)
    assert entry["tax_estimate"] == pytest.approx(400.0)   # 2000 × 20%
    assert entry["is_slab"] is False
    assert entry["tax_rate_pct"] == pytest.approx(20.0)


def test_tax_summary_excludes_sells_outside_fy(client):
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    # SELL in FY 2023-24 — should NOT appear in FY 2024-25
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2022-01-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-03-01", "units": 10,
        "price_per_unit": 1500.0, "amount_inr": 15000.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    data = resp.json()
    assert data["ltcg"]["total_gain"] == pytest.approx(0.0)
    assert data["stcg"]["assets"] == []
    assert data["ltcg"]["assets"] == []


def test_tax_summary_us_stock_st_uses_slab(client):
    """STOCK_US ST gain uses SLAB_RATE (30%) not 20%."""
    asset_resp = client.post("/assets", json=make_asset(
        asset_type="STOCK_US", asset_class="EQUITY", identifier="AAPL"
    ))
    asset_id = asset_resp.json()["id"]

    # BUY Jun 2024, SELL Sep 2024 → 92 days < 730 → ST at slab
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-06-01", "units": 5,
        "price_per_unit": 100.0, "amount_inr": -500.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-09-01", "units": 5,
        "price_per_unit": 120.0, "amount_inr": 600.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    data = resp.json()
    stcg_assets = data["stcg"]["assets"]
    entry = next((a for a in stcg_assets if a["asset_id"] == asset_id), None)
    assert entry is not None
    assert entry["gain"] == pytest.approx(100.0)
    assert entry["tax_estimate"] == pytest.approx(30.0)   # 100 × 30% slab
    assert entry["is_slab"] is True


def test_tax_summary_asset_id_present(client):
    """Each asset entry has asset_id for linking to asset page."""
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-06-01", "units": 10,
        "price_per_unit": 100.0, "amount_inr": -1000.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-09-01", "units": 10,
        "price_per_unit": 120.0, "amount_inr": 1200.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    data = resp.json()
    stcg_assets = data["stcg"]["assets"]
    entry = next((a for a in stcg_assets if a["asset_id"] == asset_id), None)
    assert entry is not None
    assert "asset_name" in entry
    assert "asset_type" in entry


def test_tax_unrealised_returns_200(client):
    resp = client.get("/tax/unrealised")
    assert resp.status_code == 200
    data = resp.json()
    assert "lots" in data
    assert "totals" in data


def test_tax_unrealised_empty(client):
    resp = client.get("/tax/unrealised")
    data = resp.json()
    assert data["lots"] == []
    assert data["totals"]["total_st_unrealised"] == 0.0
    assert data["totals"]["total_lt_unrealised"] == 0.0


def test_tax_unrealised_with_price_cache(client, db):
    from app.models.price_cache import PriceCache
    from datetime import datetime

    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-01-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    db.add(PriceCache(
        asset_id=asset_id, price_inr=120000,
        fetched_at=datetime.utcnow(), source="test", is_stale=False,
    ))
    db.commit()

    resp = client.get("/tax/unrealised")
    data = resp.json()
    assert len(data["lots"]) >= 1
    lot = next(l for l in data["lots"] if l["asset_id"] == asset_id)
    assert lot["unrealised_gain"] == pytest.approx(2000.0)
    assert "asset_class" in lot   # new field


def test_tax_harvest_returns_200(client):
    resp = client.get("/tax/harvest-opportunities")
    assert resp.status_code == 200
    assert "opportunities" in resp.json()


def test_tax_harvest_empty(client):
    resp = client.get("/tax/harvest-opportunities")
    assert resp.json()["opportunities"] == []


def test_tax_harvest_with_loss(client, db):
    from app.models.price_cache import PriceCache
    from datetime import datetime

    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-01-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    db.add(PriceCache(
        asset_id=asset_id, price_inr=80000,
        fetched_at=datetime.utcnow(), source="test", is_stale=False,
    ))
    db.commit()

    resp = client.get("/tax/harvest-opportunities")
    data = resp.json()
    assert len(data["opportunities"]) >= 1
    opp = next(o for o in data["opportunities"] if o["asset_id"] == asset_id)
    assert opp["unrealised_loss"] == pytest.approx(2000.0)

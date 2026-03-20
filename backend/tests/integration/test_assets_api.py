import pytest
from tests.factories import make_asset


def test_create_asset_returns_201(client):
    resp = client.post("/assets", json=make_asset())
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Asset"
    assert data["asset_type"] == "STOCK_IN"
    assert "id" in data


def test_create_asset_missing_required_field_returns_422(client):
    resp = client.post("/assets", json={"name": "Missing Type"})
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_list_assets_filter_by_type(client):
    client.post("/assets", json=make_asset(asset_type="STOCK_IN"))
    client.post("/assets", json=make_asset(name="MF Asset", asset_type="MF", identifier="INF123"))
    resp = client.get("/assets?type=MF")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["asset_type"] == "MF"


def test_list_assets_filter_by_active_false(client):
    r1 = client.post("/assets", json=make_asset(name="Active"))
    assert r1.status_code == 201
    r2 = client.post("/assets", json=make_asset(name="Inactive"))
    assert r2.status_code == 201
    asset_id = r2.json()["id"]
    client.delete(f"/assets/{asset_id}")
    resp = client.get("/assets?active=false")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["is_active"] is False


def test_get_asset_not_found_returns_404(client):
    resp = client.get("/assets/99999")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


def test_update_asset(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.put(f"/assets/{asset_id}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


def test_delete_asset_soft_deletes(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.delete(f"/assets/{asset_id}")
    assert resp.status_code == 200
    # Asset should still exist in DB with is_active=False
    get_resp = client.get(f"/assets/{asset_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False

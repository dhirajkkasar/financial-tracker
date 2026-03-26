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

def make_goal(**overrides):
    return {
        "name": "Retirement",
        "target_amount_inr": 5000000.0,
        "target_date": "2040-01-01",
        "assumed_return_pct": 12.0,
        **overrides,
    }


def test_get_asset_returns_empty_goals_when_unallocated(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.get(f"/assets/{asset_id}")
    assert resp.status_code == 200
    assert resp.json()["goals"] == []


def test_get_asset_returns_single_goal_when_allocated(client, seeded_asset):
    asset_id = seeded_asset["id"]
    goal_resp = client.post("/goals", json=make_goal())
    goal = goal_resp.json()
    client.post(f"/goals/{goal['id']}/allocations", json={"asset_id": asset_id, "allocation_pct": 100})

    data = client.get(f"/assets/{asset_id}").json()
    assert len(data["goals"]) == 1
    assert data["goals"][0] == {"id": goal["id"], "name": "Retirement"}


def test_get_asset_returns_multiple_goals_when_allocated_to_many(client, seeded_asset):
    asset_id = seeded_asset["id"]
    g1 = client.post("/goals", json=make_goal(name="Retirement")).json()
    g2 = client.post("/goals", json=make_goal(name="House")).json()
    client.post(f"/goals/{g1['id']}/allocations", json={"asset_id": asset_id, "allocation_pct": 60})
    client.post(f"/goals/{g2['id']}/allocations", json={"asset_id": asset_id, "allocation_pct": 40})

    data = client.get(f"/assets/{asset_id}").json()
    goal_ids = {g["id"] for g in data["goals"]}
    goal_names = {g["name"] for g in data["goals"]}
    assert goal_ids == {g1["id"], g2["id"]}
    assert goal_names == {"Retirement", "House"}


# TestFixInactiveStocks removed — retroactive fix done by cleaning DB and reimporting
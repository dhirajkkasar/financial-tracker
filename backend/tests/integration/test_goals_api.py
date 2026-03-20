import pytest
from tests.factories import make_asset


def make_goal(**overrides):
    return {
        "name": "Retirement",
        "target_amount_inr": 5000000.0,
        "target_date": "2040-01-01",
        "assumed_return_pct": 12.0,
        **overrides,
    }


def test_create_goal(client):
    resp = client.post("/goals", json=make_goal())
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Retirement"
    assert data["target_amount_inr"] == 5000000.0


def test_add_allocation_valid(client):
    goal_resp = client.post("/goals", json=make_goal())
    goal_id = goal_resp.json()["id"]
    asset1_resp = client.post("/assets", json=make_asset(name="Asset1"))
    asset1_id = asset1_resp.json()["id"]
    asset2_resp = client.post("/assets", json=make_asset(name="Asset2", identifier="HDFC"))
    asset2_id = asset2_resp.json()["id"]

    resp1 = client.post(f"/goals/{goal_id}/allocations", json={"asset_id": asset1_id, "allocation_pct": 70})
    assert resp1.status_code == 201

    resp2 = client.post(f"/goals/{goal_id}/allocations", json={"asset_id": asset2_id, "allocation_pct": 30})
    assert resp2.status_code == 201


def test_add_allocation_invalid_sum_returns_422(client):
    goal1_resp = client.post("/goals", json=make_goal(name="Goal1"))
    goal1_id = goal1_resp.json()["id"]
    goal2_resp = client.post("/goals", json=make_goal(name="Goal2"))
    goal2_id = goal2_resp.json()["id"]
    asset_resp = client.post("/assets", json=make_asset())
    asset_id = asset_resp.json()["id"]

    # Allocate 70% for goal1
    resp1 = client.post(f"/goals/{goal1_id}/allocations", json={"asset_id": asset_id, "allocation_pct": 70})
    assert resp1.status_code == 201

    # Try to allocate 40% for goal2 → total would be 110% → 422
    resp2 = client.post(f"/goals/{goal2_id}/allocations", json={"asset_id": asset_id, "allocation_pct": 40})
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "VALIDATION_ERROR"


def test_add_allocation_not_multiple_of_10_returns_422(client):
    goal_resp = client.post("/goals", json=make_goal())
    goal_id = goal_resp.json()["id"]
    asset_resp = client.post("/assets", json=make_asset())
    asset_id = asset_resp.json()["id"]

    resp = client.post(f"/goals/{goal_id}/allocations", json={"asset_id": asset_id, "allocation_pct": 75})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_add_allocation_unallocated_asset_valid(client):
    # Asset with 0 allocations is valid (no constraint needed)
    asset_resp = client.post("/assets", json=make_asset())
    assert asset_resp.status_code == 201
    # Just check we can create and list goals without errors
    goal_resp = client.post("/goals", json=make_goal())
    assert goal_resp.status_code == 201


def test_update_allocation_revalidates_sum(client):
    goal1_resp = client.post("/goals", json=make_goal(name="Goal1"))
    goal1_id = goal1_resp.json()["id"]
    goal2_resp = client.post("/goals", json=make_goal(name="Goal2"))
    goal2_id = goal2_resp.json()["id"]
    asset_resp = client.post("/assets", json=make_asset())
    asset_id = asset_resp.json()["id"]

    # Allocate 70% to goal1, 30% to goal2 → sum = 100%
    alloc1_resp = client.post(f"/goals/{goal1_id}/allocations", json={"asset_id": asset_id, "allocation_pct": 70})
    alloc1_id = alloc1_resp.json()["id"]
    client.post(f"/goals/{goal2_id}/allocations", json={"asset_id": asset_id, "allocation_pct": 30})

    # Update goal1 to 80% → sum would be 80+30=110% → 422
    resp = client.put(f"/goals/{goal1_id}/allocations/{alloc1_id}", json={"allocation_pct": 80})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Update goal1 to 60% → sum would be 60+30=90% (not 0 or 100) → 422
    resp2 = client.put(f"/goals/{goal1_id}/allocations/{alloc1_id}", json={"allocation_pct": 60})
    assert resp2.status_code == 422

    # Update goal1 to 70% (same) → sum = 100% → OK
    resp3 = client.put(f"/goals/{goal1_id}/allocations/{alloc1_id}", json={"allocation_pct": 70})
    assert resp3.status_code == 200


def test_delete_allocation_revalidates_sum(client):
    goal_resp = client.post("/goals", json=make_goal())
    goal_id = goal_resp.json()["id"]
    asset1_resp = client.post("/assets", json=make_asset(name="A1"))
    asset1_id = asset1_resp.json()["id"]
    asset2_resp = client.post("/assets", json=make_asset(name="A2", identifier="HDFC"))
    asset2_id = asset2_resp.json()["id"]

    alloc1_resp = client.post(f"/goals/{goal_id}/allocations", json={"asset_id": asset1_id, "allocation_pct": 70})
    alloc1_id = alloc1_resp.json()["id"]
    alloc2_resp = client.post(f"/goals/{goal_id}/allocations", json={"asset_id": asset2_id, "allocation_pct": 30})
    alloc2_id = alloc2_resp.json()["id"]

    # Delete asset2's only allocation → asset2 sum goes to 0 (fully unlinked) → valid
    resp = client.delete(f"/goals/{goal_id}/allocations/{alloc2_id}")
    assert resp.status_code == 204

    # Delete asset1's only allocation → asset1 sum goes to 0 → valid
    resp2 = client.delete(f"/goals/{goal_id}/allocations/{alloc1_id}")
    assert resp2.status_code == 204


def test_list_allocations(client):
    goal_resp = client.post("/goals", json=make_goal())
    goal_id = goal_resp.json()["id"]
    asset_resp = client.post("/assets", json=make_asset())
    asset_id = asset_resp.json()["id"]

    client.post(f"/goals/{goal_id}/allocations", json={"asset_id": asset_id, "allocation_pct": 100})

    resp = client.get(f"/goals/{goal_id}/allocations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["allocation_pct"] == 100


def test_goal_target_amount_roundtrip(client):
    resp = client.post("/goals", json=make_goal(target_amount_inr=1234567.89))
    assert resp.status_code == 201
    assert resp.json()["target_amount_inr"] == 1234567.89

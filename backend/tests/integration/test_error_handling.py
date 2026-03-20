import pytest
from tests.factories import make_asset, make_transaction


def test_404_returns_consistent_json(client):
    resp = client.get("/assets/99999")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "message" in data["error"]


def test_409_returns_consistent_json(client, seeded_asset):
    asset_id = seeded_asset["id"]
    txn = make_transaction(txn_id="dup-txn-001")
    resp1 = client.post(f"/assets/{asset_id}/transactions", json=txn)
    assert resp1.status_code == 201
    resp2 = client.post(f"/assets/{asset_id}/transactions", json=txn)
    assert resp2.status_code == 409
    data = resp2.json()
    assert "error" in data
    assert data["error"]["code"] == "DUPLICATE"
    assert "message" in data["error"]


def test_422_returns_consistent_json(client):
    resp = client.post("/assets", json={"name": "Missing Required Fields"})
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "message" in data["error"]

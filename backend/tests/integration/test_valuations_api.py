import pytest
from tests.factories import make_asset


def make_valuation(**overrides):
    return {"date": "2023-01-01", "value_inr": 100000.0, **overrides}


def test_create_valuation(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.post(f"/assets/{asset_id}/valuations", json=make_valuation())
    assert resp.status_code == 201
    data = resp.json()
    assert data["value_inr"] == 100000.0
    assert data["asset_id"] == asset_id


def test_list_valuations_ordered_by_date(client, seeded_asset):
    asset_id = seeded_asset["id"]
    client.post(f"/assets/{asset_id}/valuations", json=make_valuation(date="2023-01-01"))
    client.post(f"/assets/{asset_id}/valuations", json=make_valuation(date="2023-06-01"))
    resp = client.get(f"/assets/{asset_id}/valuations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Most recent first
    assert data[0]["date"] > data[1]["date"]


def test_delete_valuation(client, seeded_asset):
    asset_id = seeded_asset["id"]
    create_resp = client.post(f"/assets/{asset_id}/valuations", json=make_valuation())
    assert create_resp.status_code == 201
    val_id = create_resp.json()["id"]

    del_resp = client.delete(f"/assets/{asset_id}/valuations/{val_id}")
    assert del_resp.status_code == 204

    list_resp = client.get(f"/assets/{asset_id}/valuations")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0


def test_valuation_converts_inr_correctly(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.post(
        f"/assets/{asset_id}/valuations",
        json=make_valuation(value_inr=150000.50),
    )
    assert resp.status_code == 201
    # Should round-trip correctly
    assert resp.json()["value_inr"] == 150000.50

import pytest
from tests.factories import make_asset, make_transaction


def test_create_transaction_generates_txn_id(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.post(f"/assets/{asset_id}/transactions", json=make_transaction())
    assert resp.status_code == 201
    data = resp.json()
    assert data["txn_id"] is not None
    assert len(data["txn_id"]) == 64  # SHA256 hex digest


def test_create_transaction_generates_lot_id_for_buy(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.post(f"/assets/{asset_id}/transactions", json=make_transaction(type="BUY"))
    assert resp.status_code == 201
    assert resp.json()["lot_id"] is not None


def test_create_transaction_no_lot_id_for_switch(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.post(
        f"/assets/{asset_id}/transactions",
        json=make_transaction(type="SWITCH_IN", amount_inr=25000.0),
    )
    assert resp.status_code == 201
    assert resp.json()["lot_id"] is None


def test_duplicate_txn_id_returns_409(client, seeded_asset):
    asset_id = seeded_asset["id"]
    txn = make_transaction(txn_id="unique-txn-001")
    resp1 = client.post(f"/assets/{asset_id}/transactions", json=txn)
    assert resp1.status_code == 201
    resp2 = client.post(f"/assets/{asset_id}/transactions", json=txn)
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "DUPLICATE"


def test_list_transactions_ordered_by_date_desc(client, seeded_asset):
    asset_id = seeded_asset["id"]
    client.post(
        f"/assets/{asset_id}/transactions",
        json=make_transaction(date="2023-01-01", txn_id="txn-old"),
    )
    client.post(
        f"/assets/{asset_id}/transactions",
        json=make_transaction(date="2023-06-01", txn_id="txn-new"),
    )
    resp = client.get(f"/assets/{asset_id}/transactions")
    assert resp.status_code == 200
    data = resp.json()
    # Paginated response shape
    assert "items" in data
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["date"] > data["items"][1]["date"]


def test_delete_transaction_hard_deletes(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.post(f"/assets/{asset_id}/transactions", json=make_transaction())
    assert resp.status_code == 201
    txn_id = resp.json()["id"]

    del_resp = client.delete(f"/assets/{asset_id}/transactions/{txn_id}")
    assert del_resp.status_code == 204

    list_resp = client.get(f"/assets/{asset_id}/transactions")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_amount_inr_stored_as_paise_returned_as_inr(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.post(
        f"/assets/{asset_id}/transactions",
        json=make_transaction(amount_inr=-25000.0),
    )
    assert resp.status_code == 201
    assert resp.json()["amount_inr"] == -25000.0

"""Integration tests for /corp-actions API endpoints."""
from unittest.mock import MagicMock, patch


def test_fetch_all_returns_200(client):
    with patch(
        "app.api.corp_actions.CorpActionsService.process_all_stocks",
        return_value={"bonus_created": 0, "bonus_skipped": 0, "split_applied": 0,
                      "split_skipped": 0, "dividend_created": 0, "dividend_skipped": 0},
    ):
        resp = client.post("/corp-actions/fetch-all")
    assert resp.status_code == 200
    data = resp.json()
    assert "bonus_created" in data
    assert "split_applied" in data
    assert "dividend_created" in data


def test_fetch_asset_returns_200_for_stock_in(client):
    # Create a STOCK_IN asset
    asset_resp = client.post("/assets", json={
        "name": "RELIANCE",
        "asset_type": "STOCK_IN",
        "identifier": "INE002A01018",
        "asset_class": "EQUITY",
        "currency": "INR",
    })
    assert asset_resp.status_code == 201
    asset_id = asset_resp.json()["id"]

    with patch(
        "app.api.corp_actions.CorpActionsService.process_asset",
        return_value={"bonus_created": 0, "bonus_skipped": 0, "split_applied": 0,
                      "split_skipped": 0, "dividend_created": 0, "dividend_skipped": 0},
    ):
        resp = client.post(f"/corp-actions/fetch-asset/{asset_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "bonus_created" in data


def test_fetch_asset_404_for_unknown_id(client):
    resp = client.post("/corp-actions/fetch-asset/99999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_fetch_asset_422_for_non_stock_in(client):
    # Create an FD asset (not STOCK_IN)
    asset_resp = client.post("/assets", json={
        "name": "SBI FD",
        "asset_type": "FD",
        "asset_class": "DEBT",
        "currency": "INR",
    })
    assert asset_resp.status_code == 201
    asset_id = asset_resp.json()["id"]

    resp = client.post(f"/corp-actions/fetch-asset/{asset_id}")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

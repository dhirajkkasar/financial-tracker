"""Integration tests for MF scheme_category classification."""
from unittest.mock import patch
from tests.factories import make_asset


def _mf_nav_response(scheme_category: str) -> dict:
    return {
        "status": "SUCCESS",
        "meta": {"scheme_category": scheme_category},
        "data": [{"date": "01-01-2024", "nav": "50.0"}],
    }


def test_price_refresh_does_not_change_asset_class(client, db):
    """Price refresh must not modify asset_class — classification is set at import time."""
    asset = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="DEBT", name="HDFC Liquid Fund",
        identifier="INF179L", mfapi_scheme_code="119551"
    )).json()

    with patch("app.services.price_feed.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = _mf_nav_response("Debt Scheme - Liquid Fund")
        client.post(f"/assets/{asset['id']}/price/refresh")

    refreshed = client.get(f"/assets/{asset['id']}").json()
    assert refreshed["asset_class"] == "DEBT"   # unchanged from creation
    assert refreshed["scheme_category"] is None  # price refresh does not set this


def test_price_refresh_does_not_set_scheme_category(client, db):
    """scheme_category is resolved at import time; price refresh leaves it None."""
    asset = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="EQUITY", name="HDFC Balanced Fund",
        identifier="INF179H", mfapi_scheme_code="119552"
    )).json()

    with patch("app.services.price_feed.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = _mf_nav_response("Hybrid Scheme - Balanced Advantage Fund")
        client.post(f"/assets/{asset['id']}/price/refresh")

    refreshed = client.get(f"/assets/{asset['id']}").json()
    assert refreshed["asset_class"] == "EQUITY"  # price refresh does not reclassify
    assert refreshed["scheme_category"] is None


def test_scheme_category_in_asset_response(client, db):
    """scheme_category field is present in GET /assets/{id} response."""
    asset = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="EQUITY", name="Test MF",
        identifier="INF999X", mfapi_scheme_code="999999"
    )).json()
    assert "scheme_category" in asset
    assert asset["scheme_category"] is None  # before any refresh


def test_scheme_category_not_writable_via_create(client):
    """scheme_category sent in POST /assets is silently ignored.

    Guard test: scheme_category is not in AssetCreate, so it is never
    written via the API. This test never produces a RED signal.
    """
    payload = make_asset(asset_type="MF", asset_class="EQUITY", name="Test MF2", identifier="INF999Y")
    payload["scheme_category"] = "Equity Scheme - Injected"
    asset = client.post("/assets", json=payload).json()
    assert asset.get("scheme_category") is None

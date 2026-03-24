"""Integration tests for MF scheme_category classification via price refresh."""
from unittest.mock import patch
from tests.factories import make_asset


def _mf_nav_response(scheme_category: str) -> dict:
    return {
        "status": "SUCCESS",
        "meta": {"scheme_category": scheme_category},
        "data": [{"date": "01-01-2024", "nav": "50.0"}],
    }


def test_price_refresh_sets_debt_class_for_debt_mf(client, db):
    """After refresh, MF with Debt scheme_category gets asset_class=DEBT."""
    asset = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="MIXED", name="HDFC Liquid Fund",
        identifier="INF179L", mfapi_scheme_code="119551"
    )).json()

    with patch("app.services.price_feed.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = _mf_nav_response("Debt Scheme - Liquid Fund")
        client.post(f"/assets/{asset['id']}/price/refresh")

    refreshed = client.get(f"/assets/{asset['id']}").json()
    assert refreshed["asset_class"] == "DEBT"
    assert refreshed["scheme_category"] == "Debt Scheme - Liquid Fund"


def test_price_refresh_sets_equity_class_for_hybrid_mf(client, db):
    """After refresh, MF with Hybrid scheme_category gets asset_class=EQUITY."""
    asset = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="MIXED", name="HDFC Balanced Fund",
        identifier="INF179H", mfapi_scheme_code="119552"
    )).json()

    with patch("app.services.price_feed.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = _mf_nav_response("Hybrid Scheme - Balanced Advantage Fund")
        client.post(f"/assets/{asset['id']}/price/refresh")

    refreshed = client.get(f"/assets/{asset['id']}").json()
    assert refreshed["asset_class"] == "EQUITY"
    assert refreshed["scheme_category"] == "Hybrid Scheme - Balanced Advantage Fund"


def test_scheme_category_in_asset_response(client, db):
    """scheme_category field is present in GET /assets/{id} response."""
    asset = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="MIXED", name="Test MF",
        identifier="INF999X", mfapi_scheme_code="999999"
    )).json()
    assert "scheme_category" in asset
    assert asset["scheme_category"] is None  # before any refresh


def test_scheme_category_not_writable_via_create(client):
    """scheme_category sent in POST /assets is silently ignored.

    Guard test: scheme_category is not in AssetCreate, so it is never
    written via the API. This test never produces a RED signal.
    """
    payload = make_asset(asset_type="MF", asset_class="MIXED", name="Test MF2", identifier="INF999Y")
    payload["scheme_category"] = "Equity Scheme - Injected"
    asset = client.post("/assets", json=payload).json()
    assert asset.get("scheme_category") is None

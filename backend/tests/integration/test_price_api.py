import pytest
from unittest.mock import patch, MagicMock
from tests.factories import make_asset
from app.services.price_feed import PriceResult
from datetime import datetime, timedelta


def test_get_price_returns_cached(client, seeded_asset):
    asset_id = seeded_asset["id"]
    # Seed price cache directly via mock refresh
    with patch("app.api.prices.PriceService") as MockSvc:
        mock_instance = MagicMock()
        mock_cache = MagicMock()
        mock_cache.price_inr = 125000  # paise
        mock_cache.fetched_at = datetime.utcnow()
        mock_cache.source = "yfinance"
        mock_cache.is_stale = False
        mock_instance.get_price.return_value = mock_cache
        MockSvc.return_value = mock_instance
        resp = client.get(f"/assets/{asset_id}/price")
    assert resp.status_code == 200
    data = resp.json()
    assert data["price_inr"] == 1250.0  # paise→INR
    assert data["is_stale"] == False


def test_get_price_no_cache_returns_404(client, seeded_asset):
    asset_id = seeded_asset["id"]
    with patch("app.api.prices.PriceService") as MockSvc:
        mock_instance = MagicMock()
        mock_instance.get_price.return_value = None
        MockSvc.return_value = mock_instance
        resp = client.get(f"/assets/{asset_id}/price")
    assert resp.status_code == 404


def test_refresh_price_updates_cache(client, seeded_asset):
    asset_id = seeded_asset["id"]
    with patch("app.api.prices.PriceService") as MockSvc:
        mock_instance = MagicMock()
        mock_cache = MagicMock()
        mock_cache.price_inr = 125000
        mock_cache.fetched_at = datetime.utcnow()
        mock_cache.source = "yfinance"
        mock_cache.is_stale = False
        mock_instance.refresh_asset.return_value = mock_cache
        MockSvc.return_value = mock_instance
        resp = client.post(f"/assets/{asset_id}/price/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert data["price_inr"] == 1250.0


def test_refresh_price_no_feed_returns_404(client, seeded_asset):
    asset_id = seeded_asset["id"]
    with patch("app.api.prices.PriceService") as MockSvc:
        mock_instance = MagicMock()
        mock_instance.refresh_asset.return_value = None  # no fetcher
        MockSvc.return_value = mock_instance
        resp = client.post(f"/assets/{asset_id}/price/refresh")
    assert resp.status_code == 404


def test_refresh_all_returns_counts(client):
    with patch("app.api.prices.PriceService") as MockSvc:
        mock_instance = MagicMock()
        mock_instance.refresh_all.return_value = {"refreshed": 3, "skipped": 2, "failed": 0}
        MockSvc.return_value = mock_instance
        resp = client.post("/prices/refresh-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["refreshed"] == 3
    assert data["skipped"] == 2

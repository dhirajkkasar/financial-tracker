import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from app.services.price_feed import MFAPIFetcher, YFinanceFetcher, GoldFetcher, PriceResult
from app.models.asset import Asset, AssetType, AssetClass


def make_mock_asset(**kwargs):
    asset = MagicMock(spec=Asset)
    asset.id = kwargs.get("id", 1)
    asset.name = kwargs.get("name", "Test")
    asset.identifier = kwargs.get("identifier", "RELIANCE")
    asset.mfapi_scheme_code = kwargs.get("mfapi_scheme_code", None)
    asset.asset_type = kwargs.get("asset_type", AssetType.STOCK_IN)
    return asset


class TestMFAPIFetcher:
    def test_fetch_success_with_scheme_code(self):
        # mock httpx GET
        asset = make_mock_asset(
            asset_type=AssetType.MF,
            identifier="INF179KC1BS5",
            mfapi_scheme_code="125497"
        )
        mock_response = {
            "status": "SUCCESS",
            "meta": {"scheme_name": "HDFC Multi Cap Fund"},
            "data": [{"date": "19-03-2026", "nav": "19.855"}]
        }
        with patch("app.services.price_feed.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response
            fetcher = MFAPIFetcher()
            result = fetcher.fetch(asset)
        assert result is not None
        assert abs(result.price_inr - 19.855) < 0.001
        assert result.source == "mfapi"
        # Should call /mf/125497/latest directly (scheme_code known)
        mock_get.assert_called_once()
        assert "125497" in mock_get.call_args[0][0]

    def test_fetch_falls_back_to_search_when_no_scheme_code(self):
        asset = make_mock_asset(
            asset_type=AssetType.MF,
            identifier="INF179KC1BS5",
            mfapi_scheme_code=None,
            name="HDFC Multi Cap Fund"
        )
        search_response = [{"schemeCode": 125497, "schemeName": "HDFC Multi Cap Fund Direct Growth"}]
        nav_response = {
            "status": "SUCCESS",
            "data": [{"date": "19-03-2026", "nav": "19.855"}]
        }
        with patch("app.services.price_feed.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            # First call = search, second call = NAV
            mock_get.return_value.json.side_effect = [search_response, nav_response]
            fetcher = MFAPIFetcher()
            result = fetcher.fetch(asset)
        assert result is not None
        assert mock_get.call_count == 2

    def test_fetch_returns_none_on_404(self):
        asset = make_mock_asset(asset_type=AssetType.MF, mfapi_scheme_code="999999")
        with patch("app.services.price_feed.httpx.get") as mock_get:
            mock_get.return_value.status_code = 404
            fetcher = MFAPIFetcher()
            result = fetcher.fetch(asset)
        assert result is None

    def test_fetch_returns_none_on_network_error(self):
        asset = make_mock_asset(asset_type=AssetType.MF, mfapi_scheme_code="125497")
        with patch("app.services.price_feed.httpx.get") as mock_get:
            mock_get.side_effect = Exception("network error")
            fetcher = MFAPIFetcher()
            result = fetcher.fetch(asset)
        assert result is None


class TestYFinanceFetcher:
    def test_fetch_nse_stock(self):
        asset = make_mock_asset(asset_type=AssetType.STOCK_IN, identifier="RELIANCE")
        mock_ticker = MagicMock()
        mock_ticker.fast_info.last_price = 1250.50
        with patch("app.services.price_feed.yf.Ticker", return_value=mock_ticker):
            fetcher = YFinanceFetcher(suffix=".NS")
            result = fetcher.fetch(asset)
        assert result is not None
        assert abs(result.price_inr - 1250.50) < 0.01
        assert result.source == "yfinance"

    def test_fetch_us_stock_converts_to_inr(self):
        asset = make_mock_asset(asset_type=AssetType.STOCK_US, identifier="AAPL")
        mock_stock = MagicMock()
        mock_stock.fast_info.last_price = 175.0
        mock_forex = MagicMock()
        mock_forex.fast_info.last_price = 83.5

        def ticker_side_effect(symbol):
            if symbol == "USDINR=X":
                return mock_forex
            return mock_stock

        with patch("app.services.price_feed.yf.Ticker", side_effect=ticker_side_effect):
            fetcher = YFinanceFetcher(suffix="")
            result = fetcher.fetch(asset)
        assert result is not None
        assert abs(result.price_inr - 175.0 * 83.5) < 1.0

    def test_fetch_returns_none_on_error(self):
        asset = make_mock_asset(asset_type=AssetType.STOCK_IN, identifier="INVALID")
        with patch("app.services.price_feed.yf.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.fast_info = {}  # no last_price key
            fetcher = YFinanceFetcher(suffix=".NS")
            result = fetcher.fetch(asset)
        assert result is None


class TestGoldFetcher:
    def test_fetch_gold_converts_to_inr_per_gram(self):
        asset = make_mock_asset(asset_type=AssetType.GOLD, identifier="GC=F")
        mock_gold = MagicMock()
        mock_gold.fast_info.last_price = 3100.0  # USD/troy oz
        mock_forex = MagicMock()
        mock_forex.fast_info.last_price = 83.5   # USD/INR

        def ticker_side_effect(symbol):
            if symbol == "USDINR=X":
                return mock_forex
            return mock_gold

        with patch("app.services.price_feed.yf.Ticker", side_effect=ticker_side_effect):
            fetcher = GoldFetcher()
            result = fetcher.fetch(asset)
        assert result is not None
        expected = 3100.0 * 83.5 / 31.1035
        assert abs(result.price_inr - expected) < 1.0
        assert result.source == "yfinance_gold"

    def test_fetch_gold_returns_none_on_forex_failure(self):
        asset = make_mock_asset(asset_type=AssetType.GOLD)
        with patch("app.services.price_feed.yf.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.fast_info = {}
            fetcher = GoldFetcher()
            result = fetcher.fetch(asset)
        assert result is None

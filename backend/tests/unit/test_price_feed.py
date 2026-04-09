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
        # Should call /mf/125497 directly (scheme_code known)
        mock_get.assert_called_once()
        assert "125497" in mock_get.call_args[0][0]

    def test_fetch_returns_none_when_no_scheme_code(self):
        """fetch() returns None immediately when mfapi_scheme_code is not set; no HTTP call made."""
        asset = make_mock_asset(
            asset_type=AssetType.MF,
            identifier="INF179KC1BS5",
            mfapi_scheme_code=None,
            name="HDFC Multi Cap Fund"
        )
        with patch("app.services.price_feed.httpx.get") as mock_get:
            fetcher = MFAPIFetcher()
            result = fetcher.fetch(asset)
        assert result is None
        mock_get.assert_not_called()

    def test_fetch_uses_latest_url(self):
        """Fetcher calls /{scheme_code}/latest for the NAV endpoint."""
        asset = make_mock_asset(asset_type=AssetType.MF, mfapi_scheme_code="125497")
        mock_response = {
            "status": "SUCCESS",
            "meta": {},
            "data": [{"date": "19-03-2026", "nav": "19.855"}]
        }
        with patch("app.services.price_feed.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response
            fetcher = MFAPIFetcher()
            fetcher.fetch(asset)
        called_url = mock_get.call_args[0][0]
        assert called_url.endswith("/125497/latest"), f"Expected URL ending in /125497/latest, got: {called_url}"

    def test_fetch_does_not_set_resolved_scheme_category(self):
        """fetch() never sets _resolved_scheme_category — classification is import-time only."""
        asset = make_mock_asset(asset_type=AssetType.MF, mfapi_scheme_code="125497")
        mock_response = {
            "status": "SUCCESS",
            "meta": {},
            "data": [{"date": "19-03-2026", "nav": "19.855"}]
        }
        with patch("app.services.price_feed.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response
            fetcher = MFAPIFetcher()
            fetcher.fetch(asset)
        assert not hasattr(asset, "_resolved_scheme_category")

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
    def test_fetch_gold_etf_uses_yfinance_nse(self):
        """Gold ETF (GOLDBEES) should use YFinanceFetcher with NSE suffix."""
        asset = make_mock_asset(
            asset_type=AssetType.GOLD,
            name="GOLDBEES",
            identifier="GOLDBEES"
        )
        mock_ticker = MagicMock()
        mock_ticker.fast_info.last_price = 6850.50

        with patch("app.services.price_feed.yf.Ticker", return_value=mock_ticker):
            fetcher = GoldFetcher()
            result = fetcher.fetch(asset)
        assert result is not None
        assert abs(result.price_inr - 6850.50) < 0.01
        assert result.source == "yfinance"

    def test_fetch_sgb_from_nse_api(self):
        """SGB should fetch from NSE API, not goodreturns.in."""
        asset = make_mock_asset(
            asset_type=AssetType.GOLD,
            name="SGBJUN29II",
            identifier="SGBJUN29II"
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "priceInfo": {"lastPrice": 6500.0}
        }

        with patch("app.services.price_feed.httpx.get", return_value=mock_response):
            fetcher = GoldFetcher()
            result = fetcher.fetch(asset)
        assert result is not None
        assert abs(result.price_inr - 6500.0) < 0.01
        assert result.source == "NSE_SGB"

    def test_fetch_physical_gold_22k_from_goodreturns(self):
        """Physical gold (22K) should scrape goodreturns.in and parse HTML."""
        asset = make_mock_asset(
            asset_type=AssetType.GOLD,
            name="Physical Gold",
            identifier="Gold22k"
        )
        mock_html = """
        <html>
            <body>
                <p>22K Gold /g ₹7,850</p>
                <p>24K Gold /g ₹8,560</p>
            </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.status_code = 200

        with patch("app.services.price_feed.httpx.get", return_value=mock_response):
            with patch("app.services.price_feed.BeautifulSoup") as mock_bs:
                mock_soup = MagicMock()
                mock_soup.get_text.return_value = mock_html
                mock_bs.return_value = mock_soup

                fetcher = GoldFetcher()
                result = fetcher.fetch(asset)
        assert result is not None
        assert result.price_inr == 7850
        assert result.source == "GoodReturns_22K"

    def test_fetch_physical_gold_24k_from_goodreturns(self):
        """Physical gold (24K) should scrape and extract 24K price."""
        asset = make_mock_asset(
            asset_type=AssetType.GOLD,
            name="Physical Gold",
            identifier="Gold24k"
        )
        mock_html = """
        <html>
            <body>
                <p>22K Gold /g ₹7,850</p>
                <p>24K Gold /g ₹8,560</p>
            </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.status_code = 200

        with patch("app.services.price_feed.httpx.get", return_value=mock_response):
            with patch("app.services.price_feed.BeautifulSoup") as mock_bs:
                mock_soup = MagicMock()
                mock_soup.get_text.return_value = mock_html
                mock_bs.return_value = mock_soup

                fetcher = GoldFetcher()
                result = fetcher.fetch(asset)
        assert result is not None
        assert result.price_inr == 8560
        assert result.source == "GoodReturns_24K"

    def test_fetch_gold_returns_none_on_sgb_api_failure(self):
        """SGB fetch should return None on NSE API failure."""
        asset = make_mock_asset(
            asset_type=AssetType.GOLD,
            name="SGBJUN29II",
            identifier="SGBJUN29II"
        )
        with patch("app.services.price_feed.httpx.get") as mock_get:
            mock_get.side_effect = Exception("API error")
            fetcher = GoldFetcher()
            result = fetcher.fetch(asset)
        assert result is None

    def test_fetch_gold_returns_none_on_goodreturns_parse_failure(self):
        """Physical gold fetch should return None if regex doesn't match."""
        asset = make_mock_asset(
            asset_type=AssetType.GOLD,
            name="Physical Gold",
            identifier="Gold22k"
        )
        mock_html = "<html><body>No price data here</body></html>"
        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.status_code = 200

        with patch("app.services.price_feed.httpx.get", return_value=mock_response):
            with patch("app.services.price_feed.BeautifulSoup") as mock_bs:
                mock_soup = MagicMock()
                mock_soup.get_text.return_value = mock_html
                mock_bs.return_value = mock_soup

                fetcher = GoldFetcher()
                result = fetcher.fetch(asset)
        assert result is None

    def test_fetch_gold_returns_none_on_goodreturns_error(self):
        """Physical gold fetch should return None on any exception."""
        asset = make_mock_asset(
            asset_type=AssetType.GOLD,
            name="Physical Gold",
            identifier="Gold22k"
        )
        with patch("app.services.price_feed.httpx.get") as mock_get:
            mock_get.side_effect = Exception("Network error")
            fetcher = GoldFetcher()
            result = fetcher.fetch(asset)
        assert result is None

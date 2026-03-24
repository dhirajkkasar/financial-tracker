import logging
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Protocol, runtime_checkable

import httpx
import yfinance as yf

from app.models.asset import Asset, AssetType

logger = logging.getLogger(__name__)

TROY_OZ_TO_GRAMS = 31.1035


@dataclass
class PriceResult:
    price_inr: float
    source: str
    fetched_at: datetime = None

    def __post_init__(self):
        if self.fetched_at is None:
            self.fetched_at = datetime.utcnow()


@runtime_checkable
class PriceFetcher(Protocol):
    def fetch(self, asset: Asset) -> PriceResult | None: ...


class MFAPIFetcher:
    """Fetches MF NAV from mfapi.in."""
    BASE_URL = "https://api.mfapi.in/mf"

    def fetch(self, asset: Asset) -> PriceResult | None:
        try:
            scheme_code = asset.mfapi_scheme_code
            if not scheme_code:
                scheme_code = self._search_scheme_code(asset)
                if not scheme_code:
                    logger.warning("MFAPIFetcher: could not find scheme_code for %s", asset.name)
                    return None
                # Caller (PriceService) will persist scheme_code back to asset
                asset._resolved_scheme_code = str(scheme_code)

            resp = httpx.get(f"{self.BASE_URL}/{scheme_code}", timeout=10)
            if resp.status_code != 200:
                logger.warning("MFAPIFetcher: HTTP %s for scheme %s", resp.status_code, scheme_code)
                return None
            data = resp.json()
            if data.get("status") != "SUCCESS" or not data.get("data"):
                return None
            nav = float(data["data"][0]["nav"])
            scheme_category = data.get("meta", {}).get("scheme_category")
            if scheme_category:
                asset._resolved_scheme_category = scheme_category
            return PriceResult(price_inr=nav, source="mfapi")
        except Exception as e:
            logger.warning("MFAPIFetcher: error fetching %s: %s", asset.name, e)
            return None

    def _search_scheme_code(self, asset: Asset) -> str | None:
        """Search by scheme name, try to match by ISIN or name."""
        try:
            resp = httpx.get(
                f"{self.BASE_URL}/search",
                params={"q": asset.name[:40]},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            results = resp.json()
            if not results:
                return None
            # Return first result's scheme code (best-effort)
            return str(results[0]["schemeCode"])
        except Exception as e:
            logger.warning("MFAPIFetcher: search error for %s: %s", asset.name, e)
            return None


class YFinanceFetcher:
    """Fetches price from yfinance. For INR assets pass suffix='.NS', for USD pass suffix=''."""

    def __init__(self, suffix: str = ".NS", use_name_as_ticker: bool = False):
        self.suffix = suffix
        self.use_name_as_ticker = use_name_as_ticker

    @staticmethod
    def _get_price(ticker) -> float | None:
        """Try multiple yfinance price fields; fast_info.last_price fails for some exchanges."""
        # 1. fast_info (fastest, works for most US tickers)
        try:
            p = ticker.fast_info.last_price
            if p and p > 0:
                return p
        except Exception:
            pass
        # 2. info dict (slower, but reliable for NSE/BSE)
        try:
            info = ticker.info
            for key in ("currentPrice", "regularMarketPrice", "navPrice"):
                p = info.get(key)
                if p and p > 0:
                    return p
        except Exception:
            pass
        # 3. last close from recent history
        try:
            hist = ticker.history(period="5d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
        return None

    def fetch(self, asset: Asset) -> PriceResult | None:
        try:
            # Indian stocks: identifier is ISIN, but yfinance needs the NSE ticker (stored in name)
            ticker_base = asset.name if self.use_name_as_ticker else asset.identifier
            symbol = f"{ticker_base}{self.suffix}"
            ticker = yf.Ticker(symbol)
            raw_price = self._get_price(ticker)
            if raw_price is None:
                logger.warning("YFinanceFetcher: no price for %s", symbol)
                return None

            if self.suffix == "":
                # US stock — convert USD → INR
                forex = yf.Ticker("USDINR=X")
                rate = self._get_price(forex)
                if rate is None:
                    logger.warning("YFinanceFetcher: could not get USDINR rate")
                    return None
                price_inr = raw_price * rate
            else:
                price_inr = raw_price

            return PriceResult(price_inr=price_inr, source="yfinance")
        except Exception as e:
            logger.warning("YFinanceFetcher: error for %s: %s", asset.identifier, e)
            return None


class GoldFetcher:
    """Fetches gold price.

    - Gold ETFs (GOLDBEES, etc.): fetched directly from NSE via yfinance (price per ETF unit).
    - Physical gold, SGBs, other GOLD assets: GC=F → INR/gram (1 unit = 1 gram).
    """

    # NSE-listed gold ETFs whose unit price ≠ 1 gram — fetch via NSE ticker instead of GC=F
    _GOLD_ETF_TICKERS: frozenset[str] = frozenset({
        "GOLDBEES", "GOLDSHARE", "IPGETF", "PGULD", "GOLDCASE",
        "BSLGOLDETF", "LICMFGOLD", "KOTAKGOLD", "HDFCGOLD",
        "AXISGOLD", "NIPPONIGOLD", "SBIGOLD", "GOLD1D", "MAFANG",
    })

    def fetch(self, asset: Asset) -> PriceResult | None:
        ticker_name = (asset.name or "").strip().upper()
        if ticker_name in self._GOLD_ETF_TICKERS:
            # Use NSE market price for gold ETFs (unit price ≠ 1 gram)
            return YFinanceFetcher(suffix=".NS", use_name_as_ticker=True).fetch(asset)
        try:
            gold = yf.Ticker("GC=F")
            forex = yf.Ticker("USDINR=X")
            price_usd_oz = YFinanceFetcher._get_price(gold)
            rate = YFinanceFetcher._get_price(forex)
            if price_usd_oz is None or rate is None:
                logger.warning("GoldFetcher: missing price or forex rate")
                return None
            price_inr_gram = price_usd_oz * rate / TROY_OZ_TO_GRAMS
            return PriceResult(price_inr=price_inr_gram, source="yfinance_gold")
        except Exception as e:
            logger.warning("GoldFetcher: error: %s", e)
            return None


class NPSNavFetcher:
    """Fetches NPS NAV from npsnav.in.

    Usage pattern (refresh_all):
      1. Call bulk_resolve_schemes(nps_assets) once → sets asset._resolved_nps_scheme_code on each.
      2. Call fetch(asset) per asset → only does the NAV call, no scheme lookup.

    Usage pattern (refresh_asset, standalone):
      fetch() falls back to a single /api/schemes call if no code is resolved yet.
    """

    SCHEMES_URL = "https://npsnav.in/api/schemes"
    NAV_URL = "https://npsnav.in/api/{code}"

    def bulk_resolve_schemes(self, assets: list) -> None:
        """Fetch /api/schemes once and resolve scheme codes for all NPS assets.

        Always uses the freshly fetched scheme list (ignores stored identifier)
        and sets asset._resolved_nps_scheme_code on every matched asset.
        """
        schemes = self._fetch_schemes()
        if not schemes:
            return
        for asset in assets:
            code = self._best_match(asset.name, schemes)
            if code:
                if code != asset.identifier:
                    logger.info(
                        "NPSNavFetcher: %s → %s (was: %s)", asset.name, code, asset.identifier
                    )
                asset._resolved_nps_scheme_code = code
            else:
                logger.warning("NPSNavFetcher: no match for '%s'", asset.name)

    def fetch(self, asset: Asset) -> PriceResult | None:
        """Fetch NAV for a single asset. Uses _resolved_nps_scheme_code if set by
        bulk_resolve_schemes; falls back to a fresh /api/schemes lookup otherwise."""
        try:
            scheme_code = getattr(asset, "_resolved_nps_scheme_code", None)
            if not scheme_code:
                # Standalone call (refresh_asset) — do a one-off resolution
                schemes = self._fetch_schemes()
                if schemes:
                    scheme_code = self._best_match(asset.name, schemes)
                    if scheme_code:
                        asset._resolved_nps_scheme_code = scheme_code
            if not scheme_code:
                logger.warning("NPSNavFetcher: could not resolve scheme code for '%s'", asset.name)
                return None

            resp = httpx.get(self.NAV_URL.format(code=scheme_code), timeout=10)
            if resp.status_code != 200:
                logger.warning("NPSNavFetcher: HTTP %s for scheme %s", resp.status_code, scheme_code)
                return None
            nav = float(resp.text.strip())
            return PriceResult(price_inr=nav, source="npsnav.in")
        except Exception as e:
            logger.warning("NPSNavFetcher: error fetching '%s': %s", asset.name, e)
            return None

    def _fetch_schemes(self) -> list | None:
        try:
            resp = httpx.get(self.SCHEMES_URL, timeout=10)
            if resp.status_code != 200:
                logger.warning("NPSNavFetcher: /api/schemes returned HTTP %s", resp.status_code)
                return None
            data = resp.json()
            return data if isinstance(data, list) else data.get("data", [])
        except Exception as e:
            logger.warning("NPSNavFetcher: failed to fetch schemes: %s", e)
            return None

    def _best_match(self, name: str, schemes: list) -> str | None:
        name_upper = name.upper()
        best_code, best_score = None, 0.0
        for entry in schemes:
            code, scheme_name = entry[0], entry[1].upper()
            score = SequenceMatcher(None, name_upper, scheme_name).ratio()
            if score > best_score:
                best_score = score
                best_code = code
        if best_score >= 0.6:
            return best_code
        return None


# Registry: maps AssetType → fetcher instance
FETCHER_REGISTRY: dict[AssetType, PriceFetcher] = {
    AssetType.MF:         MFAPIFetcher(),
    # STOCK_IN: identifier=ISIN, name=NSE ticker (e.g. "TCS") — use name as ticker
    AssetType.STOCK_IN:   YFinanceFetcher(suffix=".NS", use_name_as_ticker=True),
    # STOCK_US / RSU: identifier=ticker (e.g. "AAPL") — use identifier
    AssetType.STOCK_US:   YFinanceFetcher(suffix=""),
    AssetType.RSU:        YFinanceFetcher(suffix=""),
    AssetType.GOLD:       GoldFetcher(),
    AssetType.NPS:        NPSNavFetcher(),
    # SGB: no live feed — skip (valuation-based in practice)
}
# PPF, EPF, FD, RD, REAL_ESTATE → no entry = no price feed

# Staleness thresholds in minutes
STALE_MINUTES: dict[AssetType, int] = {
    AssetType.MF:        1440,   # 1 day
    AssetType.NPS:       1440,   # 1 day (NAV published daily)
    AssetType.STOCK_IN:   360,   # 6 hours
    AssetType.STOCK_US:   360,
    AssetType.RSU:        360,
    AssetType.GOLD:       360,
    AssetType.SGB:        360,
}

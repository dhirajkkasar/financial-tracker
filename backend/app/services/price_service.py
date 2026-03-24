import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetType
from app.models.price_cache import PriceCache
from app.repositories.asset_repo import AssetRepository
from app.repositories.price_cache_repo import PriceCacheRepository
from app.services.price_feed import FETCHER_REGISTRY, STALE_MINUTES, NPSNavFetcher, PriceFetcher, PriceResult

logger = logging.getLogger(__name__)


class PriceService:
    def __init__(self, db: Session, fetchers: dict = None):
        self.db = db
        self.fetchers = fetchers if fetchers is not None else FETCHER_REGISTRY
        self.asset_repo = AssetRepository(db)
        self.cache_repo = PriceCacheRepository(db)

    def get_price(self, asset_id: int) -> PriceCache | None:
        """Return cached price with is_stale computed."""
        cache = self.cache_repo.get_by_asset_id(asset_id)
        if cache is None:
            return None
        asset = self.asset_repo.get_by_id(asset_id)
        if asset:
            cache.is_stale = self._is_stale(asset.asset_type, cache.fetched_at)
        return cache

    def refresh_asset(self, asset_id: int) -> PriceCache | None:
        """Fetch fresh price and upsert PriceCache. Returns None if no fetcher."""
        asset = self.asset_repo.get_by_id(asset_id)
        if not asset:
            from app.middleware.error_handler import NotFoundError
            raise NotFoundError(f"Asset {asset_id} not found")

        fetcher = self.fetchers.get(asset.asset_type)
        if not fetcher:
            logger.info("PriceService: no price feed for asset type %s", asset.asset_type)
            return None

        result = fetcher.fetch(asset)
        if result is None:
            logger.warning("PriceService: fetch failed for asset %s (%s)", asset.id, asset.name)
            # Mark existing cache as stale if present
            cache = self.cache_repo.get_by_asset_id(asset_id)
            if cache:
                cache.is_stale = True
                self.db.commit()
            return None

        # Persist resolved scheme_code if MF fetcher discovered it
        if hasattr(asset, "_resolved_scheme_code") and asset._resolved_scheme_code:
            asset.mfapi_scheme_code = asset._resolved_scheme_code
            self.db.commit()

        # Persist resolved NPS scheme code to identifier
        if hasattr(asset, "_resolved_nps_scheme_code") and asset._resolved_nps_scheme_code:
            asset.identifier = asset._resolved_nps_scheme_code
            self.db.commit()

        # Persist scheme_category and reclassify asset_class for MF assets
        if hasattr(asset, "_resolved_scheme_category") and asset._resolved_scheme_category:
            from app.engine.mf_classifier import classify_mf
            asset.scheme_category = asset._resolved_scheme_category
            asset.asset_class = classify_mf(asset.scheme_category)
            self.db.commit()

        price_paise = round(result.price_inr * 100)
        cache = self.cache_repo.upsert(
            asset_id=asset_id,
            price_inr=price_paise,
            source=result.source,
            fetched_at=result.fetched_at,
            is_stale=False,
        )
        logger.info("PriceService: refreshed price for asset %s: ₹%.2f", asset.id, result.price_inr)
        return cache

    def refresh_all(self) -> dict:
        """Refresh prices for all active assets in parallel (fetch) then sequential (write)."""
        assets = self.asset_repo.list(active=True)

        # Bulk-resolve NPS scheme codes in one /api/schemes call before the parallel fetch
        nps_fetcher = self.fetchers.get(AssetType.NPS)
        if isinstance(nps_fetcher, NPSNavFetcher):
            nps_assets = [a for a in assets if a.asset_type == AssetType.NPS]
            if nps_assets:
                nps_fetcher.bulk_resolve_schemes(nps_assets)
                for asset in nps_assets:
                    code = getattr(asset, "_resolved_nps_scheme_code", None)
                    if code and code != asset.identifier:
                        asset.identifier = code
                if any(getattr(a, "_resolved_nps_scheme_code", None) for a in nps_assets):
                    self.db.commit()

        fetchable = [(a, self.fetchers[a.asset_type]) for a in assets if a.asset_type in self.fetchers]
        skipped = len(assets) - len(fetchable)

        mf_fetchable = [(a, f) for a, f in fetchable if a.asset_type == AssetType.MF]
        other_fetchable = [(a, f) for a, f in fetchable if a.asset_type != AssetType.MF]

        def _fetch(asset_fetcher):
            asset, fetcher = asset_fetcher
            try:
                return asset, fetcher.fetch(asset)
            except Exception as e:
                logger.warning("refresh_all: fetch error for asset %s: %s", asset.id, e)
                return asset, None

        # Non-MF assets: parallel fetch
        workers = min(10, len(other_fetchable)) if other_fetchable else 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fetch_results = list(pool.map(_fetch, other_fetchable))

        # MF assets: sequential fetch with 60s delay to avoid mfapi.in throttling
        for i, asset_fetcher in enumerate(mf_fetchable):
            if i > 0:
                logger.info("refresh_all: waiting 60s before next mfapi call (%d/%d)", i + 1, len(mf_fetchable))
                time.sleep(60)
            fetch_results.append(_fetch(asset_fetcher))

        # Phase 2: sequential DB writes
        refreshed, failed = 0, 0
        for asset, result in fetch_results:
            if result is None:
                cache = self.cache_repo.get_by_asset_id(asset.id)
                if cache:
                    cache.is_stale = True
                failed += 1
                continue

            if hasattr(asset, "_resolved_scheme_code") and asset._resolved_scheme_code:
                asset.mfapi_scheme_code = asset._resolved_scheme_code
            if hasattr(asset, "_resolved_nps_scheme_code") and asset._resolved_nps_scheme_code:
                asset.identifier = asset._resolved_nps_scheme_code
            if hasattr(asset, "_resolved_scheme_category") and asset._resolved_scheme_category:
                from app.engine.mf_classifier import classify_mf
                asset.scheme_category = asset._resolved_scheme_category
                asset.asset_class = classify_mf(asset.scheme_category)

            price_paise = round(result.price_inr * 100)
            self.cache_repo.upsert(
                asset_id=asset.id,
                price_inr=price_paise,
                source=result.source,
                fetched_at=result.fetched_at,
                is_stale=False,
            )
            logger.info("refresh_all: ₹%.2f for asset %s (%s)", result.price_inr, asset.id, asset.name)
            refreshed += 1

        self.db.commit()
        return {"refreshed": refreshed, "skipped": skipped, "failed": failed}

    def _is_stale(self, asset_type: AssetType, fetched_at: datetime) -> bool:
        threshold = STALE_MINUTES.get(asset_type)
        if threshold is None:
            return False
        return datetime.utcnow() - fetched_at > timedelta(minutes=threshold)

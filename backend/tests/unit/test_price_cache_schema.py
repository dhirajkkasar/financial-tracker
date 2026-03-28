"""Tests for PriceCacheResponse schema conversion."""
from datetime import datetime
from app.schemas.price_cache import PriceCacheResponse


def test_price_cache_response_from_orm_converts_paise_to_inr():
    """from_orm_convert should divide price_inr by 100."""
    from unittest.mock import MagicMock
    obj = MagicMock()
    obj.id = 1
    obj.asset_id = 42
    obj.price_inr = 200000    # 2000 INR in paise
    obj.fetched_at = datetime(2024, 1, 1, 12, 0, 0)
    obj.source = "yfinance"
    obj.is_stale = False

    schema = PriceCacheResponse.from_orm_convert(obj)
    assert schema.id == 1
    assert schema.asset_id == 42
    assert abs(schema.price_inr - 2000.0) < 0.01
    assert schema.source == "yfinance"
    assert schema.is_stale is False


def test_price_cache_response_direct_construct():
    """PriceCacheResponse can be constructed directly."""
    schema = PriceCacheResponse(
        id=1,
        asset_id=5,
        price_inr=1500.0,
        fetched_at=datetime(2024, 6, 1),
        source="mfapi",
        is_stale=True,
    )
    assert schema.price_inr == 1500.0
    assert schema.is_stale is True

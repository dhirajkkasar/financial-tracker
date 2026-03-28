from datetime import timedelta


def test_base_price_fetcher_is_abstract():
    from app.services.price_feed import BasePriceFetcher
    import pytest
    with pytest.raises(TypeError):
        BasePriceFetcher()


def test_all_fetchers_have_staleness_threshold():
    """Each registered fetcher declares staleness_threshold as a ClassVar."""
    import app.services.price_feed  # trigger registration
    from app.services.price_feed import _FETCHER_REGISTRY

    for asset_type, cls in _FETCHER_REGISTRY.items():
        assert hasattr(cls, "staleness_threshold"), (
            f"{cls.__name__} missing staleness_threshold ClassVar"
        )
        assert isinstance(cls.staleness_threshold, timedelta), (
            f"{cls.__name__}.staleness_threshold must be timedelta"
        )


def test_mfapi_fetcher_staleness_is_one_day():
    from app.services.price_feed import MFAPIFetcher
    assert MFAPIFetcher.staleness_threshold == timedelta(days=1)


def test_yfinance_fetcher_staleness_is_six_hours():
    from app.services.price_feed import YFinanceFetcher
    assert YFinanceFetcher.staleness_threshold == timedelta(hours=6)

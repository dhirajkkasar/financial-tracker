import pytest
from datetime import date, datetime
from unittest.mock import MagicMock
from app.schemas.responses.returns import AssetReturnsResponse


def _make_asset(asset_id=1, name="Test", asset_type="STOCK_IN", is_active=True):
    asset = MagicMock()
    asset.id = asset_id
    asset.name = name
    asset.asset_type = MagicMock()
    asset.asset_type.value = asset_type
    asset.is_active = is_active
    return asset


def _make_txn(type_val, amount_inr_paise, txn_date=None, units=None, lot_id=None, price_pu=None):
    t = MagicMock()
    t.type.value = type_val
    t.amount_inr = amount_inr_paise
    t.date = txn_date or date(2024, 1, 1)
    t.units = units
    t.lot_id = lot_id
    t.id = 1
    t.price_per_unit = price_pu
    return t


def _make_uow(transactions=None, price=None, valuations=None, fd_detail=None, snap=None):
    uow = MagicMock()
    uow.transactions.list_by_asset.return_value = transactions or []
    uow.price_cache.get_by_asset_id.return_value = price
    uow.valuations.list_by_asset.return_value = valuations or []
    uow.fd.get_by_asset_id.return_value = fd_detail
    uow.cas_snapshots.get_latest_by_asset_id.return_value = snap
    return uow


def test_strategy_registry_raises_for_unknown_type():
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry
    from app.models.asset import AssetType

    registry = DefaultReturnsStrategyRegistry()
    with pytest.raises(ValueError, match="No returns strategy"):
        registry.get("UNKNOWN_TYPE")


def test_strategy_registry_has_all_asset_types():
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry

    registry = DefaultReturnsStrategyRegistry()
    expected_types = [
        "STOCK_IN", "STOCK_US", "RSU", "MF", "NPS",
        "GOLD", "SGB", "FD", "RD", "PPF", "REAL_ESTATE", "EPF",
    ]
    for at in expected_types:
        strategy = registry.get(at)
        assert strategy is not None, f"No strategy for {at}"


def test_returns_service_get_asset_returns_dispatches_to_strategy():
    from app.services.returns.returns_service import ReturnsService
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry
    from app.middleware.error_handler import NotFoundError

    class FakeUoW:
        class FakeAssets:
            def get_by_id(self, id):
                return None  # simulate not found
        assets = FakeAssets()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    service = ReturnsService(
        uow_factory=lambda: FakeUoW(),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )
    with pytest.raises(NotFoundError):
        service.get_asset_returns(999)


# ── AssetReturnsStrategy base ──────────────────────────────────────────────

def test_base_strategy_get_invested_value_sums_outflows():
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF")
    txns = [
        _make_txn("CONTRIBUTION", -1000000),   # -₹10,000 in paise (outflow)
        _make_txn("CONTRIBUTION", -500000),    # -₹5,000
        _make_txn("INTEREST", 100000),         # +₹1,000 (not outflow)
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.get_invested_value(asset, uow)
    assert abs(result - 15000.0) < 0.01  # 10000 + 5000


def test_base_strategy_build_cashflows_excludes_excluded_types():
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF")
    txns = [
        _make_txn("CONTRIBUTION", -500000, date(2023, 1, 1)),
        _make_txn("SWITCH_IN", -100000, date(2023, 6, 1)),   # excluded
        _make_txn("SWITCH_OUT", 100000, date(2023, 7, 1)),   # excluded
        _make_txn("INTEREST", 50000, date(2024, 1, 1)),
    ]
    uow = _make_uow(transactions=txns)
    flows = strategy.build_cashflows(asset, uow)
    # SWITCH_IN and SWITCH_OUT excluded — 2 flows remain
    assert len(flows) == 2
    # CONTRIBUTION: amount_inr=-500000 paise → INR=-5000, cashflow=+5000 (negated)
    assert flows[0] == (date(2023, 1, 1), 5000.0)
    # INTEREST: amount_inr=+50000 paise → INR=+500, cashflow=-500 (negated)
    assert flows[1] == (date(2024, 1, 1), -500.0)


def test_base_strategy_compute_lots_returns_empty_list():
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF")
    uow = _make_uow()
    assert strategy.compute_lots(asset, uow) == []


# ── ValuationBasedStrategy ─────────────────────────────────────────────────

def test_valuation_based_get_current_value_returns_latest():
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF")
    v1 = MagicMock(); v1.date = date(2023, 1, 1); v1.value_inr = 500000  # paise = ₹5000
    v2 = MagicMock(); v2.date = date(2024, 1, 1); v2.value_inr = 700000  # paise = ₹7000 (latest)
    uow = _make_uow(valuations=[v1, v2])
    result = strategy.get_current_value(asset, uow)
    assert abs(result - 7000.0) < 0.01


def test_valuation_based_get_current_value_no_valuations_returns_none():
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF")
    uow = _make_uow(valuations=[])
    assert strategy.get_current_value(asset, uow) is None


def test_valuation_based_compute_no_valuation_includes_message():
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF")
    uow = _make_uow(valuations=[], transactions=[])
    result = strategy.compute(asset, uow)
    assert result.current_value is None
    assert result.message is not None
    assert "valuation" in result.message.lower()


def test_valuation_based_compute_with_valuation_no_message():
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF")
    v = MagicMock(); v.date = date(2024, 1, 1); v.value_inr = 1000000  # ₹10,000
    txn = _make_txn("CONTRIBUTION", -500000, date(2023, 1, 1))
    uow = _make_uow(valuations=[v], transactions=[txn])
    result = strategy.compute(asset, uow)
    assert result.current_value is not None
    assert result.message is None


# ── FDStrategy ─────────────────────────────────────────────────────────────

def _make_fd_detail(principal_paise=10_000_000, rate_pct=8.0, compounding="QUARTERLY",
                    start_date=None, maturity_date=None):
    from app.models.fd_detail import CompoundingType, FDType
    fd = MagicMock()
    fd.principal_amount = principal_paise
    fd.interest_rate_pct = rate_pct
    fd.compounding = MagicMock()
    fd.compounding.value = compounding
    fd.start_date = start_date or date(2023, 1, 1)
    fd.maturity_date = maturity_date or date(2026, 1, 1)
    fd.fd_type = MagicMock()
    fd.fd_type.value = "FD"
    return fd


def test_fd_strategy_get_current_value_no_fd_detail_returns_none():
    from app.services.returns.strategies.asset_types.fd import FDStrategy
    strategy = FDStrategy()
    asset = _make_asset(asset_type="FD")
    uow = _make_uow(fd_detail=None)
    assert strategy.get_current_value(asset, uow) is None


def test_fd_strategy_get_current_value_returns_accrued():
    from app.services.returns.strategies.asset_types.fd import FDStrategy
    strategy = FDStrategy()
    asset = _make_asset(asset_type="FD")
    fd = _make_fd_detail(
        principal_paise=10_000_000,  # ₹1,00,000
        rate_pct=8.0, compounding="QUARTERLY",
        start_date=date(2023, 1, 1), maturity_date=date(2026, 1, 1),
    )
    uow = _make_uow(fd_detail=fd)
    result = strategy.get_current_value(asset, uow)
    assert result is not None
    assert result > 100000.0  # should have accrued interest


def test_fd_strategy_compute_includes_maturity_amount():
    from app.services.returns.strategies.asset_types.fd import FDStrategy
    strategy = FDStrategy()
    asset = _make_asset(asset_type="FD")
    fd = _make_fd_detail(
        principal_paise=10_000_000,
        rate_pct=8.0, compounding="QUARTERLY",
        start_date=date(2023, 1, 1), maturity_date=date(2026, 1, 1),
    )
    interest_txn = _make_txn("INTEREST", 500000, date(2024, 1, 1))  # ₹5,000 interest
    contrib_txn = _make_txn("CONTRIBUTION", -10_000_000, date(2023, 1, 1))
    v = MagicMock(); v.date = date(2024, 1, 1); v.value_inr = 11_000_000
    uow = _make_uow(fd_detail=fd, transactions=[contrib_txn, interest_txn], valuations=[v])
    result = strategy.compute(asset, uow)
    assert result.maturity_amount is not None
    assert result.maturity_amount > 100000.0
    assert result.taxable_interest is not None
    assert abs(result.taxable_interest - 5000.0) < 0.01
    assert result.potential_tax_30pct is not None


# ── RDStrategy ─────────────────────────────────────────────────────────────

def test_rd_strategy_get_invested_value_sums_contributions():
    from app.services.returns.strategies.asset_types.rd import RDStrategy
    strategy = RDStrategy()
    asset = _make_asset(asset_type="RD")
    txns = [
        _make_txn("CONTRIBUTION", -500000),   # ₹5,000
        _make_txn("CONTRIBUTION", -500000),   # ₹5,000
        _make_txn("INTEREST", 100000),        # not a contribution
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.get_invested_value(asset, uow)
    assert abs(result - 10000.0) < 0.01


def test_rd_strategy_get_current_value_no_fd_detail_returns_none():
    from app.services.returns.strategies.asset_types.rd import RDStrategy
    strategy = RDStrategy()
    asset = _make_asset(asset_type="RD")
    uow = _make_uow(fd_detail=None)
    assert strategy.get_current_value(asset, uow) is None


def test_rd_strategy_get_current_value_returns_accrued():
    from app.services.returns.strategies.asset_types.rd import RDStrategy
    strategy = RDStrategy()
    asset = _make_asset(asset_type="RD")
    fd = _make_fd_detail(
        principal_paise=500000,   # ₹5,000 monthly installment
        rate_pct=7.0, compounding="QUARTERLY",
        start_date=date(2022, 1, 1), maturity_date=date(2023, 1, 1),
    )
    uow = _make_uow(fd_detail=fd)
    result = strategy.get_current_value(asset, uow)
    assert result is not None
    assert result >= 0


# ── EPFStrategy ────────────────────────────────────────────────────────────

def test_epf_strategy_get_invested_value():
    from app.services.returns.strategies.asset_types.epf import EPFStrategy
    strategy = EPFStrategy()
    asset = _make_asset(asset_type="EPF")
    txns = [
        _make_txn("CONTRIBUTION", -1200000),   # ₹12,000
        _make_txn("CONTRIBUTION", -1200000),   # ₹12,000
        _make_txn("INTEREST", 240000),         # not contribution
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.get_invested_value(asset, uow)
    assert abs(result - 24000.0) < 0.01


def test_epf_strategy_get_current_value_invested_plus_interest():
    from app.services.returns.strategies.asset_types.epf import EPFStrategy
    strategy = EPFStrategy()
    asset = _make_asset(asset_type="EPF")
    txns = [
        _make_txn("CONTRIBUTION", -1200000),   # ₹12,000 outflow
        _make_txn("INTEREST", 240000),         # ₹2,400 inflow
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.get_current_value(asset, uow)
    # invested=12000, interest=2400 → 14400
    assert abs(result - 14400.0) < 0.01


# ── MFStrategy ─────────────────────────────────────────────────────────────

def test_mf_strategy_no_snapshot_raises_validation_error():
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    from app.middleware.error_handler import ValidationError
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF", name="Test Fund")
    uow = _make_uow(snap=None)
    with pytest.raises(ValidationError, match="CAS snapshot"):
        strategy.get_current_value(asset, uow)


def test_mf_strategy_fresh_snapshot_uses_market_value():
    from datetime import timedelta
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF")
    snap = MagicMock()
    snap.date = date.today() - timedelta(days=5)   # fresh (< 30 days)
    snap.market_value_inr = 12_000_000  # paise = ₹1,20,000
    snap.closing_units = 1000.0
    uow = _make_uow(snap=snap)
    result = strategy.get_current_value(asset, uow)
    assert abs(result - 120000.0) < 0.01


def test_mf_strategy_stale_snapshot_with_price_uses_units_x_nav():
    from datetime import timedelta
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF")
    snap = MagicMock()
    snap.date = date.today() - timedelta(days=45)   # stale (> 30 days)
    snap.market_value_inr = 11_000_000
    snap.closing_units = 1000.0
    price = MagicMock()
    price.price_inr = 13000   # ₹130/unit in paise
    uow = _make_uow(snap=snap, price=price)
    result = strategy.get_current_value(asset, uow)
    assert abs(result - 130000.0) < 0.01   # 1000 units × ₹130


def test_mf_strategy_stale_snapshot_no_price_falls_back():
    from datetime import timedelta
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF")
    snap = MagicMock()
    snap.date = date.today() - timedelta(days=45)
    snap.market_value_inr = 11_000_000  # ₹1,10,000
    snap.closing_units = 1000.0
    uow = _make_uow(snap=snap, price=None)
    result = strategy.get_current_value(asset, uow)
    assert abs(result - 110000.0) < 0.01   # falls back to snapshot value


# ── MarketBasedStrategy (via StockINStrategy) ──────────────────────────────

def test_market_based_get_current_value_no_price_returns_none():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    uow = _make_uow(price=None, transactions=[])
    result = strategy.get_current_value(asset, uow)
    assert result is None


def test_market_based_get_current_value_units_times_price():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    price = MagicMock()
    price.price_inr = 200000   # ₹2000 in paise
    txns = [
        _make_txn("BUY", -20000000, units=100.0),    # buy 100 units
        _make_txn("SELL", 10000000, units=40.0),     # sell 40
    ]
    uow = _make_uow(price=price, transactions=txns)
    result = strategy.get_current_value(asset, uow)
    # 100 - 40 = 60 units × ₹2000 = ₹1,20,000
    assert abs(result - 120000.0) < 0.01


def test_market_based_compute_returns_response():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    price = MagicMock()
    price.price_inr = 200000   # ₹2000 in paise
    price.is_stale = False
    price.fetched_at = MagicMock()
    price.fetched_at.isoformat.return_value = "2024-01-01T00:00:00"
    txn = _make_txn("BUY", -10000000, date(2023, 1, 1), units=50.0, lot_id="lot1", price_pu=2000.0)
    uow = _make_uow(price=price, transactions=[txn])
    result = strategy.compute(asset, uow)
    assert result.asset_id == asset.id
    assert result.current_value is not None


def test_market_based_compute_lots_returns_list():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    price = MagicMock()
    price.price_inr = 200000   # ₹2000/unit
    price.is_stale = False
    price.fetched_at = MagicMock()
    price.fetched_at.isoformat.return_value = "2024-01-01T00:00:00"
    txn = _make_txn("BUY", -10000000, date(2023, 1, 1), units=50.0, lot_id="lot1", price_pu=2000.0)
    uow = _make_uow(price=price, transactions=[txn])
    lots = strategy.compute_lots(asset, uow)
    assert isinstance(lots, list)
    assert len(lots) > 0
    assert lots[0].lot_id is not None


def test_market_based_compute_lots_empty_when_no_price():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    uow = _make_uow(price=None)
    lots = strategy.compute_lots(asset, uow)
    assert lots == []


def test_market_based_lots_data_with_sell_reduces_remaining():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    price = MagicMock()
    price.price_inr = 300000  # ₹3000/unit
    price.is_stale = False
    price.fetched_at = MagicMock()
    price.fetched_at.isoformat.return_value = "2024-01-01T00:00:00"
    buy = _make_txn("BUY", -10000000, date(2022, 1, 1), units=100.0, lot_id="lot1", price_pu=1000.0)
    sell = _make_txn("SELL", 5000000, date(2023, 1, 1), units=50.0)
    uow = _make_uow(price=price, transactions=[buy, sell])
    lots = strategy.compute_lots(asset, uow)
    # 100 - 50 sold = 50 remaining in lot
    assert len(lots) == 1
    assert abs(lots[0].units - 50.0) < 0.01


def test_market_based_bonus_lot_buy_price_is_zero():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    price = MagicMock()
    price.price_inr = 200000  # ₹2000/unit
    price.is_stale = False
    price.fetched_at = MagicMock()
    price.fetched_at.isoformat.return_value = "2024-01-01T00:00:00"
    buy = _make_txn("BUY", -10000000, date(2023, 1, 1), units=100.0, lot_id="lot1", price_pu=1000.0)
    bonus = _make_txn("BONUS", 0, date(2023, 6, 1), units=10.0, lot_id="lot2")
    uow = _make_uow(price=price, transactions=[buy, bonus])
    lots = strategy.compute_lots(asset, uow)
    bonus_lot = next((l for l in lots if abs(l.buy_price_per_unit) < 0.01), None)
    assert bonus_lot is not None


# ── ReturnsService ─────────────────────────────────────────────────────────

def test_returns_service_get_all_returns_empty():
    from app.services.returns.returns_service import ReturnsService
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry

    class FakeUoW:
        class FakeAssets:
            def list(self, active=None): return []
        assets = FakeAssets()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    service = ReturnsService(
        uow_factory=lambda: FakeUoW(),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )
    results = service.get_all_returns()
    assert results == []


def test_returns_service_get_all_returns_skips_on_exception():
    from app.services.returns.returns_service import ReturnsService
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry

    failing_asset = _make_asset(asset_id=1, asset_type="MF")  # MF raises if no snapshot

    class FakeUoW:
        class FakeAssets:
            def list(self, active=None): return [failing_asset]
        assets = FakeAssets()
        cas_snapshots = MagicMock()
        cas_snapshots.get_latest_by_asset_id.return_value = None
        transactions = MagicMock()
        transactions.list_by_asset.return_value = []
        def __enter__(self): return self
        def __exit__(self, *a): pass

    service = ReturnsService(
        uow_factory=lambda: FakeUoW(),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )
    results = service.get_all_returns()
    # MF with no snapshot raises ValidationError — should be caught and skipped
    assert results == []


def test_returns_service_get_asset_lots_not_found_raises():
    from app.services.returns.returns_service import ReturnsService
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry
    from app.middleware.error_handler import NotFoundError

    class FakeUoW:
        class FakeAssets:
            def get_by_id(self, id): return None
        assets = FakeAssets()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    service = ReturnsService(
        uow_factory=lambda: FakeUoW(),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )
    with pytest.raises(NotFoundError):
        service.get_asset_lots(999)


def test_returns_service_get_asset_lots_returns_paginated():
    from app.services.returns.returns_service import ReturnsService
    from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry

    asset = _make_asset(asset_id=1, asset_type="STOCK_IN")
    price = MagicMock()
    price.price_inr = 200000
    price.is_stale = False
    price.fetched_at = MagicMock()
    price.fetched_at.isoformat.return_value = "2024-01-01T00:00:00"
    buy = _make_txn("BUY", -10000000, date(2023, 1, 1), units=50.0, lot_id="lot1", price_pu=2000.0)

    class FakeUoW:
        class FakeAssets:
            def get_by_id(self, id): return asset
        assets = FakeAssets()
        transactions = MagicMock()
        transactions.list_by_asset.return_value = [buy]
        price_cache = MagicMock()
        price_cache.get_by_asset_id.return_value = price
        def __enter__(self): return self
        def __exit__(self, *a): pass

    service = ReturnsService(
        uow_factory=lambda: FakeUoW(),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )
    response = service.get_asset_lots(1, page=1, size=50)
    assert response.total >= 0
    assert response.page == 1
    assert response.size == 50

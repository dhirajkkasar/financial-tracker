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

def test_mf_strategy_active_uses_price_cache_nav():
    """Active MF: current_value = units × price_cache NAV."""
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF")
    price = MagicMock()
    price.price_inr = 15000  # ₹150/unit in paise
    price.is_stale = False
    price.fetched_at = None
    sip = _make_txn("SIP", -10_000_000, date(2022, 1, 1), units=1000.0)
    uow = _make_uow(transactions=[sip], price=price)
    result = strategy.get_current_value(asset, uow)
    assert abs(result - 150000.0) < 0.01  # 1000 units × ₹150


def test_mf_strategy_no_price_returns_none():
    """Active MF with no price_cache entry: current_value is None."""
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF")
    sip = _make_txn("SIP", -10_000_000, date(2022, 1, 1), units=1000.0)
    uow = _make_uow(transactions=[sip], price=None)
    result = strategy.get_current_value(asset, uow)
    assert result is None


def test_mf_strategy_inactive_returns_realised_gains():
    """Fully redeemed MF: alltime_pnl = st_realised + lt_realised from lot engine."""
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF", is_active=False)
    price = MagicMock()
    price.price_inr = 0
    price.is_stale = False
    price.fetched_at = None
    # SIP: 1000 units for ₹1,00,000; REDEMPTION: 1000 units for ₹1,20,000 (₹20k gain)
    sip = _make_txn("SIP", -10_000_000, date(2022, 1, 1), units=1000.0, price_pu=100.0)
    redemption = _make_txn("REDEMPTION", 12_000_000, date(2023, 6, 1), units=1000.0)
    uow = _make_uow(transactions=[sip, redemption], price=price)
    result = strategy.compute(asset, uow)
    assert result.current_value == 0.0
    assert result.alltime_pnl is not None
    assert result.alltime_pnl > 0  # realised gain from the sell
    # At least one of the realised buckets must be populated
    assert (result.st_realised_gain or 0.0) + (result.lt_realised_gain or 0.0) > 0


def test_mf_strategy_inactive_xirr_computed():
    """Fully redeemed MF: XIRR is computed from transaction cashflows."""
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF", is_active=False)
    price = MagicMock()
    price.price_inr = 0
    price.is_stale = False
    price.fetched_at = None
    sip = _make_txn("SIP", -10_000_000, date(2022, 1, 1), units=1000.0, price_pu=100.0)
    redemption = _make_txn("REDEMPTION", 12_000_000, date(2023, 1, 1), units=1000.0)
    uow = _make_uow(transactions=[sip, redemption], price=price)
    result = strategy.compute(asset, uow)
    assert result.xirr is not None
    assert result.xirr > 0


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


def test_market_based_compute_alltime_pnl_includes_realised():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    price = MagicMock()
    price.price_inr = 300000  # ₹3000/unit
    price.is_stale = False
    price.fetched_at = MagicMock()
    price.fetched_at.isoformat.return_value = "2024-01-01T00:00:00"
    # Buy 100 units at ₹1000 each
    buy = _make_txn("BUY", -100_000_000, date(2020, 1, 1), units=100.0, lot_id="lot1", price_pu=1000.0)
    # Sell 50 units at ₹2000 each = ₹1,00,000 inflow (realised ₹50,000 gain)
    sell = _make_txn("SELL", 20_000_000, date(2022, 1, 1), units=50.0)
    uow = _make_uow(price=price, transactions=[buy, sell])
    result = strategy.compute(asset, uow)
    # Realised: sold 50 units at ₹2000 cost ₹50,000 → gain ₹50,000
    assert result.alltime_pnl is not None
    # alltime_pnl >= current_pnl (includes realised)
    assert result.alltime_pnl >= (result.current_pnl or 0)
    assert result.st_realised_gain is not None or result.lt_realised_gain is not None


def test_market_based_compute_sets_total_units_avg_price_current_price():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    price = MagicMock()
    price.price_inr = 200000   # ₹2000/unit
    price.is_stale = False
    price.fetched_at = MagicMock()
    price.fetched_at.isoformat.return_value = "2024-01-01T00:00:00"
    buy = _make_txn("BUY", -20_000_000, date(2023, 1, 1), units=100.0, lot_id="lot1", price_pu=2000.0)
    uow = _make_uow(price=price, transactions=[buy])
    result = strategy.compute(asset, uow)
    assert abs((result.total_units or 0) - 100.0) < 0.01
    assert result.avg_price is not None
    assert abs((result.current_price or 0) - 2000.0) < 0.01


def test_market_based_compute_sets_cagr():
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    price = MagicMock()
    price.price_inr = 400000   # ₹4000/unit
    price.is_stale = False
    price.fetched_at = MagicMock()
    price.fetched_at.isoformat.return_value = "2024-01-01T00:00:00"
    # Buy 2 years ago at ₹2000 each
    buy_date = date(2024, 1, 1)   # the test is run with today=2026-03-31
    buy = _make_txn("BUY", -400_000_000, buy_date, units=100.0, lot_id="lot1", price_pu=2000.0)
    uow = _make_uow(price=price, transactions=[buy])
    result = strategy.compute(asset, uow)
    assert result.cagr is not None


# ── FDStrategy additional ──────────────────────────────────────────────────

def test_fd_strategy_compute_days_to_maturity_and_accrued():
    from app.services.returns.strategies.asset_types.fd import FDStrategy
    strategy = FDStrategy()
    asset = _make_asset(asset_type="FD")
    fd = _make_fd_detail(
        principal_paise=10_000_000,
        rate_pct=8.0, compounding="QUARTERLY",
        start_date=date(2024, 1, 1), maturity_date=date(2027, 1, 1),
    )
    contrib = _make_txn("CONTRIBUTION", -10_000_000, date(2024, 1, 1))
    uow = _make_uow(fd_detail=fd, transactions=[contrib], valuations=[])
    result = strategy.compute(asset, uow)
    assert result.accrued_value_today is not None
    assert result.days_to_maturity is not None
    assert result.days_to_maturity >= 0


def test_fd_strategy_taxable_interest_formula_based():
    from app.services.returns.strategies.asset_types.fd import FDStrategy
    strategy = FDStrategy()
    asset = _make_asset(asset_type="FD")
    # Cumulative FD — no INTEREST transactions posted yet
    fd = _make_fd_detail(
        principal_paise=10_000_000,
        rate_pct=8.0, compounding="QUARTERLY",
        start_date=date(2024, 1, 1), maturity_date=date(2027, 1, 1),
    )
    contrib = _make_txn("CONTRIBUTION", -10_000_000, date(2024, 1, 1))
    uow = _make_uow(fd_detail=fd, transactions=[contrib], valuations=[])
    result = strategy.compute(asset, uow)
    # Taxable interest should be formula-based (accrued - invested), not 0
    assert result.taxable_interest is not None
    assert result.taxable_interest >= 0


# ── RDStrategy additional ──────────────────────────────────────────────────

def test_rd_strategy_xirr_uses_maturity_amount():
    from app.services.returns.strategies.asset_types.rd import RDStrategy
    strategy = RDStrategy()
    asset = _make_asset(asset_type="RD")
    fd = _make_fd_detail(
        principal_paise=500_000,   # ₹5,000/month
        rate_pct=7.0, compounding="QUARTERLY",
        start_date=date(2023, 1, 1), maturity_date=date(2024, 1, 1),
    )
    contribs = [_make_txn("CONTRIBUTION", -500_000, date(2023, i, 1)) for i in range(1, 13)]
    uow = _make_uow(fd_detail=fd, transactions=contribs)
    result = strategy.compute(asset, uow)
    # XIRR must be computable (maturity_amount terminal was appended)
    assert result.xirr is not None
    # XIRR should be roughly 7% for an RD at 7% interest
    assert 0.04 < result.xirr < 0.12


# ── EPFStrategy additional ─────────────────────────────────────────────────

def test_epf_strategy_xirr_excludes_interest_in_cashflows():
    from app.services.returns.strategies.asset_types.epf import EPFStrategy
    strategy = EPFStrategy()
    asset = _make_asset(asset_type="EPF")
    txns = [
        _make_txn("CONTRIBUTION", -1_200_000, date(2023, 1, 1)),  # ₹12,000
        _make_txn("CONTRIBUTION", -1_200_000, date(2023, 4, 1)),  # ₹12,000
        _make_txn("INTEREST", 480_000, date(2023, 12, 31)),       # ₹4,800 interest
    ]
    uow = _make_uow(transactions=txns)
    flows = strategy.build_cashflows(asset, uow)
    # Only 2 flows from CONTRIBUTION — INTEREST must NOT appear
    assert len(flows) == 2
    assert all(f[1] > 0 for f in flows)   # outflows negated → positive


# ── get_portfolio_cashflows — base (MarketBasedStrategy) ──────────────────

def test_base_get_portfolio_cashflows_includes_all_non_excluded():
    """Market-based: inflows + outflows, raw DB sign, SWITCH_IN/OUT excluded."""
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    txns = [
        _make_txn("BUY",       -10_000_000, date(2023, 1, 1)),   # outflow → negative
        _make_txn("SELL",       5_000_000,  date(2023, 6, 1)),   # inflow  → positive
        _make_txn("DIVIDEND",     100_000,  date(2023, 9, 1)),   # inflow  → positive
        _make_txn("SWITCH_IN",  -200_000,   date(2023, 3, 1)),   # excluded
        _make_txn("SWITCH_OUT",  200_000,   date(2023, 4, 1)),   # excluded
    ]
    uow = _make_uow(transactions=txns)
    flows = strategy.get_portfolio_cashflows(asset, uow)
    assert len(flows) == 3
    # BUY is negative (raw DB sign preserved)
    buy_flow = next(f for f in flows if f[0] == date(2023, 1, 1))
    assert buy_flow[1] == -100_000.0   # -10_000_000 paise / 100
    # SELL is positive
    sell_flow = next(f for f in flows if f[0] == date(2023, 6, 1))
    assert sell_flow[1] == 50_000.0


def test_base_get_portfolio_cashflows_split_excluded():
    """SPLIT transactions must be excluded from portfolio cashflows."""
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN")
    txns = [
        _make_txn("BUY",   -5_000_000, date(2023, 1, 1)),
        _make_txn("SPLIT",          0, date(2023, 6, 1)),
    ]
    uow = _make_uow(transactions=txns)
    flows = strategy.get_portfolio_cashflows(asset, uow)
    assert len(flows) == 1
    assert flows[0][0] == date(2023, 1, 1)


# ── get_portfolio_cashflows — ValuationBasedStrategy (outflow-only) ────────

def test_valuation_based_get_portfolio_cashflows_outflows_only():
    """PPF/EPF/FD/RD: only CONTRIBUTION outflows, no INTEREST inflows."""
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF")
    txns = [
        _make_txn("CONTRIBUTION", -1_000_000, date(2023, 1, 1)),  # outflow
        _make_txn("CONTRIBUTION", -1_000_000, date(2024, 1, 1)),  # outflow
        _make_txn("INTEREST",        500_000, date(2024, 3, 1)),  # inflow — must be excluded
    ]
    uow = _make_uow(transactions=txns)
    flows = strategy.get_portfolio_cashflows(asset, uow)
    assert len(flows) == 2
    # Both flows should be negative (outflows in raw DB sign)
    assert all(f[1] < 0 for f in flows)


def test_epf_get_portfolio_cashflows_outflows_only():
    """EPF inherits ValuationBasedStrategy: interest excluded from portfolio cashflows."""
    from app.services.returns.strategies.asset_types.epf import EPFStrategy
    strategy = EPFStrategy()
    asset = _make_asset(asset_type="EPF")
    txns = [
        _make_txn("CONTRIBUTION", -2_400_000, date(2023, 1, 1)),
        _make_txn("INTEREST",        480_000, date(2023, 12, 31)),
        _make_txn("TRANSFER",        100_000, date(2024, 1, 1)),   # inflow — excluded
    ]
    uow = _make_uow(transactions=txns)
    flows = strategy.get_portfolio_cashflows(asset, uow)
    assert len(flows) == 1
    assert flows[0][1] == -24_000.0   # -2_400_000 paise / 100


def test_fd_get_portfolio_cashflows_no_maturity_terminal():
    """FDStrategy inherits ValuationBasedStrategy: no maturity terminal in portfolio cashflows."""
    from app.services.returns.strategies.asset_types.fd import FDStrategy
    strategy = FDStrategy()
    asset = _make_asset(asset_type="FD")
    fd = _make_fd_detail(
        principal_paise=10_000_000,
        rate_pct=8.0, compounding="QUARTERLY",
        start_date=date(2023, 1, 1), maturity_date=date(2026, 1, 1),
    )
    contrib = _make_txn("CONTRIBUTION", -10_000_000, date(2023, 1, 1))
    uow = _make_uow(fd_detail=fd, transactions=[contrib])
    flows = strategy.get_portfolio_cashflows(asset, uow)
    # Only the CONTRIBUTION outflow — no maturity amount appended
    assert len(flows) == 1
    assert flows[0][1] == -100_000.0   # principal in INR


# ── get_inactive_realized_gain — base (MarketBasedStrategy) ───────────────

def test_base_get_inactive_realized_gain_returns_none():
    """Market-based assets handle realized gains via lot engine — base returns None."""
    from app.services.returns.strategies.asset_types.stock_in import StockINStrategy
    strategy = StockINStrategy()
    asset = _make_asset(asset_type="STOCK_IN", is_active=False)
    uow = _make_uow()
    assert strategy.get_inactive_realized_gain(asset, uow) is None


# ── get_inactive_realized_gain — ValuationBasedStrategy ───────────────────

def test_valuation_based_get_inactive_realized_gain_returns_terminal_gain():
    """PPF inactive: returns last_valuation - contributions."""
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF", is_active=False)
    v = MagicMock()
    v.date = date(2024, 1, 1)
    v.value_inr = 15_000_000   # ₹1,50,000
    txns = [
        _make_txn("CONTRIBUTION", -10_000_000, date(2020, 1, 1)),  # ₹1,00,000 total invested
        _make_txn("CONTRIBUTION",  -2_000_000, date(2021, 1, 1)),
    ]
    uow = _make_uow(valuations=[v], transactions=txns)
    gain = strategy.get_inactive_realized_gain(asset, uow)
    # current_value=150000, invested=120000 → gain=30000
    assert gain is not None
    assert abs(gain - 30_000.0) < 0.01


def test_valuation_based_get_inactive_realized_gain_no_valuation_returns_none():
    """No valuation entry → current_value is None → return None."""
    from app.services.returns.strategies.asset_types.ppf import PPFStrategy
    strategy = PPFStrategy()
    asset = _make_asset(asset_type="PPF", is_active=False)
    uow = _make_uow(valuations=[], transactions=[])
    assert strategy.get_inactive_realized_gain(asset, uow) is None


def test_fd_get_inactive_realized_gain_returns_earned_interest():
    """Matured FD: realized gain = maturity_amount - principal."""
    from app.services.returns.strategies.asset_types.fd import FDStrategy
    strategy = FDStrategy()
    asset = _make_asset(asset_type="FD", is_active=False)
    # FD matured 1 year ago
    fd = _make_fd_detail(
        principal_paise=10_000_000,   # ₹1,00,000
        rate_pct=8.0, compounding="QUARTERLY",
        start_date=date(2022, 1, 1), maturity_date=date(2023, 1, 1),  # matured
    )
    contrib = _make_txn("CONTRIBUTION", -10_000_000, date(2022, 1, 1))
    uow = _make_uow(fd_detail=fd, transactions=[contrib])
    gain = strategy.get_inactive_realized_gain(asset, uow)
    # Matured FD: current_value = maturity_amount (formula clamps to maturity_date)
    assert gain is not None
    assert gain > 0   # earned interest is positive


def test_rd_get_inactive_realized_gain_returns_earned_interest():
    """Matured RD: realized gain = rd_maturity_amount - total_contributions."""
    from app.services.returns.strategies.asset_types.rd import RDStrategy
    strategy = RDStrategy()
    asset = _make_asset(asset_type="RD", is_active=False)
    fd = _make_fd_detail(
        principal_paise=500_000,   # ₹5,000/month
        rate_pct=7.0, compounding="QUARTERLY",
        start_date=date(2023, 1, 1), maturity_date=date(2024, 1, 1),
    )
    contribs = [_make_txn("CONTRIBUTION", -500_000, date(2023, i, 1)) for i in range(1, 13)]
    uow = _make_uow(fd_detail=fd, transactions=contribs)
    gain = strategy.get_inactive_realized_gain(asset, uow)
    assert gain is not None
    assert gain > 0


def test_epf_strategy_no_contributions_returns_none_current_value():
    from app.services.returns.strategies.asset_types.epf import EPFStrategy
    strategy = EPFStrategy()
    asset = _make_asset(asset_type="EPF")
    uow = _make_uow(transactions=[])
    result = strategy.get_current_value(asset, uow)
    assert result is None


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

    failing_asset = _make_asset(asset_id=1, asset_type="STOCK_IN")

    class FakeUoW:
        class FakeAssets:
            def list(self, active=None): return [failing_asset]
        assets = FakeAssets()
        transactions = MagicMock()
        transactions.list_by_asset.side_effect = RuntimeError("db error")
        price_cache = MagicMock()
        price_cache.get_by_asset_id.side_effect = RuntimeError("db error")
        def __enter__(self): return self
        def __exit__(self, *a): pass

    service = ReturnsService(
        uow_factory=lambda: FakeUoW(),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )
    results = service.get_all_returns()
    # Any unhandled exception from strategy should be caught and skipped
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

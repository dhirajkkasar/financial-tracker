# backend/tests/unit/test_tax_strategies.py
import pytest
from app.services.tax.strategies.base import (
    AssetTaxGainsResult,
    TaxStrategyRegistry,
    _REGISTRY,
)


def test_asset_tax_gains_result_is_dataclass():
    r = AssetTaxGainsResult(
        asset_id=1, asset_name="Test", asset_type="STOCK_IN", asset_class="EQUITY",
        st_gain=1000.0, lt_gain=500.0,
        st_tax_estimate=200.0, lt_tax_estimate=62.5,
        ltcg_exemption_used=0.0, has_slab=False,
        ltcg_exempt_eligible=True, ltcg_slab=False,
    )
    assert r.asset_id == 1
    assert r.st_gain == 1000.0
    assert r.ltcg_exempt_eligible is True


def test_registry_returns_none_for_unknown():
    registry = TaxStrategyRegistry()
    assert registry.get("UNKNOWN_TYPE", "EQUITY") is None


from unittest.mock import MagicMock
from datetime import date as d


def _make_asset(asset_type="STOCK_IN", asset_class="EQUITY", asset_id=1, name="Test Asset"):
    asset = MagicMock()
    asset.id = asset_id
    asset.name = name
    asset.asset_type.value = asset_type
    asset.asset_class.value = asset_class
    return asset


def _make_txn(type_val, date_val, units, amount_inr, lot_id=None, txn_id=1):
    txn = MagicMock()
    txn.type.value = type_val
    txn.date = date_val
    txn.units = units
    txn.amount_inr = amount_inr
    txn.lot_id = lot_id
    txn.id = txn_id
    return txn


def _make_uow(transactions=None, fd_detail=None):
    uow = MagicMock()
    uow.transactions.list_by_asset.return_value = transactions or []
    uow.fd.get_by_asset_id.return_value = fd_detail
    return uow


def test_fifo_strategy_no_sells_returns_zero():
    from app.services.tax.strategies.indian_equity import StockINTaxGainsStrategy
    strategy = StockINTaxGainsStrategy()
    asset = _make_asset()
    txns = [_make_txn("BUY", d(2023, 1, 1), 10, -1000000)]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == 0.0
    assert result.lt_gain == 0.0
    assert result.st_tax_estimate == 0.0


def test_fifo_strategy_st_gain_stock_in():
    from app.services.tax.strategies.indian_equity import StockINTaxGainsStrategy
    strategy = StockINTaxGainsStrategy()
    asset = _make_asset()
    # BUY Jun 2024, SELL Sep 2024 → 92 days < 365 → ST at 20%
    txns = [
        _make_txn("BUY",  d(2024, 6, 1), 10, -1000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 9, 1), 10,  1200000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == pytest.approx(2000.0)
    assert result.lt_gain == pytest.approx(0.0)
    assert result.st_tax_estimate == pytest.approx(400.0)   # 2000 × 20%
    assert result.has_slab is False
    assert result.ltcg_exempt_eligible is True


def test_fifo_strategy_lt_gain_stock_in():
    from app.services.tax.strategies.indian_equity import StockINTaxGainsStrategy
    strategy = StockINTaxGainsStrategy()
    asset = _make_asset()
    # BUY Jan 2023, SELL Jun 2024 → 517 days ≥ 365 → LT at 12.5%
    txns = [
        _make_txn("BUY",  d(2023, 1, 1), 10, -1000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 6, 1), 10,  1500000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.lt_gain == pytest.approx(5000.0)
    assert result.st_gain == pytest.approx(0.0)
    assert result.lt_tax_estimate == pytest.approx(625.0)   # 5000 × 12.5%


def test_fifo_strategy_sell_outside_fy_excluded():
    from app.services.tax.strategies.indian_equity import StockINTaxGainsStrategy
    strategy = StockINTaxGainsStrategy()
    asset = _make_asset()
    # SELL in FY 2023-24 — must NOT appear in FY 2024-25
    txns = [
        _make_txn("BUY",  d(2022, 1, 1), 10, -1000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 3, 1), 10,  1500000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == 0.0
    assert result.lt_gain == 0.0


def test_registry_wildcard_fallback():
    # After strategies are registered (Task 3+), wildcard lookup works.
    # This test imports a concrete strategy to trigger registration.
    from app.services.tax.strategies.indian_equity import StockINTaxGainsStrategy  # noqa
    registry = TaxStrategyRegistry()
    strategy = registry.get("STOCK_IN", "EQUITY")
    assert strategy is not None

    # Wildcard: STOCK_IN with any asset_class
    strategy_any = registry.get("STOCK_IN", "DEBT")
    assert strategy_any is not None  # falls back to ("STOCK_IN", "*")


def test_foreign_equity_st_is_slab():
    """STOCK_US ST gain → slab rate (not 20%)."""
    from app.services.tax.strategies.foreign_equity import ForeignEquityTaxGainsStrategy
    strategy = ForeignEquityTaxGainsStrategy()
    asset = _make_asset(asset_type="STOCK_US", asset_class="EQUITY")
    # BUY Jun 2024, SELL Sep 2024 → 92 days < 730 → ST
    txns = [
        _make_txn("BUY",  d(2024, 6, 1), 5, -50000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 9, 1), 5,  60000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == pytest.approx(100.0)
    assert result.st_tax_estimate == pytest.approx(30.0)   # 100 × 30% slab
    assert result.has_slab is True
    assert result.ltcg_exempt_eligible is False


def test_gold_st_threshold_is_1095_days():
    """GOLD held 1000 days → still ST (< 1095)."""
    from app.services.tax.strategies.gold import GoldTaxGainsStrategy
    strategy = GoldTaxGainsStrategy()
    asset = _make_asset(asset_type="GOLD", asset_class="GOLD")
    # BUY Jan 2021, SELL Oct 2023 → 1003 days < 1095 → ST
    txns = [
        _make_txn("BUY",  d(2021, 1, 1), 10, -5000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2023, 10, 1), 10, 6000000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2023, 4, 1), d(2024, 3, 31), 30.0)
    assert result.st_gain == pytest.approx(10000.0)
    assert result.lt_gain == pytest.approx(0.0)
    assert result.has_slab is True


def test_debt_mf_lt_is_also_slab():
    """Debt MF: both ST and LT at slab rate (post-2023 budget)."""
    from app.services.tax.strategies.debt_mf import DebtMFTaxGainsStrategy
    strategy = DebtMFTaxGainsStrategy()
    asset = _make_asset(asset_type="MF", asset_class="DEBT")
    # BUY Jan 2022, SELL Jun 2024 → LT but still slab
    txns = [
        _make_txn("BUY",  d(2022, 1, 1), 100, -1000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 6, 1), 100,  1200000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.lt_gain == pytest.approx(2000.0)
    assert result.lt_tax_estimate == pytest.approx(600.0)   # 2000 × 30% slab
    assert result.ltcg_slab is True
    assert result.ltcg_exempt_eligible is False


def _make_fd_detail(fd_type="FD", principal_paise=100000_00,  # 1L INR in paise
                    rate_pct=7.0, compounding="QUARTERLY",
                    start_date=None, maturity_date=None):
    fd = MagicMock()
    fd.fd_type.value = fd_type
    fd.principal_amount = principal_paise
    fd.interest_rate_pct = rate_pct
    fd.compounding.value = compounding
    fd.start_date = start_date or d(2023, 10, 1)
    fd.maturity_date = maturity_date or d(2025, 9, 30)
    return fd


def test_accrued_interest_fd_partial_fy():
    """FD started Oct 2023: interest from Oct 2023 → Mar 2025 in FY 2024-25 window."""
    from app.services.tax.strategies.accrued_interest import AccruedInterestTaxGainsStrategy
    strategy = AccruedInterestTaxGainsStrategy()
    asset = _make_asset(asset_type="FD", asset_class="DEBT")
    fd = _make_fd_detail(
        start_date=d(2023, 10, 1),
        maturity_date=d(2025, 9, 30),
        principal_paise=100_000 * 100,  # 1L INR
        rate_pct=7.0, compounding="QUARTERLY",
    )
    uow = _make_uow(fd_detail=fd)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    # Interest for Apr 2024 – Mar 2025 on a 1L FD at 7% quarterly
    assert result.st_gain > 0
    assert result.lt_gain == 0.0
    assert result.has_slab is True
    assert result.st_tax_estimate == pytest.approx(result.st_gain * 0.30, rel=1e-3)


def test_accrued_interest_fd_before_fy_zero():
    """FD matured before FY starts → zero interest in this FY."""
    from app.services.tax.strategies.accrued_interest import AccruedInterestTaxGainsStrategy
    strategy = AccruedInterestTaxGainsStrategy()
    asset = _make_asset(asset_type="FD", asset_class="DEBT")
    fd = _make_fd_detail(
        start_date=d(2022, 1, 1),
        maturity_date=d(2023, 12, 31),   # matured before FY 2024-25
    )
    uow = _make_uow(fd_detail=fd)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == 0.0


def test_accrued_interest_no_fd_detail_returns_zero():
    """FD with no fd_detail record → return zero gains."""
    from app.services.tax.strategies.accrued_interest import AccruedInterestTaxGainsStrategy
    strategy = AccruedInterestTaxGainsStrategy()
    asset = _make_asset(asset_type="FD", asset_class="DEBT")
    uow = _make_uow(fd_detail=None)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == 0.0
    assert result.st_tax_estimate == 0.0

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


@pytest.mark.skip(reason="requires indian_equity — implemented in Task 3")
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

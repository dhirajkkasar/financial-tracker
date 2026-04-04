# Realised Gain Breakdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible per-asset breakdown to the Tax Summary Realised Gains section, grouping by `asset_class` (from DB) with a proper tax gains strategy hierarchy and slab rate estimation.

**Architecture:** New `services/tax/strategies/` module with a `TaxGainsStrategy` ABC and concrete implementations per asset type. `TaxService` is restructured to use `IUnitOfWorkFactory` and a `TaxStrategyRegistry`. Frontend gains collapsible category rows with per-asset sub-rows linked to the asset page.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pytest (backend); Next.js App Router, TypeScript, Tailwind (frontend). Run backend tests with `uv run pytest`. No new dependencies.

---

## File Map

### New files
| File | Responsibility |
|---|---|
| `backend/app/services/tax/__init__.py` | Package marker |
| `backend/app/services/tax/strategies/__init__.py` | Auto-imports all strategy modules to trigger registration |
| `backend/app/services/tax/strategies/base.py` | `AssetTaxGainsResult` dataclass, `TaxGainsStrategy` ABC, `_REGISTRY`, `register_tax_strategy`, `TaxStrategyRegistry` |
| `backend/app/services/tax/strategies/fifo_base.py` | `FifoTaxGainsStrategy` — FIFO lot matching, ST/LT classification, tax computation |
| `backend/app/services/tax/strategies/indian_equity.py` | `IndianEquityTaxGainsStrategy` + 3-line leaf classes `StockINTaxGainsStrategy`, `EquityMFTaxGainsStrategy` |
| `backend/app/services/tax/strategies/foreign_equity.py` | `ForeignEquityTaxGainsStrategy` |
| `backend/app/services/tax/strategies/gold.py` | `GoldTaxGainsStrategy` |
| `backend/app/services/tax/strategies/debt_mf.py` | `DebtMFTaxGainsStrategy` |
| `backend/app/services/tax/strategies/accrued_interest.py` | `AccruedInterestTaxGainsStrategy` (FD/RD) |
| `backend/app/services/tax/strategies/real_estate.py` | `RealEstateTaxGainsStrategy` |
| `backend/app/engine/lot_helper.py` | `LotHelper` (Task 13 only — last step) |
| `backend/tests/unit/test_tax_strategies.py` | Unit tests for strategy hierarchy |

### Modified files
| File | Change |
|---|---|
| `backend/app/services/tax_service.py` | Full restructure: UoW factory, strategy dispatch, new response shape |
| `backend/app/api/dependencies.py` | Update `get_tax_service` to inject `uow_factory` + `slab_rate_pct` |
| `backend/.env` | Add `SLAB_RATE=30` |
| `backend/tests/integration/test_tax_api.py` | Update assertions for new response shape |
| `frontend/types/index.ts` | New `AssetGainBreakdown`, `AssetClass` type; updated `TaxSummaryEntry` |
| `frontend/app/tax/page.tsx` | Collapsible rows, slab label, drop `TAX_CLASS_MAP` |
| `backend/app/services/returns/strategies/market_based.py` | Delegate to `LotHelper` (Task 13 only) |
| `backend/app/services/tax/strategies/fifo_base.py` | Use `LotHelper` (Task 13 only) |

---

## Task 1: Strategy ABC + Registry

**Files:**
- Create: `backend/app/services/tax/__init__.py`
- Create: `backend/app/services/tax/strategies/__init__.py` (empty for now, filled in Task 7)
- Create: `backend/app/services/tax/strategies/base.py`
- Test: `backend/tests/unit/test_tax_strategies.py`

- [x] **Step 1: Write the failing test**

```python
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
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `app.services.tax.strategies.base` doesn't exist yet.

- [x] **Step 3: Create package markers**

```python
# backend/app/services/tax/__init__.py
# (empty)
```

```python
# backend/app/services/tax/strategies/__init__.py
# (empty for now — filled in Task 7)
```

- [x] **Step 4: Write `base.py`**

```python
# backend/app/services/tax/strategies/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.repositories.unit_of_work import UnitOfWork


@dataclass
class AssetTaxGainsResult:
    asset_id: int
    asset_name: str
    asset_type: str
    asset_class: str
    st_gain: float
    lt_gain: float
    st_tax_estimate: float        # always numeric — slab items use injected slab_rate_pct
    lt_tax_estimate: float        # always numeric, pre-exemption for ltcg_exempt_eligible
    ltcg_exemption_used: float    # always 0.0 here — exemption applied at entry level
    has_slab: bool                # True if slab_rate_pct was used for any gain
    ltcg_exempt_eligible: bool    # True for STOCK_IN and equity MF (Section 112A)
    ltcg_slab: bool               # True if LTCG is at slab rate (Debt MF, FD/RD)


class TaxGainsStrategy(ABC):
    @abstractmethod
    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        ...


# Module-level registry: (asset_type, asset_class) → strategy instance
# "*" as asset_class means "any asset class"
_REGISTRY: dict[tuple[str, str], TaxGainsStrategy] = {}


def register_tax_strategy(*keys: tuple[str, str]):
    """
    Class decorator to register a strategy for one or more (asset_type, asset_class) keys.

    Usage:
        @register_tax_strategy(("STOCK_IN", "*"))
        class StockINTaxGainsStrategy(IndianEquityTaxGainsStrategy):
            pass

        @register_tax_strategy(("FD", "*"), ("RD", "*"))
        class AccruedInterestTaxGainsStrategy(TaxGainsStrategy):
            ...
    """
    def decorator(cls):
        instance = cls()
        for key in keys:
            _REGISTRY[key] = instance
        return cls
    return decorator


class TaxStrategyRegistry:
    """Look up a TaxGainsStrategy by (asset_type, asset_class).

    Lookup order:
      1. Exact match: (asset_type, asset_class)
      2. Wildcard:    (asset_type, "*")
      3. None if neither found
    """

    def get(self, asset_type: str, asset_class: str) -> Optional[TaxGainsStrategy]:
        return _REGISTRY.get((asset_type, asset_class)) or _REGISTRY.get((asset_type, "*"))
```

- [x] **Step 5: Run test (partial pass — `test_registry_wildcard_fallback` will fail until Task 3)**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py::test_asset_tax_gains_result_is_dataclass tests/unit/test_tax_strategies.py::test_registry_returns_none_for_unknown -v
```

Expected: both PASS.

- [x] **Step 6: Commit**

```bash
cd backend && git add app/services/tax/ tests/unit/test_tax_strategies.py
git commit -m "feat: add TaxGainsStrategy ABC, AssetTaxGainsResult, TaxStrategyRegistry"
```

---

## Task 2: `FifoTaxGainsStrategy` Base

**Files:**
- Create: `backend/app/services/tax/strategies/fifo_base.py`
- Test: `backend/tests/unit/test_tax_strategies.py` (add test)

- [x] **Step 1: Add failing test**

Append to `backend/tests/unit/test_tax_strategies.py`:

```python
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
    txns = [_make_txn("BUY", d(2023, 1, 1), 10, -10000)]
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
        _make_txn("BUY",  d(2024, 6, 1), 10, -10000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 9, 1), 10,  12000, txn_id=2),
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
        _make_txn("BUY",  d(2023, 1, 1), 10, -10000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 6, 1), 10,  15000, txn_id=2),
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
        _make_txn("BUY",  d(2022, 1, 1), 10, -10000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 3, 1), 10,  15000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == 0.0
    assert result.lt_gain == 0.0
```

- [x] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -k "fifo" -v
```

Expected: `ImportError` — `fifo_base` and `indian_equity` don't exist yet.

- [x] **Step 3: Write `fifo_base.py`**

```python
# backend/app/services/tax/strategies/fifo_base.py
from __future__ import annotations

from datetime import date
from typing import ClassVar, Optional

from app.engine.lot_engine import match_lots_fifo
from app.repositories.unit_of_work import UnitOfWork
from app.services.returns.strategies.market_based import LOT_TYPES, SELL_TYPES, _Lot, _Sell
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxGainsStrategy


class FifoTaxGainsStrategy(TaxGainsStrategy):
    """
    Base for all FIFO lot-matched assets.

    Subclasses declare ClassVars:
        stcg_days: int             — holding threshold in days
        stcg_rate_pct: float|None  — None means slab rate
        ltcg_rate_pct: float|None  — None means slab rate
        ltcg_exempt_eligible: bool — True for STOCK_IN and equity MF (Section 112A)
        ltcg_slab: bool            — True if LTCG is slab-rated (Debt MF)
    """

    stcg_days: ClassVar[int]
    stcg_rate_pct: ClassVar[Optional[float]] = None
    ltcg_rate_pct: ClassVar[Optional[float]] = None
    ltcg_exempt_eligible: ClassVar[bool] = False
    ltcg_slab: ClassVar[bool] = False

    # ── Lot building (duplicated from MarketBasedStrategy — refactored in Task 13) ──

    def _build_lots_sells(self, txns) -> tuple[list[_Lot], list[_Sell]]:
        lots: list[_Lot] = []
        sells: list[_Sell] = []
        for t in sorted(txns, key=lambda x: x.date):
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            if ttype in LOT_TYPES and t.units:
                is_bonus = ttype == "BONUS"
                price_pu = 0.0 if is_bonus else (
                    abs(t.amount_inr / 100.0) / t.units if t.units else 0.0
                )
                lots.append(_Lot(
                    lot_id=t.lot_id or str(t.id),
                    buy_date=t.date,
                    units=t.units,
                    buy_price_per_unit=price_pu,
                    buy_amount_inr=0.0 if is_bonus else abs(t.amount_inr / 100.0),
                ))
            elif ttype in SELL_TYPES and t.units:
                sells.append(_Sell(
                    date=t.date,
                    units=t.units,
                    amount_inr=abs(t.amount_inr / 100.0),
                ))
        return lots, sells

    # ── FY gain extraction ──────────────────────────────────────────────────────

    def _fy_gains(
        self, matched: list[dict], fy_start: date, fy_end: date
    ) -> tuple[float, float]:
        """Filter matches by sell date in FY, return (st_gain, lt_gain)."""
        st, lt = 0.0, 0.0
        for m in matched:
            sell_date = m["sell_date"]
            if isinstance(sell_date, str):
                sell_date = date.fromisoformat(sell_date)
            if not (fy_start <= sell_date <= fy_end):
                continue
            gain = m["realised_gain_inr"]
            # is_short_term already set by match_lots_fifo using self.stcg_days
            if m["is_short_term"]:
                st += gain
            else:
                lt += gain
        return st, lt

    # ── Tax estimation ──────────────────────────────────────────────────────────

    def _tax(self, gain: float, rate_pct: Optional[float], slab_rate_pct: float) -> float:
        if gain <= 0:
            return 0.0
        rate = rate_pct if rate_pct is not None else slab_rate_pct
        return gain * rate / 100.0

    # ── Public entry point ──────────────────────────────────────────────────────

    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        txns = uow.transactions.list_by_asset(asset.id)
        lots, sells = self._build_lots_sells(txns)

        st_gain, lt_gain = 0.0, 0.0
        if lots and sells:
            matched = match_lots_fifo(lots, sells, stcg_days=self.stcg_days)
            st_gain, lt_gain = self._fy_gains(matched, fy_start, fy_end)

        has_slab = (self.stcg_rate_pct is None and st_gain != 0) or (
            self.ltcg_rate_pct is None and lt_gain != 0
        )

        return AssetTaxGainsResult(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            asset_class=asset.asset_class.value,
            st_gain=st_gain,
            lt_gain=lt_gain,
            st_tax_estimate=self._tax(st_gain, self.stcg_rate_pct, slab_rate_pct),
            lt_tax_estimate=self._tax(lt_gain, self.ltcg_rate_pct, slab_rate_pct),
            ltcg_exemption_used=0.0,
            has_slab=has_slab,
            ltcg_exempt_eligible=self.ltcg_exempt_eligible,
            ltcg_slab=self.ltcg_slab,
        )
```

- [x] **Step 4: Run tests (still fail — `indian_equity` doesn't exist yet)**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -k "fifo" -v
```

Expected: `ImportError` on `indian_equity`. That's fine — proceed to Task 3.

- [x] **Step 5: Commit `fifo_base.py`**

```bash
cd backend && git add app/services/tax/strategies/fifo_base.py
git commit -m "feat: add FifoTaxGainsStrategy base with FIFO lot matching"
```

---

## Task 3: `IndianEquityTaxGainsStrategy` + Leaf Classes

**Files:**
- Create: `backend/app/services/tax/strategies/indian_equity.py`

- [x] **Step 1: Write `indian_equity.py`**

```python
# backend/app/services/tax/strategies/indian_equity.py
from typing import ClassVar, Optional

from app.services.tax.strategies.base import register_tax_strategy
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy


class IndianEquityTaxGainsStrategy(FifoTaxGainsStrategy):
    """
    STOCK_IN and equity MF: STCG 20%, LTCG 12.5%, ₹1.25L Section-112A exemption.
    Holding threshold: 365 days.
    """
    stcg_days: ClassVar[int] = 365
    stcg_rate_pct: ClassVar[Optional[float]] = 20.0
    ltcg_rate_pct: ClassVar[Optional[float]] = 12.5
    ltcg_exempt_eligible: ClassVar[bool] = True
    ltcg_slab: ClassVar[bool] = False


@register_tax_strategy(("STOCK_IN", "*"))
class StockINTaxGainsStrategy(IndianEquityTaxGainsStrategy):
    pass


@register_tax_strategy(("MF", "EQUITY"))
class EquityMFTaxGainsStrategy(IndianEquityTaxGainsStrategy):
    pass
```

- [x] **Step 2: Run the FIFO tests (should now pass)**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -v
```

Expected: All tests PASS (the `test_registry_wildcard_fallback` test should also pass now).

- [x] **Step 3: Commit**

```bash
cd backend && git add app/services/tax/strategies/indian_equity.py
git commit -m "feat: add IndianEquityTaxGainsStrategy with StockIN and EquityMF leaf classes"
```

---

## Task 4: Foreign Equity, Gold, and Debt MF Strategies

**Files:**
- Create: `backend/app/services/tax/strategies/foreign_equity.py`
- Create: `backend/app/services/tax/strategies/gold.py`
- Create: `backend/app/services/tax/strategies/debt_mf.py`
- Test: `backend/tests/unit/test_tax_strategies.py` (add tests)

- [x] **Step 1: Add failing tests**

Append to `backend/tests/unit/test_tax_strategies.py`:

```python
def test_foreign_equity_st_is_slab():
    """STOCK_US ST gain → slab rate (not 20%)."""
    from app.services.tax.strategies.foreign_equity import ForeignEquityTaxGainsStrategy
    strategy = ForeignEquityTaxGainsStrategy()
    asset = _make_asset(asset_type="STOCK_US", asset_class="EQUITY")
    # BUY Jun 2024, SELL Sep 2024 → 92 days < 730 → ST
    txns = [
        _make_txn("BUY",  d(2024, 6, 1), 5, -500, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 9, 1), 5,  600, txn_id=2),
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
        _make_txn("BUY",  d(2021, 1, 1), 10, -50000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2023, 10, 1), 10, 60000, txn_id=2),
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
        _make_txn("BUY",  d(2022, 1, 1), 100, -10000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 6, 1), 100,  12000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.lt_gain == pytest.approx(2000.0)
    assert result.lt_tax_estimate == pytest.approx(600.0)   # 2000 × 30% slab
    assert result.ltcg_slab is True
    assert result.ltcg_exempt_eligible is False
```

- [x] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -k "foreign or gold or debt_mf" -v
```

Expected: `ImportError` on missing modules.

- [x] **Step 3: Write the three strategy files**

```python
# backend/app/services/tax/strategies/foreign_equity.py
from typing import ClassVar, Optional
from app.services.tax.strategies.base import register_tax_strategy
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy


@register_tax_strategy(("STOCK_US", "*"))
class ForeignEquityTaxGainsStrategy(FifoTaxGainsStrategy):
    """Foreign stocks: STCG at slab, LTCG 12.5%, 730-day threshold."""
    stcg_days: ClassVar[int] = 730
    stcg_rate_pct: ClassVar[Optional[float]] = None    # slab
    ltcg_rate_pct: ClassVar[Optional[float]] = 12.5
    ltcg_exempt_eligible: ClassVar[bool] = False
    ltcg_slab: ClassVar[bool] = False
```

```python
# backend/app/services/tax/strategies/gold.py
from typing import ClassVar, Optional
from app.services.tax.strategies.base import register_tax_strategy
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy


@register_tax_strategy(("GOLD", "*"))
class GoldTaxGainsStrategy(FifoTaxGainsStrategy):
    """Gold/Gold ETF: STCG at slab, LTCG 12.5%, 1095-day threshold."""
    stcg_days: ClassVar[int] = 1095
    stcg_rate_pct: ClassVar[Optional[float]] = None    # slab
    ltcg_rate_pct: ClassVar[Optional[float]] = 12.5
    ltcg_exempt_eligible: ClassVar[bool] = False
    ltcg_slab: ClassVar[bool] = False
```

```python
# backend/app/services/tax/strategies/debt_mf.py
from typing import ClassVar, Optional
from app.services.tax.strategies.base import register_tax_strategy
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy


@register_tax_strategy(("MF", "DEBT"))
class DebtMFTaxGainsStrategy(FifoTaxGainsStrategy):
    """Debt MF: all gains at slab rate (post-2023 budget change), 365-day threshold."""
    stcg_days: ClassVar[int] = 365
    stcg_rate_pct: ClassVar[Optional[float]] = None    # slab
    ltcg_rate_pct: ClassVar[Optional[float]] = None    # slab
    ltcg_exempt_eligible: ClassVar[bool] = False
    ltcg_slab: ClassVar[bool] = True
```

- [x] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -v
```

Expected: All tests PASS.

- [x] **Step 5: Commit**

```bash
cd backend && git add app/services/tax/strategies/foreign_equity.py app/services/tax/strategies/gold.py app/services/tax/strategies/debt_mf.py
git commit -m "feat: add ForeignEquity, Gold, DebtMF tax gain strategies"
```

---

## Task 5: `AccruedInterestTaxGainsStrategy` (FD/RD)

**Files:**
- Create: `backend/app/services/tax/strategies/accrued_interest.py`
- Test: `backend/tests/unit/test_tax_strategies.py` (add tests)

- [x] **Step 1: Add failing tests**

Append to `backend/tests/unit/test_tax_strategies.py`:

```python
def _make_fd_detail(fd_type="FD", principal_paise=100000_00,  # 1L INR in paise
                    rate_pct=7.0, compounding="QUARTERLY",
                    start_date=None, maturity_date=None):
    from datetime import date
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
```

- [x] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -k "accrued" -v
```

Expected: `ImportError`.

- [x] **Step 3: Write `accrued_interest.py`**

```python
# backend/app/services/tax/strategies/accrued_interest.py
from __future__ import annotations

from datetime import date, timedelta

from app.engine.fd_engine import compute_fd_current_value, compute_rd_maturity
from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import (
    AssetTaxGainsResult,
    TaxGainsStrategy,
    register_tax_strategy,
)


def _fd_value_at(fd, as_of: date) -> float:
    """Current value of an FD (in INR) at a given date using compound interest."""
    principal_inr = fd.principal_amount / 100.0
    return compute_fd_current_value(
        principal_inr,
        fd.interest_rate_pct,
        fd.compounding.value,
        fd.start_date,
        fd.maturity_date,
        as_of=as_of,
    )


def _rd_interest_in_window(fd, window_start: date, window_end: date) -> float:
    """
    RD interest accrued in [window_start, window_end] using linear proration
    of total interest across the RD tenure.
    """
    total_months = round((fd.maturity_date - fd.start_date).days / 30.44)
    if total_months == 0:
        return 0.0
    monthly_inr = fd.principal_amount / 100.0
    maturity_inr = compute_rd_maturity(monthly_inr, fd.interest_rate_pct, total_months)
    total_principal = monthly_inr * total_months
    total_interest = max(0.0, maturity_inr - total_principal)
    total_days = (fd.maturity_date - fd.start_date).days
    if total_days == 0:
        return 0.0
    window_days = (window_end - window_start).days
    return total_interest * (window_days / total_days)


def _zero_result(asset) -> AssetTaxGainsResult:
    return AssetTaxGainsResult(
        asset_id=asset.id,
        asset_name=asset.name,
        asset_type=asset.asset_type.value,
        asset_class=asset.asset_class.value,
        st_gain=0.0, lt_gain=0.0,
        st_tax_estimate=0.0, lt_tax_estimate=0.0,
        ltcg_exemption_used=0.0,
        has_slab=False,
        ltcg_exempt_eligible=False,
        ltcg_slab=True,
    )


@register_tax_strategy(("FD", "*"), ("RD", "*"))
class AccruedInterestTaxGainsStrategy(TaxGainsStrategy):
    """
    FD/RD: interest accrued in the FY is taxed at slab rate.

    FD: exact compound interest using compute_fd_current_value.
    RD: linear proration of total interest across tenure (approximation).
    """

    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        fd = uow.fd.get_by_asset_id(asset.id)
        if fd is None:
            return _zero_result(asset)

        # No overlap between FD tenure and FY
        if fd.start_date > fy_end or fd.maturity_date < fy_start:
            return _zero_result(asset)

        effective_end = min(fy_end, fd.maturity_date)
        # Value at end of previous FY (or FD start if it began this FY)
        prior_date = max(fd.start_date, fy_start - timedelta(days=1))

        if prior_date >= effective_end:
            return _zero_result(asset)

        fd_type = fd.fd_type.value
        if fd_type == "FD":
            value_end = _fd_value_at(fd, effective_end)
            value_prior = _fd_value_at(fd, prior_date)
            interest = max(0.0, value_end - value_prior)
        else:  # RD
            window_start = max(fd.start_date, fy_start)
            window_end = min(fy_end, fd.maturity_date)
            interest = _rd_interest_in_window(fd, window_start, window_end)

        st_tax = interest * slab_rate_pct / 100.0

        return AssetTaxGainsResult(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            asset_class=asset.asset_class.value,
            st_gain=interest,
            lt_gain=0.0,
            st_tax_estimate=st_tax,
            lt_tax_estimate=0.0,
            ltcg_exemption_used=0.0,
            has_slab=True,
            ltcg_exempt_eligible=False,
            ltcg_slab=True,
        )
```

- [x] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -v
```

Expected: All tests PASS.

- [x] **Step 5: Commit**

```bash
cd backend && git add app/services/tax/strategies/accrued_interest.py
git commit -m "feat: add AccruedInterestTaxGainsStrategy for FD/RD interest income"
```

---

## Task 6: `RealEstateTaxGainsStrategy`

**Files:**
- Create: `backend/app/services/tax/strategies/real_estate.py`
- Test: `backend/tests/unit/test_tax_strategies.py` (add tests)

- [x] **Step 1: Add failing tests**

Append to `backend/tests/unit/test_tax_strategies.py`:

```python
def test_real_estate_no_sell_in_fy_zero():
    from app.services.tax.strategies.real_estate import RealEstateTaxGainsStrategy
    strategy = RealEstateTaxGainsStrategy()
    asset = _make_asset(asset_type="REAL_ESTATE", asset_class="REAL_ESTATE")
    txns = [_make_txn("CONTRIBUTION", d(2020, 1, 1), None, -5_000_000, txn_id=1)]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == 0.0
    assert result.lt_gain == 0.0


def test_real_estate_lt_gain_over_2_years():
    """Property bought Jan 2020, sold Jun 2024 → 1612 days ≥ 730 → LT at 12.5%."""
    from app.services.tax.strategies.real_estate import RealEstateTaxGainsStrategy
    strategy = RealEstateTaxGainsStrategy()
    asset = _make_asset(asset_type="REAL_ESTATE", asset_class="REAL_ESTATE")
    txns = [
        _make_txn("CONTRIBUTION", d(2020, 1, 1), None, -5_000_000, txn_id=1),
        _make_txn("SELL",         d(2024, 6, 1), None,  7_000_000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.lt_gain == pytest.approx(2_000_000.0)
    assert result.st_gain == pytest.approx(0.0)
    assert result.lt_tax_estimate == pytest.approx(250_000.0)   # 2M × 12.5%
    assert result.has_slab is False


def test_real_estate_st_gain_under_2_years():
    """Property bought Jun 2023, sold Sep 2024 → 457 days < 730 → ST at slab."""
    from app.services.tax.strategies.real_estate import RealEstateTaxGainsStrategy
    strategy = RealEstateTaxGainsStrategy()
    asset = _make_asset(asset_type="REAL_ESTATE", asset_class="REAL_ESTATE")
    txns = [
        _make_txn("CONTRIBUTION", d(2023, 6, 1), None, -3_000_000, txn_id=1),
        _make_txn("SELL",         d(2024, 9, 1), None,  3_500_000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == pytest.approx(500_000.0)
    assert result.lt_gain == pytest.approx(0.0)
    assert result.st_tax_estimate == pytest.approx(150_000.0)   # 500K × 30% slab
    assert result.has_slab is True
```

- [x] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -k "real_estate" -v
```

Expected: `ImportError`.

- [x] **Step 3: Write `real_estate.py`**

```python
# backend/app/services/tax/strategies/real_estate.py
from __future__ import annotations

from datetime import date

from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import (
    AssetTaxGainsResult,
    TaxGainsStrategy,
    register_tax_strategy,
)

REAL_ESTATE_STCG_DAYS = 730   # 2 years
LTCG_RATE = 12.5

BUY_TXNS = {"BUY", "CONTRIBUTION"}
SELL_TXNS = {"SELL", "WITHDRAWAL"}


def _zero_result(asset) -> AssetTaxGainsResult:
    return AssetTaxGainsResult(
        asset_id=asset.id, asset_name=asset.name,
        asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
        st_gain=0.0, lt_gain=0.0,
        st_tax_estimate=0.0, lt_tax_estimate=0.0,
        ltcg_exemption_used=0.0, has_slab=False,
        ltcg_exempt_eligible=False, ltcg_slab=False,
    )


@register_tax_strategy(("REAL_ESTATE", "*"))
class RealEstateTaxGainsStrategy(TaxGainsStrategy):
    """
    Real estate: SELL/WITHDRAWAL transactions in FY → gain = proceeds − total invested.
    STCG (< 730 days from earliest purchase) at slab; LTCG (≥ 730 days) at 12.5%.

    Not FIFO — real estate is not unit-tracked. Gain = all proceeds in FY minus
    total cost basis across all purchase transactions for this asset.
    """

    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        txns = uow.transactions.list_by_asset(asset.id)

        buy_txns = [
            t for t in txns
            if (t.type.value if hasattr(t.type, "value") else str(t.type)) in BUY_TXNS
        ]
        sell_txns_in_fy = [
            t for t in txns
            if (t.type.value if hasattr(t.type, "value") else str(t.type)) in SELL_TXNS
            and fy_start <= t.date <= fy_end
        ]

        if not buy_txns or not sell_txns_in_fy:
            return _zero_result(asset)

        total_invested = sum(abs(t.amount_inr / 100.0) for t in buy_txns)
        if total_invested == 0:
            return _zero_result(asset)

        total_proceeds = sum(abs(t.amount_inr / 100.0) for t in sell_txns_in_fy)
        gain = total_proceeds - total_invested

        earliest_buy_date = min(t.date for t in buy_txns)
        latest_sell_date = max(t.date for t in sell_txns_in_fy)
        holding_days = (latest_sell_date - earliest_buy_date).days
        is_short_term = holding_days < REAL_ESTATE_STCG_DAYS

        st_gain = gain if is_short_term else 0.0
        lt_gain = 0.0 if is_short_term else gain

        st_tax = max(0.0, st_gain) * slab_rate_pct / 100.0
        lt_tax = max(0.0, lt_gain) * LTCG_RATE / 100.0
        has_slab = is_short_term and gain > 0

        return AssetTaxGainsResult(
            asset_id=asset.id, asset_name=asset.name,
            asset_type=asset.asset_type.value, asset_class=asset.asset_class.value,
            st_gain=st_gain, lt_gain=lt_gain,
            st_tax_estimate=st_tax, lt_tax_estimate=lt_tax,
            ltcg_exemption_used=0.0, has_slab=has_slab,
            ltcg_exempt_eligible=False, ltcg_slab=False,
        )
```

- [x] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -v
```

Expected: All tests PASS.

- [x] **Step 5: Commit**

```bash
cd backend && git add app/services/tax/strategies/real_estate.py
git commit -m "feat: add RealEstateTaxGainsStrategy with 730-day ST/LT threshold"
```

---

## Task 7: Strategy Registry Auto-Import

**Files:**
- Modify: `backend/app/services/tax/strategies/__init__.py`

The registry works by side-effect of importing strategy modules (the `@register_tax_strategy` decorator runs on import). `TaxStrategyRegistry` needs all modules imported before `.get()` is called. We do this once in `__init__.py`.

- [x] **Step 1: Update `__init__.py`**

```python
# backend/app/services/tax/strategies/__init__.py
# Import all strategy modules to trigger @register_tax_strategy decorators.
# Order does not matter.
from app.services.tax.strategies import (  # noqa: F401
    indian_equity,
    foreign_equity,
    gold,
    debt_mf,
    accrued_interest,
    real_estate,
)
```

- [x] **Step 2: Verify the full test suite still passes**

```bash
cd backend && uv run pytest tests/unit/test_tax_strategies.py -v
```

Expected: All PASS.

- [x] **Step 3: Commit**

```bash
cd backend && git add app/services/tax/strategies/__init__.py
git commit -m "feat: auto-import tax strategy modules to populate registry"
```

---

## Task 8: Restructure `TaxService`

**Files:**
- Modify: `backend/app/services/tax_service.py`

This is the largest change. The service switches from direct-repo to UoW factory, drops the old private helpers, dispatches via `TaxStrategyRegistry`, and emits the new response shape with `asset_class` grouping and `asset_breakdown`.

- [x] **Step 1: Write the new `tax_service.py`**

Replace the entire file:

```python
# backend/app/services/tax_service.py
import logging
from datetime import date

from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS
from app.engine.lot_engine import match_lots_fifo, compute_lot_unrealised
from app.engine.returns import EXCLUDED_TYPES
from app.engine.tax_engine import (
    parse_fy,
    apply_ltcg_exemption,
    find_harvest_opportunities,
)
from app.repositories.unit_of_work import IUnitOfWorkFactory
from app.services.returns.strategies.market_based import LOT_TYPES, SELL_TYPES, _Lot, _Sell
from app.services.tax.strategies import  # noqa: F401 — triggers registration
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxStrategyRegistry

logger = logging.getLogger(__name__)

SKIPPED_ASSET_TYPES = {"EPF", "PPF", "NPS", "SGB", "RSU"}
LOT_ASSET_TYPES = {"STOCK_IN", "STOCK_US", "MF", "GOLD"}   # FIFO-tracked for unrealised
ASSET_CLASS_ORDER = ["EQUITY", "DEBT", "GOLD", "REAL_ESTATE"]

LTCG_NEAR_THRESHOLD = 125_000.0
LTCG_NEAR_PCT = 0.10


class TaxService:
    def __init__(self, uow_factory: IUnitOfWorkFactory, slab_rate_pct: float = 30.0):
        self._uow_factory = uow_factory
        self._slab_rate_pct = slab_rate_pct
        self._registry = TaxStrategyRegistry()

    # ── Realised gains ────────────────────────────────────────────────────────

    def _compute_entry_lt_tax(
        self, results: list[AssetTaxGainsResult]
    ) -> tuple[float, float]:
        """
        Compute (total_lt_tax, ltcg_exemption_used) for an asset_class entry.

        ₹1.25L Section-112A exemption is applied once against the combined
        exempt-eligible (STOCK_IN + equity MF) LTCG — not per-asset.
        All other LTCG at 12.5% flat; slab-rate LTCG at configured slab rate.
        """
        exempt_eligible_lt = sum(
            max(0.0, r.lt_gain) for r in results if r.ltcg_exempt_eligible
        )
        exemption_result = apply_ltcg_exemption(exempt_eligible_lt, "STOCK_IN")
        exemption_used = exemption_result["exemption_used"]
        taxable_exempt_lt = exemption_result["taxable_lt_gain"]

        lt_tax = taxable_exempt_lt * 12.5 / 100.0   # Indian equity after exemption

        for r in results:
            if r.ltcg_exempt_eligible:
                continue   # already handled above
            if r.ltcg_slab:
                lt_tax += max(0.0, r.lt_gain) * self._slab_rate_pct / 100.0
            else:
                lt_tax += max(0.0, r.lt_gain) * 12.5 / 100.0   # Gold, ForeignEquity, RealEstate

        return lt_tax, exemption_used

    def get_tax_summary(self, fy_label: str) -> dict:
        fy_start, fy_end = parse_fy(fy_label)
        buckets: dict[str, list[AssetTaxGainsResult]] = {}

        with self._uow_factory() as uow:
            for asset in uow.assets.list(active=None):
                atype = asset.asset_type.value
                if atype in SKIPPED_ASSET_TYPES:
                    continue
                strategy = self._registry.get(atype, asset.asset_class.value)
                if strategy is None:
                    continue
                try:
                    result = strategy.compute(asset, uow, fy_start, fy_end, self._slab_rate_pct)
                except Exception as e:
                    logger.warning("Tax gains error for asset %d: %s", asset.id, str(e))
                    continue
                if result.st_gain == 0.0 and result.lt_gain == 0.0:
                    continue
                buckets.setdefault(asset.asset_class.value, []).append(result)

        entries = []
        total_st_gain = 0.0
        total_lt_gain = 0.0
        total_st_tax = 0.0
        total_lt_tax = 0.0
        has_slab = False

        for asset_class_val in ASSET_CLASS_ORDER:
            results = buckets.get(asset_class_val)
            if not results:
                continue

            st_gain = sum(r.st_gain for r in results)
            lt_gain = sum(r.lt_gain for r in results)
            st_tax = sum(r.st_tax_estimate for r in results)
            lt_tax, exemption_used = self._compute_entry_lt_tax(results)
            entry_has_slab = any(r.has_slab for r in results)
            slab_rate_for_entry = self._slab_rate_pct if entry_has_slab else None

            entries.append({
                "asset_class": asset_class_val,
                "st_gain": st_gain,
                "lt_gain": lt_gain,
                "total_gain": st_gain + lt_gain,
                "ltcg_exemption_used": exemption_used,
                "st_tax_estimate": st_tax,
                "lt_tax_estimate": lt_tax,
                "total_tax_estimate": st_tax + lt_tax,
                "slab_rate_pct": slab_rate_for_entry,
                "asset_breakdown": [
                    {
                        "asset_id": r.asset_id,
                        "asset_name": r.asset_name,
                        "asset_type": r.asset_type,
                        "st_gain": r.st_gain,
                        "lt_gain": r.lt_gain,
                        "st_tax_estimate": r.st_tax_estimate,
                        "lt_tax_estimate": r.lt_tax_estimate,
                        "ltcg_exemption_used": r.ltcg_exemption_used,
                    }
                    for r in sorted(results, key=lambda r: abs(r.st_gain + r.lt_gain), reverse=True)
                ],
            })

            total_st_gain += st_gain
            total_lt_gain += lt_gain
            total_st_tax += st_tax
            total_lt_tax += lt_tax
            if entry_has_slab:
                has_slab = True

        return {
            "fy": fy_label,
            "entries": entries,
            "totals": {
                "total_st_gain": total_st_gain,
                "total_lt_gain": total_lt_gain,
                "total_gain": total_st_gain + total_lt_gain,
                "total_st_tax": total_st_tax,
                "total_lt_tax": total_lt_tax,
                "total_tax": total_st_tax + total_lt_tax,
                "has_slab_rate_items": has_slab,
            },
        }

    # ── Unrealised gains ──────────────────────────────────────────────────────

    def _build_lots_for_asset(self, asset_id: int, asset_type: str, uow) -> tuple[list, list]:
        """Build open lots and matched sells for a single FIFO-tracked asset."""
        transactions = uow.transactions.list_by_asset(asset_id)
        lots, sells = [], []
        for t in sorted(transactions, key=lambda x: x.date):
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            if ttype in LOT_TYPES and t.units:
                is_bonus = ttype == "BONUS"
                price = 0.0 if is_bonus else (abs(t.amount_inr / 100.0) / t.units if t.units else 0)
                lots.append(_Lot(
                    lot_id=t.lot_id or str(t.id),
                    buy_date=t.date,
                    units=t.units,
                    buy_price_per_unit=0.0 if is_bonus else (price or t.price_per_unit),
                    buy_amount_inr=0.0 if is_bonus else abs(t.amount_inr / 100.0),
                ))
            elif ttype in SELL_TYPES and t.units:
                sells.append(_Sell(date=t.date, units=t.units, amount_inr=abs(t.amount_inr / 100.0)))

        stcg_days = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
        matched = match_lots_fifo(lots, sells, stcg_days=stcg_days)

        sold_units: dict[str, float] = {}
        for m in matched:
            sold_units[m["lot_id"]] = sold_units.get(m["lot_id"], 0.0) + m["units_sold"]

        price_cache = uow.price_cache.get_by_asset_id(asset_id)
        current_price = (price_cache.price_inr / 100.0) if price_cache else None

        open_lots = []
        for lot in lots:
            units_remaining = lot.units - sold_units.get(lot.lot_id, 0.0)
            if units_remaining <= 0:
                continue
            entry = {
                "lot_id": lot.lot_id,
                "buy_date": lot.buy_date,
                "units": units_remaining,
                "buy_price_per_unit": lot.buy_price_per_unit,
                "buy_amount_inr": lot.buy_amount_inr,
            }
            if current_price is not None:
                unrealised = compute_lot_unrealised(lot, current_price, stcg_days=stcg_days)
                scale = units_remaining / lot.units if lot.units else 0
                entry.update({
                    "current_value": current_price * units_remaining,
                    "unrealised_gain": unrealised["unrealised_gain"] * scale,
                    "holding_days": unrealised["holding_days"],
                    "is_short_term": unrealised["is_short_term"],
                })
            else:
                holding_days = (date.today() - lot.buy_date).days
                entry.update({
                    "current_value": None,
                    "unrealised_gain": None,
                    "holding_days": holding_days,
                    "is_short_term": holding_days < stcg_days,
                })
            open_lots.append(entry)

        return open_lots, matched

    def get_unrealised_summary(self) -> dict:
        all_lots: list[dict] = []
        with self._uow_factory() as uow:
            for asset in uow.assets.list(active=True):
                atype = asset.asset_type.value
                if atype not in LOT_ASSET_TYPES:
                    continue
                try:
                    open_lots, _ = self._build_lots_for_asset(asset.id, atype, uow)
                    for lot in open_lots:
                        all_lots.append({
                            **lot,
                            "asset_id": asset.id,
                            "asset_name": asset.name,
                            "asset_type": atype,
                            "asset_class": asset.asset_class.value,
                        })
                except Exception as e:
                    logger.warning("Error building lots for asset %d: %s", asset.id, str(e))

        total_st = 0.0
        total_lt = 0.0
        enriched = []
        for lot in all_lots:
            gain = lot.get("unrealised_gain") or 0.0
            is_st = lot.get("is_short_term", True)
            atype = lot["asset_type"]
            near_threshold = (
                not is_st and gain > 0
                and atype in {"STOCK_IN", "MF"}
                and (LTCG_NEAR_THRESHOLD - gain) <= LTCG_NEAR_THRESHOLD * LTCG_NEAR_PCT
            )
            if is_st:
                total_st += gain
            else:
                total_lt += gain
            entry = dict(lot)
            if not isinstance(entry.get("buy_date"), str):
                entry["buy_date"] = str(entry["buy_date"])
            entry["near_ltcg_threshold"] = near_threshold
            enriched.append(entry)

        return {
            "lots": enriched,
            "totals": {
                "total_st_unrealised": total_st,
                "total_lt_unrealised": total_lt,
                "total_unrealised": total_st + total_lt,
                "near_threshold_count": sum(1 for l in enriched if l["near_ltcg_threshold"]),
            },
        }

    def get_harvest_opportunities(self) -> dict:
        summary = self.get_unrealised_summary()
        for lot in summary["lots"]:
            if not isinstance(lot.get("buy_date"), str):
                lot["buy_date"] = str(lot["buy_date"])
        opportunities = find_harvest_opportunities(summary["lots"])
        return {"opportunities": opportunities}
```

> **Note on the import:** `from app.services.tax.strategies import` triggers `__init__.py` which imports all strategy modules and populates `_REGISTRY`. The `# noqa: F401` suppresses the "imported but unused" linter warning.

- [x] **Step 2: Fix the import line** — the bare `from app.services.tax.strategies import` is invalid Python. Replace with a named import that still triggers the module load:

In the file above, change:
```python
from app.services.tax.strategies import  # noqa: F401 — triggers registration
```
to:
```python
import app.services.tax.strategies  # noqa: F401 — triggers @register_tax_strategy decorators
```

- [x] **Step 3: Verify the server starts**

```bash
cd backend && uv run uvicorn app.main:app --reload &
sleep 3 && curl -s "http://localhost:8000/tax/summary?fy=2024-25" | python3 -m json.tool | head -20
kill %1
```

Expected: JSON response with `entries`, `totals` keys. No `ImportError`.

- [x] **Step 4: Commit**

```bash
cd backend && git add app/services/tax_service.py
git commit -m "feat: restructure TaxService — UoW factory, strategy dispatch, asset_class grouping"
```

---

## Task 9: Update `dependencies.py` and `.env`

**Files:**
- Modify: `backend/app/api/dependencies.py`
- Modify: `backend/.env`

- [x] **Step 1: Add `SLAB_RATE` to `.env`**

Add this line to `backend/.env`:

```
SLAB_RATE=30
```

- [x] **Step 2: Update `get_tax_service` in `dependencies.py`**

Find and replace the existing `get_tax_service` function (currently lines 132–133):

```python
# Old:
def get_tax_service(db: Session = Depends(get_db)) -> TaxService:
    return TaxService(db)
```

```python
# New:
import os

def get_tax_service(db: Session = Depends(get_db)) -> TaxService:
    slab_rate_pct = float(os.environ.get("SLAB_RATE", "30.0"))
    return TaxService(uow_factory=lambda: UnitOfWork(db), slab_rate_pct=slab_rate_pct)
```

Add `import os` at the top of `dependencies.py` if not already present.

- [x] **Step 3: Run all tests to confirm nothing is broken**

```bash
cd backend && uv run pytest -x -q
```

Expected: Any failures will be in `test_tax_api.py` due to response shape change — that's fixed in Task 10. Other tests should PASS.

- [x] **Step 4: Commit**

```bash
cd backend && git add app/api/dependencies.py .env
git commit -m "feat: inject slab_rate_pct into TaxService from SLAB_RATE env var"
```

---

## Task 10: Update Integration Tests for New Response Shape

**Files:**
- Modify: `backend/tests/integration/test_tax_api.py`

The existing tests check `entry["asset_type"]`, `entry["is_st_slab"]`, and `entry["st_tax_estimate"] is None`. All three no longer exist in the new response. Update the tests.

- [ ] **Step 1: Replace `test_tax_api.py` with updated assertions**

```python
# backend/tests/integration/test_tax_api.py
import pytest
from tests.factories import make_asset


def test_tax_summary_returns_200(client):
    resp = client.get("/tax/summary?fy=2024-25")
    assert resp.status_code == 200
    data = resp.json()
    assert "fy" in data
    assert "entries" in data
    assert "totals" in data


def test_tax_summary_empty_db(client):
    resp = client.get("/tax/summary?fy=2024-25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == []
    assert data["totals"]["total_st_gain"] == 0.0
    assert data["totals"]["total_lt_gain"] == 0.0
    assert data["totals"]["total_tax"] == 0.0


def test_tax_summary_invalid_fy_returns_422(client):
    resp = client.get("/tax/summary?fy=bad")
    assert resp.status_code == 422


def test_tax_summary_missing_fy_returns_422(client):
    resp = client.get("/tax/summary")
    assert resp.status_code == 422


def test_tax_summary_stock_lt_gain(client):
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    # BUY Jan 2023, SELL Jun 2024 → 517 days → LT for equity
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2023-01-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-06-01", "units": 10,
        "price_per_unit": 1500.0, "amount_inr": 15000.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    # Grouped by asset_class now
    entry = next((e for e in entries if e["asset_class"] == "EQUITY"), None)
    assert entry is not None
    assert entry["lt_gain"] == pytest.approx(5000.0)
    assert entry["st_gain"] == pytest.approx(0.0)
    # LTCG exemption: 5000 < 125000 → fully exempt → lt_tax = 0
    assert entry["lt_tax_estimate"] == pytest.approx(0.0)
    assert entry["ltcg_exemption_used"] == pytest.approx(5000.0)
    assert entry["slab_rate_pct"] is None   # pure equity — no slab rate

    # asset_breakdown present and contains this asset
    assert len(entry["asset_breakdown"]) == 1
    breakdown = entry["asset_breakdown"][0]
    assert breakdown["asset_id"] == asset_id
    assert breakdown["lt_gain"] == pytest.approx(5000.0)


def test_tax_summary_stock_st_gain(client):
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    # BUY Jun 2024, SELL Sep 2024 → 92 days → ST at 20%
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-06-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-09-01", "units": 10,
        "price_per_unit": 1200.0, "amount_inr": 12000.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    entry = next(e for e in resp.json()["entries"] if e["asset_class"] == "EQUITY")
    assert entry["st_gain"] == pytest.approx(2000.0)
    assert entry["st_tax_estimate"] == pytest.approx(400.0)   # 2000 × 20%
    assert entry["slab_rate_pct"] is None


def test_tax_summary_excludes_sells_outside_fy(client):
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    # SELL in FY 2023-24 — should NOT appear in FY 2024-25
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2022-01-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-03-01", "units": 10,
        "price_per_unit": 1500.0, "amount_inr": 15000.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    data = resp.json()
    assert data["totals"]["total_lt_gain"] == pytest.approx(0.0)
    assert data["entries"] == []


def test_tax_summary_us_stock_st_uses_slab(client):
    """STOCK_US ST gain uses SLAB_RATE (30%) not 20%."""
    asset_resp = client.post("/assets", json=make_asset(
        asset_type="STOCK_US", asset_class="EQUITY", identifier="AAPL"
    ))
    asset_id = asset_resp.json()["id"]

    # BUY Jun 2024, SELL Sep 2024 → 92 days < 730 → ST at slab
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-06-01", "units": 5,
        "price_per_unit": 100.0, "amount_inr": -500.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-09-01", "units": 5,
        "price_per_unit": 120.0, "amount_inr": 600.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    entry = next(e for e in resp.json()["entries"] if e["asset_class"] == "EQUITY")
    assert entry["st_gain"] == pytest.approx(100.0)
    assert entry["st_tax_estimate"] == pytest.approx(30.0)   # 100 × 30% slab
    assert entry["slab_rate_pct"] == pytest.approx(30.0)     # slab label present


def test_tax_summary_asset_breakdown_link(client):
    """asset_breakdown contains asset_id for linking to asset page."""
    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-06-01", "units": 10,
        "price_per_unit": 100.0, "amount_inr": -1000.0, "charges_inr": 0,
    })
    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "SELL", "date": "2024-09-01", "units": 10,
        "price_per_unit": 120.0, "amount_inr": 1200.0, "charges_inr": 0,
    })

    resp = client.get("/tax/summary?fy=2024-25")
    entry = next(e for e in resp.json()["entries"] if e["asset_class"] == "EQUITY")
    assert len(entry["asset_breakdown"]) == 1
    assert entry["asset_breakdown"][0]["asset_id"] == asset_id
    assert "asset_name" in entry["asset_breakdown"][0]
    assert "asset_type" in entry["asset_breakdown"][0]


def test_tax_unrealised_returns_200(client):
    resp = client.get("/tax/unrealised")
    assert resp.status_code == 200
    data = resp.json()
    assert "lots" in data
    assert "totals" in data


def test_tax_unrealised_empty(client):
    resp = client.get("/tax/unrealised")
    data = resp.json()
    assert data["lots"] == []
    assert data["totals"]["total_st_unrealised"] == 0.0
    assert data["totals"]["total_lt_unrealised"] == 0.0


def test_tax_unrealised_with_price_cache(client, db):
    from app.models.price_cache import PriceCache
    from datetime import datetime

    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-01-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    db.add(PriceCache(
        asset_id=asset_id, price_inr=120000,
        fetched_at=datetime.utcnow(), source="test", is_stale=False,
    ))
    db.commit()

    resp = client.get("/tax/unrealised")
    data = resp.json()
    assert len(data["lots"]) >= 1
    lot = next(l for l in data["lots"] if l["asset_id"] == asset_id)
    assert lot["unrealised_gain"] == pytest.approx(2000.0)
    assert "asset_class" in lot   # new field


def test_tax_harvest_returns_200(client):
    resp = client.get("/tax/harvest-opportunities")
    assert resp.status_code == 200
    assert "opportunities" in resp.json()


def test_tax_harvest_empty(client):
    assert resp.json()["opportunities"] == []   # keep pattern


def test_tax_harvest_with_loss(client, db):
    from app.models.price_cache import PriceCache
    from datetime import datetime

    asset_resp = client.post("/assets", json=make_asset(asset_type="STOCK_IN", asset_class="EQUITY"))
    asset_id = asset_resp.json()["id"]

    client.post(f"/assets/{asset_id}/transactions", json={
        "type": "BUY", "date": "2024-01-01", "units": 10,
        "price_per_unit": 1000.0, "amount_inr": -10000.0, "charges_inr": 0,
    })
    db.add(PriceCache(
        asset_id=asset_id, price_inr=80000,
        fetched_at=datetime.utcnow(), source="test", is_stale=False,
    ))
    db.commit()

    resp = client.get("/tax/harvest-opportunities")
    data = resp.json()
    assert len(data["opportunities"]) >= 1
    opp = next(o for o in data["opportunities"] if o["asset_id"] == asset_id)
    assert opp["unrealised_loss"] == pytest.approx(2000.0)
```

- [ ] **Step 2: Fix the broken `test_tax_harvest_empty` test** — missing `resp =` assignment. Replace:

```python
def test_tax_harvest_empty(client):
    assert resp.json()["opportunities"] == []   # keep pattern
```

with:

```python
def test_tax_harvest_empty(client):
    resp = client.get("/tax/harvest-opportunities")
    assert resp.json()["opportunities"] == []
```

- [ ] **Step 3: Run the full test suite**

```bash
cd backend && uv run pytest -x -q
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
cd backend && git add tests/integration/test_tax_api.py
git commit -m "test: update tax API integration tests for new asset_class response shape"
```

---

## Task 11: Frontend Types

**Files:**
- Modify: `frontend/types/index.ts`

- [ ] **Step 1: Update tax types in `types/index.ts`**

Find the `// ── Tax types ──` section (currently around line 247) and replace the entire block through `HarvestResponse`:

```typescript
// ── Tax types ──────────────────────────────────────────────────────────────

export type AssetClass = 'EQUITY' | 'DEBT' | 'GOLD' | 'REAL_ESTATE'

export interface AssetGainBreakdown {
  asset_id: number
  asset_name: string
  asset_type: AssetType
  st_gain: number
  lt_gain: number
  st_tax_estimate: number
  lt_tax_estimate: number
  ltcg_exemption_used: number
}

export interface TaxSummaryEntry {
  asset_class: AssetClass
  st_gain: number
  lt_gain: number
  total_gain: number
  ltcg_exemption_used: number
  st_tax_estimate: number
  lt_tax_estimate: number
  total_tax_estimate: number
  slab_rate_pct: number | null
  asset_breakdown: AssetGainBreakdown[]
}

export interface TaxSummaryTotals {
  total_st_gain: number
  total_lt_gain: number
  total_gain: number
  total_st_tax: number
  total_lt_tax: number
  total_tax: number
  has_slab_rate_items: boolean
}

export interface TaxSummaryResponse {
  fy: string
  entries: TaxSummaryEntry[]
  totals: TaxSummaryTotals
}

export interface UnrealisedLot {
  asset_id: number
  asset_name: string
  asset_type: AssetType
  asset_class: AssetClass
  lot_id: string
  buy_date: string
  units_remaining: number
  buy_price_per_unit: number
  buy_amount_inr: number
  current_value: number | null
  unrealised_gain: number | null
  holding_days: number
  is_short_term: boolean
  near_ltcg_threshold: boolean
}

export interface UnrealisedTotals {
  total_st_unrealised: number
  total_lt_unrealised: number
  total_unrealised: number
  near_threshold_count: number
}

export interface UnrealisedResponse {
  lots: UnrealisedLot[]
  totals: UnrealisedTotals
}

export interface HarvestOpportunity extends UnrealisedLot {
  unrealised_loss: number
}

export interface HarvestResponse {
  opportunities: HarvestOpportunity[]
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | grep -E "error|Error" | head -20
```

Expected: No type errors (there will be errors in `tax/page.tsx` until Task 12).

- [ ] **Step 3: Commit**

```bash
cd frontend && git add types/index.ts
git commit -m "feat: update TaxSummaryEntry types — asset_class grouping, asset_breakdown, slab_rate_pct"
```

---

## Task 12: Frontend Collapsible UI

**Files:**
- Modify: `frontend/app/tax/page.tsx`

Replace the entire file. Key changes:
- Remove `TAX_CLASS_MAP`, `TAX_CLASS_ORDER`, `rollupRealised()`, `GainRow` interface
- Add `ASSET_CLASS_LABELS` map and collapsible state
- Render `summary.entries` directly (already grouped and ordered by backend)
- Add `+`/`−` toggle per category row
- Render asset sub-rows when expanded, linked to `/assets/{id}`
- Show `slab_rate_pct` label on category row

- [ ] **Step 1: Write the new `tax/page.tsx`**

```tsx
'use client'
import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { ASSET_TYPE_LABELS } from '@/constants'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'
import {
  TaxSummaryResponse, TaxSummaryEntry, AssetGainBreakdown,
  UnrealisedResponse, UnrealisedLot, HarvestResponse, HarvestOpportunity, AssetType,
} from '@/types'
import { Skeleton } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'

const CURRENT_FY = '2024-25'
const FY_OPTIONS = ['2024-25', '2023-24', '2022-23']

const ASSET_CLASS_LABELS: Record<string, string> = {
  EQUITY: 'Equity',
  DEBT: 'Debt',
  GOLD: 'Gold',
  REAL_ESTATE: 'Real Estate',
}

// Unrealised section still groups by asset_class (now in response)
interface UnrealisedRow { cls: string; st: number; lt: number }

function rollupUnrealised(lots: UnrealisedLot[]): UnrealisedRow[] {
  const map: Record<string, UnrealisedRow> = {}
  for (const lot of lots) {
    if (lot.unrealised_gain == null) continue
    const cls = lot.asset_class ?? 'Other'
    if (!map[cls]) map[cls] = { cls, st: 0, lt: 0 }
    if (lot.is_short_term) map[cls].st += lot.unrealised_gain
    else map[cls].lt += lot.unrealised_gain
  }
  return Object.values(map).sort((a, b) => Math.abs(b.st + b.lt) - Math.abs(a.st + a.lt))
}

interface HarvestRow { asset_id: number; asset_name: string; asset_type: string; st_loss: number; lt_loss: number; total_loss: number }

function rollupHarvest(opps: HarvestOpportunity[]): HarvestRow[] {
  const map: Record<number, HarvestRow> = {}
  for (const o of opps) {
    if (!map[o.asset_id]) map[o.asset_id] = { asset_id: o.asset_id, asset_name: o.asset_name, asset_type: o.asset_type, st_loss: 0, lt_loss: 0, total_loss: 0 }
    const r = map[o.asset_id]
    if (o.is_short_term) r.st_loss += o.unrealised_loss
    else r.lt_loss += o.unrealised_loss
    r.total_loss += o.unrealised_loss
  }
  return Object.values(map).sort((a, b) => b.total_loss - a.total_loss)
}

// ── Shared styles ─────────────────────────────────────────────────────────────

const card = 'rounded-xl border border-border bg-card p-5'
const cardStyle = { boxShadow: 'var(--shadow-card)' }
const th = 'pb-3 text-left text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary'
const thr = `${th} text-right`

function GainAmt({ value, fmt }: { value: number; fmt: (n: number) => string }) {
  if (value === 0) return <span className="text-tertiary">—</span>
  return <span className={`font-mono ${value >= 0 ? 'text-gain' : 'text-loss'}`}>{fmt(value)}</span>
}

function TaxEstimate({ value, fmt }: { value: number; fmt: (n: number) => string }) {
  if (value === 0) return <span className="text-tertiary">—</span>
  return <span className="font-mono text-loss">{fmt(value)}</span>
}

function ToggleBtn({ expanded, onClick }: { expanded: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border border-border text-[10px] text-tertiary transition-colors hover:border-accent hover:text-accent"
      aria-label={expanded ? 'Collapse' : 'Expand'}
    >
      {expanded ? '−' : '+'}
    </button>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TaxPage() {
  const { formatINR } = usePrivateMoney()
  const [fy, setFy] = useState(CURRENT_FY)
  const [summary, setSummary] = useState<TaxSummaryResponse | null>(null)
  const [unrealised, setUnrealised] = useState<UnrealisedResponse | null>(null)
  const [harvest, setHarvest] = useState<HarvestResponse | null>(null)
  const [loadingSummary, setLoadingSummary] = useState(true)
  const [loadingUnrealised, setLoadingUnrealised] = useState(true)
  const [loadingHarvest, setLoadingHarvest] = useState(true)
  const [expandedClasses, setExpandedClasses] = useState<Set<string>>(new Set())

  const [harvestPage, setHarvestPage] = useState(1)
  const [harvestPageSize, setHarvestPageSize] = useState(10)

  useEffect(() => {
    setLoadingSummary(true)
    setSummary(null)
    api.tax.summary(fy).then(setSummary).finally(() => setLoadingSummary(false))
  }, [fy])

  useEffect(() => {
    api.tax.unrealised().then(setUnrealised).finally(() => setLoadingUnrealised(false))
    api.tax.harvestOpportunities().then(setHarvest).finally(() => setLoadingHarvest(false))
  }, [])

  const unrealisedRows = useMemo(() => rollupUnrealised(unrealised?.lots ?? []), [unrealised])
  const harvestRows = useMemo(() => rollupHarvest(harvest?.opportunities ?? []), [harvest])

  const harvestTotal = harvestRows.length
  const harvestTotalPages = Math.max(1, Math.ceil(harvestTotal / harvestPageSize))
  const harvestSlice = harvestRows.slice((harvestPage - 1) * harvestPageSize, harvestPage * harvestPageSize)

  const totals = summary?.totals

  function toggleClass(cls: string) {
    setExpandedClasses(prev => {
      const next = new Set(prev)
      next.has(cls) ? next.delete(cls) : next.add(cls)
      return next
    })
  }

  return (
    <div className="space-y-8">
      {/* Header + FY selector */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl text-primary">Tax Summary</h1>
        <select
          value={fy}
          onChange={(e) => { setFy(e.target.value); setExpandedClasses(new Set()) }}
          className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent"
        >
          {FY_OPTIONS.map((f) => <option key={f} value={f}>FY {f}</option>)}
        </select>
      </div>

      {/* Summary stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {loadingSummary ? [1,2,3,4].map((i) => <Skeleton key={i} className="h-20 rounded-xl" />) : (<>
          {[
            { label: 'ST Gains', value: totals?.total_st_gain ?? 0 },
            { label: 'LT Gains', value: totals?.total_lt_gain ?? 0 },
            { label: 'Total Gain', value: totals?.total_gain ?? 0 },
            { label: 'Est. Tax', value: totals?.total_tax ?? 0, suffix: totals?.has_slab_rate_items ? '+ slab est.' : undefined },
          ].map(({ label, value, suffix }) => (
            <div key={label} className={`${card} space-y-1`} style={cardStyle}>
              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">{label}</p>
              <p className={`text-xl font-semibold font-mono ${value >= 0 ? 'text-gain' : 'text-loss'}`}>{formatINR(value)}</p>
              {suffix && <p className="text-[10px] text-tertiary">{suffix}</p>}
            </div>
          ))}
        </>)}
      </div>

      {/* ── Realised gains ── */}
      <div className={card} style={cardStyle}>
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
          Realised Gains — FY {fy}
        </h2>
        {loadingSummary ? (
          <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
        ) : !summary?.entries.length ? (
          <p className="py-10 text-center text-sm text-tertiary">No realised gains for FY {fy}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Category</th>
                <th className={thr}>ST Gain / Loss</th>
                <th className={thr}>LT Gain / Loss</th>
                <th className={thr}>Exemption</th>
                <th className={thr}>ST Tax Est.</th>
                <th className={thr}>LT Tax Est.</th>
              </tr>
            </thead>
            <tbody>
              {summary.entries.map((row) => {
                const isExpanded = expandedClasses.has(row.asset_class)
                const hasBreakdown = row.asset_breakdown.length > 0
                return (
                  <React.Fragment key={row.asset_class}>
                    {/* Category row */}
                    <tr className="border-b border-border hover:bg-accent-subtle/30 transition-colors">
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          {hasBreakdown && (
                            <ToggleBtn expanded={isExpanded} onClick={() => toggleClass(row.asset_class)} />
                          )}
                          <span className="font-medium text-primary">
                            {ASSET_CLASS_LABELS[row.asset_class] ?? row.asset_class}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-right"><GainAmt value={row.st_gain} fmt={formatINR} /></td>
                      <td className="py-3 pr-4 text-right"><GainAmt value={row.lt_gain} fmt={formatINR} /></td>
                      <td className="py-3 pr-4 text-right font-mono text-gain">
                        {row.ltcg_exemption_used > 0 ? formatINR(row.ltcg_exemption_used) : '—'}
                      </td>
                      <td className="py-3 pr-4 text-right">
                        <TaxEstimate value={row.st_tax_estimate} fmt={formatINR} />
                        {row.slab_rate_pct != null && (
                          <div className="mt-0.5 text-[10px] text-tertiary">{row.slab_rate_pct}% slab (est.)</div>
                        )}
                      </td>
                      <td className="py-3 text-right">
                        <TaxEstimate value={row.lt_tax_estimate} fmt={formatINR} />
                      </td>
                    </tr>

                    {/* Asset sub-rows */}
                    {isExpanded && row.asset_breakdown.map((asset) => (
                      <tr
                        key={asset.asset_id}
                        className="border-b border-border last:border-0 bg-accent-subtle/20"
                      >
                        <td className="py-2 pl-8 pr-4">
                          <Link
                            href={`/assets/${asset.asset_id}`}
                            className="text-sm font-medium text-accent hover:underline"
                          >
                            {asset.asset_name}
                          </Link>
                          <span className="ml-2 text-[10px] text-tertiary">
                            {ASSET_TYPE_LABELS[asset.asset_type as AssetType] ?? asset.asset_type}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-right text-sm">
                          <GainAmt value={asset.st_gain} fmt={formatINR} />
                        </td>
                        <td className="py-2 pr-4 text-right text-sm">
                          <GainAmt value={asset.lt_gain} fmt={formatINR} />
                        </td>
                        <td className="py-2 pr-4 text-right text-tertiary text-sm">—</td>
                        <td className="py-2 pr-4 text-right text-sm">
                          <TaxEstimate value={asset.st_tax_estimate} fmt={formatINR} />
                        </td>
                        <td className="py-2 text-right text-sm">
                          <TaxEstimate value={asset.lt_tax_estimate} fmt={formatINR} />
                        </td>
                      </tr>
                    ))}
                  </>
                )
              })}
            </tbody>
          </table>
        )}
        {totals?.has_slab_rate_items && !loadingSummary && (
          <p className="mt-3 text-[11px] text-tertiary">
            * Slab-rate estimates use the configured SLAB_RATE. Actual tax depends on your income bracket.
          </p>
        )}
      </div>

      {/* ── Unrealised gains ── */}
      <div className={card} style={cardStyle}>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Unrealised Gains (Open Positions)</h2>
          {unrealised && (
            <span className="text-xs text-tertiary">
              Total: <span className={`font-mono ${unrealised.totals.total_unrealised >= 0 ? 'text-gain' : 'text-loss'}`}>{formatINR(unrealised.totals.total_unrealised)}</span>
              {unrealised.totals.near_threshold_count > 0 && (
                <span className="ml-3 text-gold">⚠ {unrealised.totals.near_threshold_count} near ₹1.25L threshold</span>
              )}
            </span>
          )}
        </div>
        {loadingUnrealised ? (
          <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
        ) : unrealisedRows.length === 0 ? (
          <p className="py-8 text-center text-sm text-tertiary">No open positions with price data</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Category</th>
                <th className={thr}>ST Unrealised</th>
                <th className={thr}>LT Unrealised</th>
                <th className={thr}>Total</th>
              </tr>
            </thead>
            <tbody>
              {unrealisedRows.map((row) => (
                <tr key={row.cls} className="border-b border-border last:border-0 hover:bg-accent-subtle/30 transition-colors">
                  <td className="py-3 pr-4 font-medium text-primary">{ASSET_CLASS_LABELS[row.cls] ?? row.cls}</td>
                  <td className="py-3 pr-4 text-right"><GainAmt value={row.st} fmt={formatINR} /></td>
                  <td className="py-3 pr-4 text-right"><GainAmt value={row.lt} fmt={formatINR} /></td>
                  <td className={`py-3 text-right font-mono font-medium ${row.st + row.lt >= 0 ? 'text-gain' : 'text-loss'}`}>
                    {formatINR(row.st + row.lt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Tax-loss harvesting ── */}
      <div className={card} style={cardStyle}>
        <div className="mb-1">
          <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Tax-Loss Harvesting Opportunities</h2>
          <p className="mt-1 text-xs text-tertiary">Positions with unrealised losses — consider selling to offset gains</p>
        </div>
        {loadingHarvest ? (
          <div className="mt-4 space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
        ) : harvestRows.length === 0 ? (
          <p className="py-8 text-center text-sm text-tertiary">No loss-making positions</p>
        ) : (
          <>
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className={th}>Asset</th>
                  <th className={th}>Type</th>
                  <th className={thr}>ST Loss</th>
                  <th className={thr}>LT Loss</th>
                  <th className={thr}>Total Loss</th>
                </tr>
              </thead>
              <tbody>
                {harvestSlice.map((row) => (
                  <tr key={row.asset_id} className="border-b border-border last:border-0 hover:bg-loss-subtle/30 transition-colors">
                    <td className="py-2.5 pr-4">
                      <Link href={`/assets/${row.asset_id}`} className="font-medium text-accent hover:underline">
                        {row.asset_name}
                      </Link>
                    </td>
                    <td className="py-2.5 pr-4 text-xs text-secondary">{ASSET_TYPE_LABELS[row.asset_type as AssetType]}</td>
                    <td className="py-2.5 pr-4 text-right font-mono text-loss">
                      {row.st_loss > 0 ? formatINR(row.st_loss) : '—'}
                    </td>
                    <td className="py-2.5 pr-4 text-right font-mono text-loss">
                      {row.lt_loss > 0 ? formatINR(row.lt_loss) : '—'}
                    </td>
                    <td className="py-2.5 text-right font-mono font-semibold text-loss">
                      {formatINR(row.total_loss)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination
              page={harvestPage}
              pageSize={harvestPageSize}
              total={harvestTotal}
              totalPages={harvestTotalPages}
              onPageChange={setHarvestPage}
              onPageSizeChange={(s) => { setHarvestPageSize(s); setHarvestPage(1) }}
            />
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build to verify no TypeScript errors**

```bash
cd frontend && npm run build 2>&1 | grep -E "error TS|Error:" | head -20
```

Expected: No errors.

- [ ] **Step 3: Lint**

```bash
cd frontend && npm run lint
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
cd frontend && git add app/tax/page.tsx
git commit -m "feat: add collapsible per-asset breakdown to Realised Gains table"
```

---

## Task 13: Lot Helper Extraction (Last Step)

**Files:**
- Create: `backend/app/engine/lot_helper.py`
- Modify: `backend/app/services/returns/strategies/market_based.py`
- Modify: `backend/app/services/tax/strategies/fifo_base.py`

This is a pure refactor — no behaviour changes. Done last so the returns engine isn't touched until the tax feature is fully verified.

- [ ] **Step 1: Write failing tests for `LotHelper`**

Add to `backend/tests/unit/test_lot_engine.py` (or a new `test_lot_helper.py`):

```python
# Append to backend/tests/unit/test_lot_engine.py
from app.engine.lot_helper import LotHelper


def _make_buy(date_val, units, amount_inr, lot_id=None, txn_id=1):
    from unittest.mock import MagicMock
    t = MagicMock()
    t.type.value = "BUY"
    t.date = date_val
    t.units = units
    t.amount_inr = amount_inr
    t.lot_id = lot_id
    t.id = txn_id
    return t


def _make_sell(date_val, units, amount_inr, txn_id=2):
    from unittest.mock import MagicMock
    t = MagicMock()
    t.type.value = "SELL"
    t.date = date_val
    t.units = units
    t.amount_inr = amount_inr
    t.lot_id = None
    t.id = txn_id
    return t


def test_lot_helper_build_lots_sells():
    from datetime import date
    helper = LotHelper(stcg_days=365)
    txns = [
        _make_buy(date(2023, 1, 1), 10, -10000, lot_id="lot1"),
        _make_sell(date(2024, 6, 1), 10, 15000),
    ]
    lots, sells = helper.build_lots_sells(txns)
    assert len(lots) == 1
    assert lots[0].buy_amount_inr == pytest.approx(100.0)   # 10000 paise / 100 = 100 INR
    assert len(sells) == 1


def test_lot_helper_match_produces_gain():
    from datetime import date
    helper = LotHelper(stcg_days=365)
    txns = [
        _make_buy(date(2023, 1, 1), 10, -10000, lot_id="lot1"),
        _make_sell(date(2024, 6, 1), 10, 15000),
    ]
    lots, sells = helper.build_lots_sells(txns)
    open_lots, matched = helper.match(lots, sells)
    assert len(matched) == 1
    assert matched[0]["realised_gain_inr"] == pytest.approx(50.0)  # (150-100) INR
    assert matched[0]["is_short_term"] is False   # 517 days ≥ 365
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/unit/test_lot_engine.py -k "lot_helper" -v
```

Expected: `ImportError` — `lot_helper` doesn't exist.

- [ ] **Step 3: Write `engine/lot_helper.py`**

```python
# backend/app/engine/lot_helper.py
"""
LotHelper — shared lot-building and FIFO matching logic.

Extracted from MarketBasedStrategy and FifoTaxGainsStrategy to avoid
duplication. Both callers delegate here; if FIFO logic changes, one edit suffices.
"""
from __future__ import annotations

from app.engine.lot_engine import match_lots_fifo
from app.services.returns.strategies.market_based import (
    LOT_TYPES, SELL_TYPES, _Lot, _Sell, _OpenLot, _accumulate_sold_units,
)


class LotHelper:
    """
    Wraps lot-building and FIFO matching for a given stcg_days threshold.

    Usage:
        helper = LotHelper(stcg_days=365)
        lots, sells = helper.build_lots_sells(transactions)
        open_lots, matched = helper.match(lots, sells)
    """

    def __init__(self, stcg_days: int):
        self.stcg_days = stcg_days

    def build_lots_sells(self, txns) -> tuple[list[_Lot], list[_Sell]]:
        """Build sorted _Lot and _Sell lists from transaction records."""
        lots: list[_Lot] = []
        sells: list[_Sell] = []
        for t in sorted(txns, key=lambda x: x.date):
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            if ttype in LOT_TYPES and t.units:
                is_bonus = ttype == "BONUS"
                price_pu = 0.0 if is_bonus else (
                    abs(t.amount_inr / 100.0) / t.units if t.units else 0.0
                )
                lots.append(_Lot(
                    lot_id=t.lot_id or str(t.id),
                    buy_date=t.date,
                    units=t.units,
                    buy_price_per_unit=price_pu,
                    buy_amount_inr=0.0 if is_bonus else abs(t.amount_inr / 100.0),
                ))
            elif ttype in SELL_TYPES and t.units:
                sells.append(_Sell(date=t.date, units=t.units, amount_inr=abs(t.amount_inr / 100.0)))
        return lots, sells

    def match(self, lots: list[_Lot], sells: list[_Sell]) -> list[dict]:
        """Run FIFO matching; return raw match dicts from match_lots_fifo."""
        return match_lots_fifo(lots, sells, stcg_days=self.stcg_days)
```

> **Note:** `match()` returns only `matched` (not open lots) because open lot computation differs between tax and returns callers. Returns callers use `_match_and_get_open_lots` for `_OpenLot` objects; tax callers only need `matched` dicts. Keep the signature simple — don't force a common open-lot model.

- [ ] **Step 4: Update `FifoTaxGainsStrategy` to use `LotHelper`**

In `backend/app/services/tax/strategies/fifo_base.py`, replace the `_build_lots_sells` method and its imports:

Remove import: `from app.services.returns.strategies.market_based import LOT_TYPES, SELL_TYPES, _Lot, _Sell`

Add import: `from app.engine.lot_helper import LotHelper`

Replace the `_build_lots_sells` method body:
```python
def _build_lots_sells(self, txns) -> tuple[list, list]:
    return LotHelper(stcg_days=self.stcg_days).build_lots_sells(txns)
```

The `_fy_gains` and `compute` methods stay unchanged — they use `match_lots_fifo` directly since they don't need the `LotHelper.match()` wrapper.

- [ ] **Step 5: Update `MarketBasedStrategy` to use `LotHelper`**

In `backend/app/services/returns/strategies/market_based.py`:

Add import (near the top, after existing engine imports):
```python
from app.engine.lot_helper import LotHelper
```

Replace the `_build_lots_sells` method:
```python
def _build_lots_sells(self, txns) -> tuple[list[_Lot], list[_Sell]]:
    return LotHelper(stcg_days=self.stcg_days).build_lots_sells(txns)
```

`_match_and_get_open_lots` stays unchanged — it uses `match_lots_fifo` and `_OpenLot` directly and has its own open-lot logic.

- [ ] **Step 6: Run the full test suite**

```bash
cd backend && uv run pytest -x -q
```

Expected: All tests PASS. No behaviour change.

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/engine/lot_helper.py app/services/returns/strategies/market_based.py app/services/tax/strategies/fifo_base.py tests/unit/test_lot_engine.py
git commit -m "refactor: extract LotHelper to eliminate lot-building duplication between MarketBasedStrategy and FifoTaxGainsStrategy"
```

---

## Final Verification

- [ ] **Run all backend tests with coverage**

```bash
cd backend && uv run pytest --cov=app --cov-report=term-missing -q
```

Expected: All PASS, coverage ≥ 80%.

- [ ] **Run frontend build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds, no type errors.

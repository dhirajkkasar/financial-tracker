# Returns Strategy Missing-Conditions Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all conditions present in the old `services/returns_service.py` that were accidentally dropped during the strategy-pattern refactor, restoring correct behaviour for all asset types.

**Architecture:** Each task is isolated to one asset type (or the shared base). Tests go first (TDD). After each task the full test suite must stay green. Do **not** change the old `services/returns_service.py` — it is kept as reference only.

**Tech Stack:** Python 3.11, pytest, FastAPI, SQLAlchemy, Pydantic v2, `app/engine/lot_engine.py`, `app/engine/fd_engine.py`

---

## Differences Catalogue (old → new)

| # | Asset | Gap |
|---|-------|-----|
| 1 | **BASE** | `build_cashflows` has wrong signature `(asset, current_value, invested_value, uow)` — should be `(asset, uow)`, returns `None`, causing `TypeError: NoneType has no len()` in every `compute()` call that reaches the base |
| 2 | **BASE** | `compute()` calls `build_cashflows` with 4 args and never appends terminal inflow — after fix it must append `(date.today(), -current_value)` so XIRR has a positive return cashflow |
| 3 | **MF** | `get_invested_value` uses lot-engine open-lot cost; should use `snapshot.total_cost_inr / 100` (CAS authoritative basis) |
| 4 | **MF** | Fully-redeemed fund (`closing_units == 0`) not handled: `invested` becomes 0 (no open lots), `current_pnl` = 0, `alltime_pnl` = 0 — all wrong |
| 5 | **MF** | `build_cashflows` has 4-arg signature — must align to new 2-arg base |
| 6 | **MARKET** | `total_units`, `avg_price`, `current_price` never set in `AssetReturnsResponse` |
| 7 | **MARKET** | `alltime_pnl`, `st_realised_gain`, `lt_realised_gain` never set — FIFO matched-sells gains are computed in `_compute_lots_data` loop but discarded |
| 8 | **MARKET** | `cagr` never computed |
| 9 | **FD** | XIRR uses `(date.today(), accrued_today)` via base; should use `(maturity_date_or_today, maturity_amount)` — the contractual terminal cash flow |
| 10 | **FD** | `taxable_interest` sums INTEREST transactions, not formula (`accrued_today − invested`); for cumulative FDs with no posted INTEREST txns, this returns 0 |
| 11 | **FD** | `accrued_value_today` and `days_to_maturity` never set in response |
| 12 | **RD** | Same XIRR issue as FD — base terminal `(today, accrued)` instead of `(maturity_date_or_today, maturity_amount)` |
| 13 | **EPF** | Default `build_cashflows` includes INTEREST transactions as negative cashflows; INTEREST accumulates inside EPF, investor never receives it separately — XIRR becomes wrong |
| 14 | **EPF** | `get_current_value` returns `0` when no contributions; old code returned `None` |

---

## Task 1 — Fix base `build_cashflows` + `compute()` terminal inflow

**Files:**
- Modify: `backend/app/services/returns/strategies/base.py`
- Modify: `backend/tests/unit/test_returns_strategies.py` (tests already exist, they just fail)

### What the fix looks like

`build_cashflows` must:
- Accept `(self, asset, uow)` — two real args
- Iterate all transactions for the asset, skip `EXCLUDED_TYPES`
- **Negate** each DB amount: `amount = -(t.amount_inr / 100)` — this matches the sign convention the tests assert (CONTRIBUTION stored as `-500000` paise → cashflow `+5000`; INTEREST stored as `+50000` → cashflow `-500`)

`compute()` must:
- Call `build_cashflows(asset, uow)` — two args
- Append terminal inflow `(date.today(), -current_value)` when `current_value > 0` — the negated convention means the inflow for the investor is negative here so XIRR sees one side positive (contributions) and one side negative (terminal)

- [ ] **Step 1: Confirm the 4 failing tests**

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py -v 2>&1 | grep -E "FAILED|PASSED"
```

Expected: 5 failures including `test_base_strategy_build_cashflows_*`, `test_valuation_based_compute_*`, `test_fd_strategy_compute_*`, `test_market_based_compute_returns_response`.

- [ ] **Step 2: Fix `base.py`**

Replace the current `build_cashflows` and `compute`:

```python
# app/services/returns/strategies/base.py
from app.engine.returns import EXCLUDED_TYPES, OUTFLOW_TYPES, INFLOW_TYPES, compute_xirr, compute_cagr, compute_absolute_return

def build_cashflows(self, asset, uow: UnitOfWork) -> list[tuple[date, float]]:
    """
    Default: iterate all non-excluded transactions, negate DB sign.

    DB stores outflows as negative paise (BUY, SIP, CONTRIBUTION, VEST).
    Negating gives a positive cashflow for outflows — consistent with the
    convention used throughout the strategy layer.  The base compute() appends
    the terminal inflow (current_value, negated) so compute_xirr sees mixed signs.
    """
    txns = uow.transactions.list_by_asset(asset.id)
    return [
        (t.date, -(t.amount_inr / 100))
        for t in txns
        if t.type.value not in EXCLUDED_TYPES
    ]

def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
    invested = self.get_invested_value(asset, uow)
    current = self.get_current_value(asset, uow)
    cashflows = self.build_cashflows(asset, uow)          # ← 2 args
    if current is not None and current > 0:
        cashflows = cashflows + [(date.today(), -current)] # ← negated terminal
    xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None
    pnl = (current - invested) if (current is not None and invested is not None) else None
    pnl_pct = (pnl / invested * 100) if (pnl is not None and invested and invested > 0) else None
    return AssetReturnsResponse(
        asset_id=asset.id,
        asset_name=asset.name,
        asset_type=asset.asset_type.value,
        is_active=asset.is_active,
        invested=invested,
        current_value=current,
        current_pnl=pnl,
        current_pnl_pct=pnl_pct,
        xirr=xirr,
    )
```

- [ ] **Step 3: Run the tests that were failing — they should pass now**

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py -v 2>&1 | grep -E "FAILED|PASSED|ERROR"
```

Expected: 0 failures.

- [ ] **Step 4: Run full unit suite — no regressions**

```bash
cd backend && uv run pytest tests/unit/ -v 2>&1 | tail -20
```

Expected: all pass (same or more than before).

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/returns/strategies/base.py
git commit -m "fix: base strategy build_cashflows signature and terminal inflow in compute()"
```

---

## Task 2 — Fix MF strategy

**Files:**
- Modify: `backend/app/services/returns/strategies/asset_types/mf.py`
- Modify: `backend/tests/unit/test_returns_strategies.py`

### What needs fixing in MF

**a) `build_cashflows` — align to 2-arg signature**

Currently: `build_cashflows(self, asset, current_value, invested_value, uow)` — 4-arg.
After Task 1 `base.compute()` calls `build_cashflows(asset, uow)` so passing current_value is wrong.
MF still needs to control its own cashflows because it excludes EXCLUDED_TYPES explicitly —
the default base implementation already does this, so MFStrategy can **remove** `build_cashflows` entirely
and inherit the default. The terminal is added by `base.compute()`.

**b) `get_invested_value` — use CAS total_cost**

Currently inherits `MarketBasedStrategy.get_invested_value()` (open-lot cost basis).
Must override to use `snapshot.total_cost_inr / 100` — the CAS-authoritative cost.

If no snapshot: raise `ValidationError` (same as `get_current_value`).

**c) Fully-redeemed fund (`closing_units == 0`)**

`get_current_value` already returns `snap.market_value_inr / 100` which equals 0 for fully-redeemed.
But `get_invested_value` would return `snapshot.total_cost_inr / 100` (also 0 for fully redeemed?).
The old code returned `total_invested_txn` (sum of all outflow txns) so P&L makes sense.

Override `compute()` in `MFStrategy` to detect `snap.closing_units == 0` and:
- Set `invested` = sum of all OUTFLOW transactions (absolute INR)
- Set `current_value` = 0
- Set `message` = "Fully redeemed"
- Compute XIRR from transaction cashflows only (no terminal, since current_value=0)

- [ ] **Step 1: Write failing tests first**

Add to `tests/unit/test_returns_strategies.py`:

```python
def test_mf_strategy_get_invested_value_uses_cas_cost():
    from datetime import timedelta
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF")
    snap = MagicMock()
    snap.date = date.today() - timedelta(days=2)
    snap.market_value_inr = 15_000_000  # ₹1,50,000
    snap.closing_units = 1000.0
    snap.total_cost_inr = 12_000_000    # ₹1,20,000 CAS cost basis
    uow = _make_uow(snap=snap)
    result = strategy.get_invested_value(asset, uow)
    assert abs(result - 120000.0) < 0.01   # uses CAS total_cost, not lot engine


def test_mf_strategy_fully_redeemed_fund():
    from datetime import timedelta
    from app.services.returns.strategies.asset_types.mf import MFStrategy
    strategy = MFStrategy()
    asset = _make_asset(asset_type="MF")
    snap = MagicMock()
    snap.date = date.today() - timedelta(days=2)
    snap.market_value_inr = 0
    snap.closing_units = 0
    snap.total_cost_inr = 0
    buy1 = _make_txn("SIP",  -5_000_000, date(2022, 1, 1))  # ₹50,000 outflow
    sell1 = _make_txn("REDEMPTION", 6_000_000, date(2023, 1, 1))  # ₹60,000 inflow
    uow = _make_uow(snap=snap, transactions=[buy1, sell1])
    result = strategy.compute(asset, uow)
    assert result.current_value == 0
    assert result.message == "Fully redeemed"
    assert result.invested is not None and result.invested > 0   # sum of outflows
```

Run to confirm they fail:

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py::test_mf_strategy_get_invested_value_uses_cas_cost tests/unit/test_returns_strategies.py::test_mf_strategy_fully_redeemed_fund -v
```

Expected: both FAIL.

- [ ] **Step 2: Implement fixes in `mf.py`**

```python
# app/services/returns/strategies/asset_types/mf.py
from datetime import date
from typing import ClassVar, Optional

from app.engine.returns import EXCLUDED_TYPES, INFLOW_TYPES, OUTFLOW_TYPES
from app.middleware.error_handler import ValidationError
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


SNAPSHOT_STALE_DAYS = 5


@register_strategy("MF")
class MFStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 365

    def _get_snapshot(self, asset, uow: UnitOfWork):
        snap = uow.cas_snapshots.get_latest_by_asset_id(asset.id)
        if snap is None:
            raise ValidationError(
                f"No CAS snapshot found for '{asset.name}'. "
                "Please import your CAS PDF statement first."
            )
        return snap

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """Invested = CAS total_cost (authoritative cost basis from statement)."""
        snap = self._get_snapshot(asset, uow)
        return snap.total_cost_inr / 100

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        snap = self._get_snapshot(asset, uow)
        today = date.today()
        snap_age = (today - snap.date).days
        if snap_age < SNAPSHOT_STALE_DAYS:
            return snap.market_value_inr / 100

        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        if price_entry is None:
            return snap.market_value_inr / 100  # best guess

        nav = price_entry.price_inr / 100
        return round(snap.closing_units * nav, 2)

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        snap = self._get_snapshot(asset, uow)

        # Fully redeemed fund
        if snap.closing_units == 0:
            txns = uow.transactions.list_by_asset(asset.id)
            invested = sum(
                abs(t.amount_inr / 100)
                for t in txns
                if t.type.value in OUTFLOW_TYPES
            )
            # Cashflows: outflows (positive negated) only; no terminal (redeemed)
            cashflows = [
                (t.date, -(t.amount_inr / 100))
                for t in txns
                if t.type.value not in EXCLUDED_TYPES
            ]
            from app.engine.returns import compute_xirr
            xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None
            return AssetReturnsResponse(
                asset_id=asset.id,
                asset_name=asset.name,
                asset_type=asset.asset_type.value,
                is_active=asset.is_active,
                invested=invested,
                current_value=0,
                current_pnl=None,
                current_pnl_pct=None,
                xirr=xirr,
                message="Fully redeemed",
            )

        # Active fund — delegate to MarketBasedStrategy
        return super().compute(asset, uow)
```

- [ ] **Step 3: Run new tests — they should pass**

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py -v 2>&1 | grep -E "FAILED|PASSED|ERROR"
```

Expected: 0 failures.

- [ ] **Step 4: Run full suite**

```bash
cd backend && uv run pytest tests/unit/ 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/returns/strategies/asset_types/mf.py tests/unit/test_returns_strategies.py
git commit -m "fix: MF strategy — CAS total_cost as invested, fully-redeemed fund handling"
```

---

## Task 3 — Fix MarketBasedStrategy: `alltime_pnl`, realised gains, `total_units`, `avg_price`, `current_price`, `cagr`

**Files:**
- Modify: `backend/app/services/returns/strategies/market_based.py`
- Modify: `backend/tests/unit/test_returns_strategies.py`

### What needs fixing

`MarketBasedStrategy.compute()` already calls `_compute_lots_data()` for unrealised gains.
It also needs to call the FIFO lot engine for **realised** gains from matched-sells, then:
- `alltime_pnl = current_pnl + st_realised + lt_realised`
- set `st_realised_gain` and `lt_realised_gain` in response
- set `total_units` (net units from transactions)
- set `avg_price` = `invested / total_units`
- set `current_price` from price_cache
- set `cagr` using oldest transaction date

The lot engine helper `compute_gains_summary(open_lots, matched_sells, asset_type)` already computes both unrealised and realised; it's just not called in the strategy.

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_returns_strategies.py`:

```python
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
```

Run to confirm failures:

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py::test_market_based_compute_alltime_pnl_includes_realised tests/unit/test_returns_strategies.py::test_market_based_compute_sets_total_units_avg_price_current_price tests/unit/test_returns_strategies.py::test_market_based_compute_sets_cagr -v
```

Expected: all FAIL.

- [ ] **Step 2: Implement in `market_based.py`**

Update `MarketBasedStrategy.compute()`:

```python
# app/services/returns/strategies/market_based.py

from app.engine.lot_engine import (
    match_lots_fifo, compute_gains_summary, compute_lot_unrealised, GRANDFATHERING_CUTOFF,
)
from app.engine.returns import UNIT_ADD_TYPES, UNIT_SUB_TYPES, compute_cagr

def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
    """Override to include lot gains, price metadata, units, cagr."""
    base = super().compute(asset, uow)  # calls AssetReturnsStrategy.compute()

    txns = uow.transactions.list_by_asset(asset.id)

    # Total units
    total_units = 0.0
    for t in txns:
        ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
        if ttype in UNIT_ADD_TYPES:
            total_units += (t.units or 0.0)
        elif ttype in UNIT_SUB_TYPES:
            total_units -= (t.units or 0.0)

    price_entry = uow.price_cache.get_by_asset_id(asset.id)
    current_price = (price_entry.price_inr / 100) if price_entry else None

    # avg_price
    invested = base.invested
    avg_price = (invested / total_units) if (total_units > 0 and invested) else None

    # Lot-level data (unrealised)
    lots_data = self._compute_lots_data(asset, uow)
    st_unrealised = sum(l["unrealised_gain"] for l in lots_data if l.get("is_short_term"))
    lt_unrealised = sum(l["unrealised_gain"] for l in lots_data if not l.get("is_short_term"))

    # Realised gains from matched sells
    lots_list, sells_list = self._build_lots_sells(txns)
    st_realised: Optional[float] = None
    lt_realised: Optional[float] = None
    if lots_list:
        try:
            matched = match_lots_fifo(lots_list, sells_list, stcg_days=self.stcg_days)
            sold_units_map: dict[str, float] = {}
            for m in matched:
                sold_units_map[m["lot_id"]] = sold_units_map.get(m["lot_id"], 0.0) + m["units_sold"]
            open_lot_dicts = []
            for lot in lots_list:
                remaining = lot.units - sold_units_map.get(lot.lot_id, 0.0)
                if remaining <= 0:
                    continue
                scale = remaining / lot.units if lot.units else 0.0
                open_lot_dicts.append({
                    "lot_id": lot.lot_id,
                    "buy_date": lot.buy_date,
                    "units_remaining": remaining,
                    "buy_price_per_unit": lot.buy_price_per_unit,
                    "buy_amount_inr": lot.buy_amount_inr * scale,
                    "current_value": (current_price * remaining) if current_price else None,
                    "unrealised_gain": None,
                    "holding_days": 0,
                    "is_short_term": True,
                })
            gains = compute_gains_summary(open_lot_dicts, matched, asset.asset_type.value)
            st_realised = gains.get("st_realised_gain")
            lt_realised = gains.get("lt_realised_gain")
        except Exception:
            pass

    # all-time P&L = current P&L + realised
    current_pnl = base.current_pnl
    if current_pnl is not None or st_realised is not None or lt_realised is not None:
        alltime_pnl = (current_pnl or 0.0) + (st_realised or 0.0) + (lt_realised or 0.0)
    else:
        alltime_pnl = None

    # CAGR
    cagr = None
    from app.engine.returns import EXCLUDED_TYPES
    non_excl = [t for t in txns if t.type.value not in EXCLUDED_TYPES]
    if non_excl and base.invested and base.invested > 0 and base.current_value:
        oldest = min(non_excl, key=lambda t: t.date)
        from datetime import date as _date
        years = (_date.today() - oldest.date).days / 365.0
        cagr = compute_cagr(base.invested, base.current_value, years)

    return base.model_copy(update={
        "total_units": total_units if total_units > 0 else None,
        "avg_price": avg_price,
        "current_price": current_price,
        "st_unrealised_gain": st_unrealised if lots_data else None,
        "lt_unrealised_gain": lt_unrealised if lots_data else None,
        "st_realised_gain": st_realised,
        "lt_realised_gain": lt_realised,
        "alltime_pnl": alltime_pnl,
        "cagr": cagr,
        "price_is_stale": price_entry.is_stale if price_entry else None,
        "price_fetched_at": price_entry.fetched_at.isoformat() if price_entry and price_entry.fetched_at else None,
    })

def _build_lots_sells(self, txns):
    """Helper to build _Lot and _Sell lists from transactions."""
    lots = []
    sells = []
    for t in sorted(txns, key=lambda x: x.date):
        ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
        if ttype in LOT_TYPES and t.units:
            is_bonus = ttype == "BONUS"
            price_pu = 0.0 if is_bonus else (
                t.price_per_unit or (abs(t.amount_inr / 100.0) / t.units if t.units else 0.0)
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
```

Note: `_build_lots_sells` is separate from `_compute_lots_data` and `get_invested_value` to avoid duplicating the loop 3× — extract the shared logic into this private helper and call it from all three.

- [ ] **Step 3: Run new tests**

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py -v 2>&1 | grep -E "FAILED|PASSED|ERROR"
```

Expected: 0 failures.

- [ ] **Step 4: Run full suite**

```bash
cd backend && uv run pytest tests/unit/ 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/returns/strategies/market_based.py tests/unit/test_returns_strategies.py
git commit -m "fix: market-based strategy — alltime_pnl, realised gains, total_units, avg_price, cagr"
```

---

## Task 4 — Fix FDStrategy: XIRR terminal, taxable_interest, missing fields

**Files:**
- Modify: `backend/app/services/returns/strategies/asset_types/fd.py`
- Modify: `backend/tests/unit/test_returns_strategies.py`

### What needs fixing

**a) XIRR**: Old code used `(maturity_date_or_today, maturity_amount)` as terminal cashflow — the contractual future value. Base `compute()` would add `(today, accrued_today)` which is wrong for an FD still running.

Fix: override `build_cashflows` to build outflow transactions + the maturity-amount terminal.

**b) `taxable_interest`**: Old code computed `max(0, accrued_today − invested)` from formula. New code sums INTEREST transactions which is 0 for cumulative FDs.

Fix: keep formula-based approach as primary; fall back to summing INTEREST transactions only if there are any (for matured/paid-out FDs).

**c) Missing fields**: `accrued_value_today` and `days_to_maturity` not set.

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_returns_strategies.py`:

```python
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
```

Run to confirm failures:

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py::test_fd_strategy_compute_days_to_maturity_and_accrued tests/unit/test_returns_strategies.py::test_fd_strategy_taxable_interest_formula_based -v
```

Expected: both FAIL.

- [ ] **Step 2: Implement fixes in `fd.py`**

```python
# app/services/returns/strategies/asset_types/fd.py
from datetime import date as date_cls
from typing import Optional

from app.engine.fd_engine import compute_fd_current_value, compute_fd_maturity
from app.engine.returns import OUTFLOW_TYPES, compute_absolute_return
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("FD")
class FDStrategy(ValuationBasedStrategy):

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd = uow.fd.get_by_asset_id(asset.id)
        if fd is None:
            return None
        principal_inr = fd.principal_amount / 100.0
        return compute_fd_current_value(
            principal_inr, fd.interest_rate_pct, fd.compounding.value,
            fd.start_date, fd.maturity_date,
        )

    def build_cashflows(self, asset, uow: UnitOfWork):
        """XIRR uses maturity_amount at maturity_date (the contractual terminal cash flow)."""
        fd = uow.fd.get_by_asset_id(asset.id)
        txns = uow.transactions.list_by_asset(asset.id)

        # Outflow contributions (negated sign convention)
        cashflows = [
            (t.date, -(t.amount_inr / 100))
            for t in txns
            if t.type.value in OUTFLOW_TYPES
        ]

        if fd is not None:
            principal_inr = fd.principal_amount / 100.0
            tenure_years = (fd.maturity_date - fd.start_date).days / 365.0
            maturity_amount = compute_fd_maturity(
                principal_inr, fd.interest_rate_pct, fd.compounding.value, tenure_years,
            )
            effective_end = fd.maturity_date if fd.maturity_date >= date_cls.today() else date_cls.today()
            # Inflow at maturity: negated sign convention → negative (investor receives)
            cashflows.append((effective_end, -maturity_amount))

        return cashflows

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        # Base builds invested/current/xirr correctly using our overrides
        base = super(ValuationBasedStrategy, self).compute(asset, uow)

        fd = uow.fd.get_by_asset_id(asset.id)
        if fd is None:
            return base.model_copy(update={"message": "No FD detail found"})

        principal_inr = fd.principal_amount / 100.0
        tenure_years = (fd.maturity_date - fd.start_date).days / 365.0
        maturity_amount = compute_fd_maturity(
            principal_inr, fd.interest_rate_pct, fd.compounding.value, tenure_years,
        )
        accrued_today = compute_fd_current_value(
            principal_inr, fd.interest_rate_pct, fd.compounding.value,
            fd.start_date, fd.maturity_date,
        )
        days_to_maturity = max(0, (fd.maturity_date - date_cls.today()).days)

        # Invested = sum of contributions (or principal if no contribution txns)
        txns = uow.transactions.list_by_asset(asset.id)
        invested = sum(abs(t.amount_inr / 100) for t in txns if t.type.value in OUTFLOW_TYPES)
        effective_invested = invested if invested > 0 else principal_inr

        # Taxable interest: formula-based (accrued - invested)
        # Fall back to summing INTEREST txns only if already posted (matured FDs)
        interest_txns = [t for t in txns if t.type.value == "INTEREST"]
        if interest_txns:
            taxable_interest = sum(abs(t.amount_inr / 100) for t in interest_txns)
        else:
            taxable_interest = max(0.0, accrued_today - effective_invested)

        return base.model_copy(update={
            "maturity_amount": maturity_amount,
            "accrued_value_today": accrued_today,
            "days_to_maturity": days_to_maturity,
            "taxable_interest": taxable_interest,
            "potential_tax_30pct": round(taxable_interest * 0.30, 2),
        })
```

Note: `super(ValuationBasedStrategy, self).compute(...)` skips ValuationBasedStrategy's compute (which would add the "no valuation" message for FDs with no Valuation rows) and calls the base `AssetReturnsStrategy.compute()` directly.

- [ ] **Step 3: Run new tests**

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py -v 2>&1 | grep -E "FAILED|PASSED|ERROR"
```

Expected: 0 failures.

- [ ] **Step 4: Run full suite**

```bash
cd backend && uv run pytest tests/unit/ 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/returns/strategies/asset_types/fd.py tests/unit/test_returns_strategies.py
git commit -m "fix: FD strategy — maturity-amount XIRR, formula taxable_interest, accrued/days_to_maturity fields"
```

---

## Task 5 — Fix RDStrategy: XIRR uses maturity_amount at maturity_date

**Files:**
- Modify: `backend/app/services/returns/strategies/asset_types/rd.py`
- Modify: `backend/tests/unit/test_returns_strategies.py`

### What needs fixing

Same issue as FD: base `compute()` terminal `(today, accrued_today)` is wrong. RD XIRR should use `(maturity_date_or_today, maturity_amount)`.

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_returns_strategies.py`:

```python
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
```

Run to confirm failure:

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py::test_rd_strategy_xirr_uses_maturity_amount -v
```

Expected: FAIL or passes with wrong XIRR.

- [ ] **Step 2: Implement in `rd.py`**

```python
# app/services/returns/strategies/asset_types/rd.py
from datetime import date as date_cls
from typing import Optional

from app.engine.fd_engine import compute_rd_maturity
from app.engine.returns import OUTFLOW_TYPES
from app.repositories.unit_of_work import UnitOfWork
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("RD")
class RDStrategy(ValuationBasedStrategy):

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        txns = uow.transactions.list_by_asset(asset.id)
        contributions = [abs(t.amount_inr / 100) for t in txns if t.type.value == "CONTRIBUTION"]
        return sum(contributions) if contributions else 0.0

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd = uow.fd.get_by_asset_id(asset.id)
        if fd is None:
            return None
        principal_inr = fd.principal_amount / 100.0
        total_months = round((fd.maturity_date - fd.start_date).days / 30.44)
        elapsed = round((date_cls.today() - fd.start_date).days / 30.44)
        elapsed = max(0, min(elapsed, total_months))
        return compute_rd_maturity(principal_inr, fd.interest_rate_pct, elapsed)

    def build_cashflows(self, asset, uow: UnitOfWork):
        """XIRR: contributions as outflows + maturity_amount as terminal at maturity_date."""
        fd = uow.fd.get_by_asset_id(asset.id)
        txns = uow.transactions.list_by_asset(asset.id)

        cashflows = [
            (t.date, -(t.amount_inr / 100))
            for t in txns
            if t.type.value in OUTFLOW_TYPES
        ]

        if fd is not None:
            principal_inr = fd.principal_amount / 100.0
            total_months = round((fd.maturity_date - fd.start_date).days / 30.44)
            maturity_amount = compute_rd_maturity(principal_inr, fd.interest_rate_pct, total_months)
            effective_end = fd.maturity_date if fd.maturity_date >= date_cls.today() else date_cls.today()
            cashflows.append((effective_end, -maturity_amount))

        return cashflows
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py -v 2>&1 | grep -E "FAILED|PASSED|ERROR"
```

Expected: 0 failures.

- [ ] **Step 4: Run full suite**

```bash
cd backend && uv run pytest tests/unit/ 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/returns/strategies/asset_types/rd.py tests/unit/test_returns_strategies.py
git commit -m "fix: RD strategy — maturity-amount terminal cashflow for XIRR"
```

---

## Task 6 — Fix EPFStrategy: XIRR cashflow excludes INTEREST accumulation

**Files:**
- Modify: `backend/app/services/returns/strategies/asset_types/epf.py`
- Modify: `backend/tests/unit/test_returns_strategies.py`

### What needs fixing

Default `build_cashflows` includes ALL non-excluded transactions including INTEREST.
For EPF, INTEREST accumulates inside the fund — the investor never receives it separately until withdrawal.
Including it as a negative terminal cashflow makes XIRR converge to a wrong rate.

Fix: override `build_cashflows` to include only CONTRIBUTION outflows; the base `compute()` appends the current_value as terminal (which already includes accumulated interest via `get_current_value`).

Also: `get_current_value` returns `0` when no contributions — old code returned `None`.

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_returns_strategies.py`:

```python
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


def test_epf_strategy_no_contributions_returns_none_current_value():
    from app.services.returns.strategies.asset_types.epf import EPFStrategy
    strategy = EPFStrategy()
    asset = _make_asset(asset_type="EPF")
    uow = _make_uow(transactions=[])
    result = strategy.get_current_value(asset, uow)
    assert result is None
```

Run to confirm failures:

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py::test_epf_strategy_xirr_excludes_interest_in_cashflows tests/unit/test_returns_strategies.py::test_epf_strategy_no_contributions_returns_none_current_value -v
```

Expected: both FAIL.

- [ ] **Step 2: Implement in `epf.py`**

```python
# app/services/returns/strategies/asset_types/epf.py
from typing import Optional

from app.engine.returns import OUTFLOW_TYPES
from app.repositories.unit_of_work import UnitOfWork
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("EPF")
class EPFStrategy(ValuationBasedStrategy):

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        txns = uow.transactions.list_by_asset(asset.id)
        contributions = [abs(t.amount_inr / 100) for t in txns if t.type.value == "CONTRIBUTION"]
        return sum(contributions) if contributions else 0.0

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        invested = self.get_invested_value(asset, uow)
        if not invested:
            return None   # no contributions — can't compute current value
        txns = uow.transactions.list_by_asset(asset.id)
        interest = sum(t.amount_inr / 100 for t in txns if t.type.value == "INTEREST")
        return round(invested + interest, 2)

    def build_cashflows(self, asset, uow: UnitOfWork):
        """
        XIRR cashflows: only CONTRIBUTION outflows.

        INTEREST accumulates inside the EPF account — it is NOT a cash inflow to the
        investor until withdrawal.  The terminal inflow (current_value = invested +
        interest) is appended by base.compute() so XIRR is still computed correctly.
        """
        txns = uow.transactions.list_by_asset(asset.id)
        return [
            (t.date, -(t.amount_inr / 100))
            for t in txns
            if t.type.value in OUTFLOW_TYPES
        ]
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/unit/test_returns_strategies.py -v 2>&1 | grep -E "FAILED|PASSED|ERROR"
```

Expected: 0 failures.

- [ ] **Step 4: Run full suite**

```bash
cd backend && uv run pytest tests/unit/ 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/returns/strategies/asset_types/epf.py tests/unit/test_returns_strategies.py
git commit -m "fix: EPF strategy — exclude INTEREST from XIRR cashflows, None current_value when no contributions"
```

---

## Final Verification

- [ ] **Run full unit and integration test suites**

```bash
cd backend && uv run pytest tests/ --tb=short 2>&1 | tail -30
```

Expected: 0 failures.

- [ ] **Smoke-test a STOCK_IN asset** (if server is running)

```bash
python cli.py list assets
# pick a STOCK_IN asset ID, e.g. 5
curl -s http://localhost:8000/returns/5 | python -m json.tool | grep -E "alltime_pnl|total_units|current_price|cagr|xirr"
```

Expected: all fields populated.

- [ ] **Smoke-test an FD asset**

```bash
# pick an FD asset ID
curl -s http://localhost:8000/returns/<fd_id> | python -m json.tool | grep -E "days_to_maturity|accrued_value_today|taxable_interest|maturity_amount|xirr"
```

Expected: all fields populated.

---

## Notes for Implementer

- `compute_gains_summary` in `lot_engine.py` expects `open_lots` as list of dicts with specific keys (`buy_date`, `buy_amount_inr`, `units_remaining`, `is_short_term`, `current_value`). Check the exact signature before calling.
- The negated sign convention in `build_cashflows` (`-(t.amount_inr / 100)`) means outflows (stored negative in DB) become positive, inflows become negative. `compute_xirr` handles this correctly since it only requires mixed signs.
- `_build_lots_sells` helper refactor in Task 3 eliminates the duplicated lot-building loop that currently appears in `get_invested_value`, `_compute_lots_data`, and `compute_lots`. Extract it cleanly to avoid a 4th copy.
- Do NOT modify `services/returns_service.py` (old file, kept for reference until deprecation).

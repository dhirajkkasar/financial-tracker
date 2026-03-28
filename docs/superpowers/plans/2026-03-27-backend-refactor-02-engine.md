# Backend Refactoring — Plan 2: Engine Improvements

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all asset-type hardcoding from the engine layer: parameterize `lot_engine.py` functions so they accept `stcg_days` rather than looking it up internally; replace the flat `get_tax_rate()` conditional with a `TaxRatePolicy` class driven by per-FY YAML config files; wrap the MF classifier in an injectable protocol.

**Architecture:** All changes are to pure functions in `engine/` — no DB, no HTTP. Engine has zero asset-type knowledge after this plan. The `_STCG_DAYS` dict stays in `lot_engine.py` as a deprecated compatibility shim used by `returns_service.py` until Plan 4 migrates it. `TaxRatePolicy` lives in `engine/tax_engine.py` alongside existing functions; `ISchemeClassifier` lives in `engine/mf_classifier.py`.

**Tech Stack:** Python 3.11+, PyYAML (`pyyaml` already in deps), pytest

**Execution order:** Independent — can run in parallel with Plan 1. Must complete before Plan 4 (strategies need parameterized lot engine and TaxRatePolicy).

**Git branch** Use git branch feature/refactor to commit code. Do not use main branch.

---

## File Map

**Modified:**
- `backend/app/engine/lot_engine.py` — add `stcg_days` parameter to `match_lots_fifo` and `compute_lot_unrealised`; keep `_STCG_DAYS` dict as shim
- `backend/app/engine/tax_engine.py` — add `TaxRate` dataclass + `TaxRatePolicy` class; keep existing functions
- `backend/app/engine/mf_classifier.py` — add `ISchemeClassifier` protocol + `DefaultSchemeClassifier` class
- `backend/tests/unit/test_lot_engine.py` — add parameterized tests
- `backend/tests/unit/test_tax_engine.py` — add TaxRatePolicy tests
- `backend/tests/unit/test_mf_classifier.py` — add protocol tests

**New:**
- `backend/app/config/tax_rates/2024-25.yaml`
- `backend/app/config/tax_rates/2025-26.yaml`
- `backend/app/config/__init__.py`

**Unchanged:** `returns_service.py` still passes `stcg_days` via the shim dict (Plan 4 replaces this with per-strategy ClassVar). All existing tests remain green.

---

## Task 1: Parameterize lot_engine.py — match_lots_fifo

**Files:**
- Modify: `backend/app/engine/lot_engine.py`
- Modify: `backend/tests/unit/test_lot_engine.py`

Current signature: `match_lots_fifo(lots, sells)` — looks up `stcg_days` internally via `_STCG_DAYS[asset_type]`.

Target signature: `match_lots_fifo(lots, sells, stcg_days: int)` — receives threshold as parameter.

- [ ] **Step 1: Read the current test to understand the pattern**

```bash
cd backend
uv run pytest tests/unit/test_lot_engine.py -v --collect-only
```

Note the existing test names. The new tests must be additive (do not break existing ones).

- [ ] **Step 2: Add a failing test for the new parameterized signature**

Open `backend/tests/unit/test_lot_engine.py` and append:

```python
# --- Tests for explicit stcg_days parameter ---

def test_match_lots_fifo_with_explicit_stcg_days_equity():
    """Parameterized stcg_days=365 produces same results as the old asset_type='STOCK_IN' lookup."""
    from datetime import date
    from app.engine.lot_engine import match_lots_fifo

    lots = [
        _make_lot("lot1", date(2023, 1, 1), units=10, buy_price=100.0),
    ]
    sells = [
        _make_sell(date(2023, 6, 1), units=5, amount_inr=600.0),  # 151 days — short-term at 365
    ]
    # New API: explicit stcg_days
    matches = match_lots_fifo(lots, sells, stcg_days=365)
    assert len(matches) == 1
    assert matches[0]["is_short_term"] is True


def test_match_lots_fifo_with_explicit_stcg_days_us_stock():
    """stcg_days=730 produces long-term for a 400-day hold."""
    from datetime import date
    from app.engine.lot_engine import match_lots_fifo

    lots = [
        _make_lot("lot1", date(2022, 1, 1), units=10, buy_price=200.0),
    ]
    sells = [
        _make_sell(date(2023, 4, 1), units=5, amount_inr=1200.0),  # 455 days — LT at 730
    ]
    matches = match_lots_fifo(lots, sells, stcg_days=730)
    assert len(matches) == 1
    assert matches[0]["is_short_term"] is False
```

> If `_make_lot` and `_make_sell` helpers do not exist in the test file, add these at the top of the file (before the existing tests):
>
> ```python
> from dataclasses import dataclass
> from datetime import date
> from typing import Optional
>
> @dataclass
> class _Lot:
>     lot_id: str
>     buy_date: date
>     units: float
>     buy_price_per_unit: float
>     buy_amount_inr: float
>     jan31_2018_price: Optional[float] = None
>
> @dataclass
> class _Sell:
>     date: date
>     units: float
>     amount_inr: float
>
> def _make_lot(lot_id, buy_date, units, buy_price):
>     return _Lot(lot_id=lot_id, buy_date=buy_date, units=units,
>                 buy_price_per_unit=buy_price, buy_amount_inr=units * buy_price)
>
> def _make_sell(sell_date, units, amount_inr):
>     return _Sell(date=sell_date, units=units, amount_inr=amount_inr)
> ```

- [ ] **Step 3: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_lot_engine.py::test_match_lots_fifo_with_explicit_stcg_days_equity -v
```

Expected: `TypeError: match_lots_fifo() takes 2 positional arguments but 3 were given`

- [ ] **Step 4: Update match_lots_fifo to accept stcg_days**

In `backend/app/engine/lot_engine.py`, find the `match_lots_fifo` function (around line 57) and update its signature. The function currently computes `is_short_term` internally using `_STCG_DAYS`. Find where it does that lookup and replace it with the parameter.

The current function signature is:
```python
def match_lots_fifo(lots: list, sells: list) -> list[dict]:
```

Change it to:
```python
def match_lots_fifo(lots: list, sells: list, stcg_days: int = 365) -> list[dict]:
```

Then find any internal reference to `_STCG_DAYS` or `asset_type` inside `match_lots_fifo` and replace with `stcg_days`. For example, find the line like:
```python
threshold = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
is_short_term = holding_days < threshold
```
And replace with:
```python
is_short_term = holding_days < stcg_days
```

- [ ] **Step 5: Run tests to verify new tests pass and no regressions**

```bash
cd backend
uv run pytest tests/unit/test_lot_engine.py -v
```

Expected: All tests pass including the two new ones.

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/engine/lot_engine.py tests/unit/test_lot_engine.py
git commit -m "feat(engine): parameterize match_lots_fifo with explicit stcg_days"
```

---

## Task 2: Parameterize lot_engine.py — compute_lot_unrealised

**Files:**
- Modify: `backend/app/engine/lot_engine.py`
- Modify: `backend/tests/unit/test_lot_engine.py`

Same pattern as Task 1: `compute_lot_unrealised` currently looks up threshold from a hardcoded dict or via `asset_type` string. Make it accept `stcg_days: int` as a parameter.

- [ ] **Step 1: Add failing test**

Append to `backend/tests/unit/test_lot_engine.py`:

```python
def test_compute_lot_unrealised_with_explicit_stcg_days():
    from datetime import date
    from app.engine.lot_engine import compute_lot_unrealised

    lot = _make_lot("lot1", date(2023, 1, 1), units=10, buy_price=100.0)
    result = compute_lot_unrealised(
        lot=lot,
        current_price=130.0,
        stcg_days=365,
        grandfathering_cutoff=None,
        as_of=date(2024, 1, 1),
    )
    assert result["unrealised_gain"] == pytest.approx(300.0)
    assert result["is_short_term"] is False  # 365 days exactly is NOT short term
    assert result["holding_days"] == 365
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_lot_engine.py::test_compute_lot_unrealised_with_explicit_stcg_days -v
```

Expected: `TypeError` — wrong arguments

- [ ] **Step 3: Read the current compute_lot_unrealised signature**

```bash
cd backend
grep -n "def compute_lot_unrealised" app/engine/lot_engine.py
```

Then read the function to understand its current signature and any internal threshold lookup.

- [ ] **Step 4: Update compute_lot_unrealised**

Update the function signature to:
```python
def compute_lot_unrealised(
    lot,
    current_price: float,
    stcg_days: int,
    grandfathering_cutoff,
    as_of: date,
) -> dict:
```

Remove any internal `_STCG_DAYS` lookup and use `stcg_days` parameter directly.

- [ ] **Step 5: Update internal callers of compute_lot_unrealised**

Search for all callers within `lot_engine.py` itself (e.g., inside `compute_gains_summary` or similar helpers) and pass through the `stcg_days` parameter they already have access to.

```bash
cd backend
grep -n "compute_lot_unrealised" app/engine/lot_engine.py
```

For each internal call, add `stcg_days=stcg_days` where `stcg_days` is already a parameter of the outer function.

- [ ] **Step 6: Update returns_service.py to pass stcg_days**

`returns_service.py` calls these engine functions with an asset_type. It should now compute the threshold itself and pass it:

```bash
cd backend
grep -n "compute_lot_unrealised\|match_lots_fifo" app/services/returns_service.py
```

For each call site in `returns_service.py`, add:
```python
from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS
# ...
stcg_days = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
matches = match_lots_fifo(lots, sells, stcg_days=stcg_days)
# and:
result = compute_lot_unrealised(lot, current_price, stcg_days=stcg_days, ...)
```

The `_STCG_DAYS` dict stays in `lot_engine.py` as a compatibility shim for now.

- [ ] **Step 7: Run all tests**

```bash
cd backend
uv run pytest -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
cd backend
git add app/engine/lot_engine.py app/services/returns_service.py tests/unit/test_lot_engine.py
git commit -m "feat(engine): parameterize compute_lot_unrealised with stcg_days; update returns_service callers"
```

---

## Task 3: Add TaxRate dataclass + TaxRatePolicy to tax_engine.py

**Files:**
- Create: `backend/app/config/__init__.py`
- Create: `backend/app/config/tax_rates/2024-25.yaml`
- Create: `backend/app/config/tax_rates/2025-26.yaml`
- Modify: `backend/app/engine/tax_engine.py`
- Modify: `backend/tests/unit/test_tax_engine.py`

- [ ] **Step 1: Write failing tests for TaxRatePolicy**

Open `backend/tests/unit/test_tax_engine.py` and append:

```python
import tempfile
import os
import yaml
import pytest
from pathlib import Path


@pytest.fixture
def temp_tax_config(tmp_path):
    """Create a minimal tax rate YAML for testing."""
    rates = {
        "STOCK_IN": {
            "stcg_rate_pct": 20.0,
            "stcg_is_slab": False,
            "ltcg_rate_pct": 12.5,
            "ltcg_is_slab": False,
            "ltcg_threshold_days": 365,
            "ltcg_exemption_inr": 125000.0,
            "is_exempt": False,
            "maturity_exempt": False,
        },
        "PPF": {
            "stcg_rate_pct": None,
            "stcg_is_slab": False,
            "ltcg_rate_pct": None,
            "ltcg_is_slab": False,
            "ltcg_threshold_days": None,
            "ltcg_exemption_inr": 0.0,
            "is_exempt": True,
            "maturity_exempt": False,
        },
        "FD": {
            "stcg_rate_pct": None,
            "stcg_is_slab": True,
            "ltcg_rate_pct": None,
            "ltcg_is_slab": True,
            "ltcg_threshold_days": None,
            "ltcg_exemption_inr": 0.0,
            "is_exempt": False,
            "maturity_exempt": False,
        },
    }
    fy_file = tmp_path / "2024-25.yaml"
    fy_file.write_text(yaml.dump(rates))
    return tmp_path


def test_tax_rate_policy_loads_stock_in(temp_tax_config):
    from app.engine.tax_engine import TaxRatePolicy

    policy = TaxRatePolicy(temp_tax_config)
    rate = policy.get_rate("2024-25", "STOCK_IN")
    assert rate.stcg_rate_pct == 20.0
    assert rate.ltcg_rate_pct == 12.5
    assert rate.ltcg_exemption_inr == 125000.0
    assert rate.is_exempt is False


def test_tax_rate_policy_loads_ppf_exempt(temp_tax_config):
    from app.engine.tax_engine import TaxRatePolicy

    policy = TaxRatePolicy(temp_tax_config)
    rate = policy.get_rate("2024-25", "PPF")
    assert rate.is_exempt is True


def test_tax_rate_policy_missing_fy_raises(temp_tax_config):
    from app.engine.tax_engine import TaxRatePolicy

    policy = TaxRatePolicy(temp_tax_config)
    with pytest.raises(ValueError, match="No tax rate config for FY"):
        policy.get_rate("2099-00", "STOCK_IN")


def test_tax_rate_policy_caches_file(temp_tax_config):
    from app.engine.tax_engine import TaxRatePolicy

    policy = TaxRatePolicy(temp_tax_config)
    rate1 = policy.get_rate("2024-25", "STOCK_IN")
    rate2 = policy.get_rate("2024-25", "STOCK_IN")
    assert rate1 is rate2  # same object from cache
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_tax_engine.py::test_tax_rate_policy_loads_stock_in -v
```

Expected: `ImportError: cannot import name 'TaxRatePolicy'`

- [ ] **Step 3: Create config directory and YAML files**

```bash
mkdir -p backend/app/config/tax_rates
touch backend/app/config/__init__.py
touch backend/app/config/tax_rates/__init__.py
```

Create `backend/app/config/tax_rates/2024-25.yaml`:

```yaml
# FY2024-25 tax rates — Backend Refactoring Plan 2
# Adding a new FY: copy this file, rename to YYYY-YY.yaml, update rates.
# stcg_rate_pct / ltcg_rate_pct: null means slab rate (unknown without tax bracket)
# is_exempt: true means EEE (PPF)
# maturity_exempt: true means exempt if held to maturity (SGB)

STOCK_IN:
  stcg_rate_pct: 20.0
  stcg_is_slab: false
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 365
  ltcg_exemption_inr: 125000.0
  is_exempt: false
  maturity_exempt: false

MF:
  stcg_rate_pct: 20.0
  stcg_is_slab: false
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 365
  ltcg_exemption_inr: 125000.0
  is_exempt: false
  maturity_exempt: false

STOCK_US:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 730
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

RSU:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 730
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

GOLD:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 1095
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

SGB:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 1095
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: true

REAL_ESTATE:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 730
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

FD:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: null
  ltcg_is_slab: true
  ltcg_threshold_days: null
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

RD:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: null
  ltcg_is_slab: true
  ltcg_threshold_days: null
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

EPF:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: null
  ltcg_is_slab: true
  ltcg_threshold_days: null
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

PPF:
  stcg_rate_pct: null
  stcg_is_slab: false
  ltcg_rate_pct: null
  ltcg_is_slab: false
  ltcg_threshold_days: null
  ltcg_exemption_inr: 0.0
  is_exempt: true
  maturity_exempt: false

NPS:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 365
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false
```

Create `backend/app/config/tax_rates/2025-26.yaml`:

```yaml
# FY2025-26 tax rates
# Copy of 2024-25 — update when Finance Bill 2025 is passed.
# stcg_rate_pct / ltcg_rate_pct: null means slab rate

STOCK_IN:
  stcg_rate_pct: 20.0
  stcg_is_slab: false
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 365
  ltcg_exemption_inr: 125000.0
  is_exempt: false
  maturity_exempt: false

MF:
  stcg_rate_pct: 20.0
  stcg_is_slab: false
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 365
  ltcg_exemption_inr: 125000.0
  is_exempt: false
  maturity_exempt: false

STOCK_US:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 730
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

RSU:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 730
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

GOLD:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 1095
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

SGB:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 1095
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: true

REAL_ESTATE:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 730
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

FD:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: null
  ltcg_is_slab: true
  ltcg_threshold_days: null
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

RD:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: null
  ltcg_is_slab: true
  ltcg_threshold_days: null
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

EPF:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: null
  ltcg_is_slab: true
  ltcg_threshold_days: null
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false

PPF:
  stcg_rate_pct: null
  stcg_is_slab: false
  ltcg_rate_pct: null
  ltcg_is_slab: false
  ltcg_threshold_days: null
  ltcg_exemption_inr: 0.0
  is_exempt: true
  maturity_exempt: false

NPS:
  stcg_rate_pct: null
  stcg_is_slab: true
  ltcg_rate_pct: 12.5
  ltcg_is_slab: false
  ltcg_threshold_days: 365
  ltcg_exemption_inr: 0.0
  is_exempt: false
  maturity_exempt: false
```

- [ ] **Step 4: Add TaxRate dataclass and TaxRatePolicy to tax_engine.py**

At the top of `backend/app/engine/tax_engine.py`, after the existing imports, add:

```python
import yaml
from dataclasses import dataclass
from pathlib import Path
```

Then append after the existing constants (before the function definitions), add:

```python
# ---------------------------------------------------------------------------
# TaxRate dataclass + TaxRatePolicy — config-driven rate lookup (Section 10)
# ---------------------------------------------------------------------------

@dataclass
class TaxRate:
    """Tax rate descriptor for one asset type in one FY."""
    stcg_rate_pct: float | None      # None = slab rate
    stcg_is_slab: bool
    ltcg_rate_pct: float | None
    ltcg_is_slab: bool
    ltcg_threshold_days: int | None  # None = no LT distinction
    ltcg_exemption_inr: float
    is_exempt: bool                  # EEE (PPF)
    maturity_exempt: bool = False    # SGB held to maturity


class TaxRatePolicy:
    """
    Loads per-FY YAML config files from a directory and returns TaxRate objects.

    Adding a new FY = drop a YYYY-YY.yaml file into config_dir. Zero code changes.

    Usage:
        policy = TaxRatePolicy(Path("app/config/tax_rates"))
        rate = policy.get_rate("2024-25", "STOCK_IN")
    """

    def __init__(self, config_dir: Path):
        self._config_dir = config_dir
        self._cache: dict[str, dict[str, TaxRate]] = {}

    def get_rate(self, fy: str, asset_type: str) -> TaxRate:
        if fy not in self._cache:
            path = self._config_dir / f"{fy}.yaml"
            if not path.exists():
                raise ValueError(
                    f"No tax rate config for FY {fy!r}. "
                    f"Expected file: {path}"
                )
            with open(path) as f:
                raw_data: dict = yaml.safe_load(f)
            self._cache[fy] = {
                at: TaxRate(**fields) for at, fields in raw_data.items()
            }
        rates = self._cache[fy]
        if asset_type not in rates:
            raise ValueError(
                f"No tax rate for asset_type={asset_type!r} in FY {fy!r}. "
                f"Available: {sorted(rates.keys())}"
            )
        return rates[asset_type]
```

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_tax_engine.py -v
```

Expected: All tests pass, including the 4 new TaxRatePolicy tests.

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/engine/tax_engine.py app/config/ tests/unit/test_tax_engine.py
git commit -m "feat(engine): add TaxRate dataclass and TaxRatePolicy with per-FY YAML config"
```

---

## Task 4: Fix tax_engine.classify_holding to not import _STCG_DAYS

**Files:**
- Modify: `backend/app/engine/tax_engine.py`
- Modify: `backend/tests/unit/test_tax_engine.py`

Currently `classify_holding` imports `_STCG_DAYS` from `lot_engine` at call time. After Plan 2, the engine should have zero cross-module coupling for type-specific lookups.

- [ ] **Step 1: Add failing test**

Append to `backend/tests/unit/test_tax_engine.py`:

```python
def test_classify_holding_with_explicit_stcg_days():
    from datetime import date
    from app.engine.tax_engine import classify_holding

    result = classify_holding(
        buy_date=date(2023, 1, 1),
        sell_date=date(2023, 6, 1),
        stcg_days=365,
    )
    assert result["is_short_term"] is True
    assert result["holding_days"] == 151


def test_classify_holding_long_term_explicit():
    from datetime import date
    from app.engine.tax_engine import classify_holding

    result = classify_holding(
        buy_date=date(2022, 1, 1),
        sell_date=date(2023, 6, 1),
        stcg_days=365,
    )
    assert result["is_short_term"] is False
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_tax_engine.py::test_classify_holding_with_explicit_stcg_days -v
```

Expected: `TypeError` — unexpected keyword argument `stcg_days`

- [ ] **Step 3: Update classify_holding in tax_engine.py**

Find the current `classify_holding` function:

```python
def classify_holding(asset_type: str, buy_date: date, sell_date: date) -> dict:
    from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS
    holding_days = (sell_date - buy_date).days
    threshold = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
    return {
        "holding_days": holding_days,
        "is_short_term": holding_days < threshold,
    }
```

Replace it with:

```python
def classify_holding(
    buy_date: date,
    sell_date: date,
    stcg_days: int,
    asset_type: Optional[str] = None,  # kept for any legacy callers; ignored
) -> dict:
    """
    Return holding_days and is_short_term.

    Pass stcg_days explicitly (from TaxRatePolicy or strategy ClassVar).
    asset_type parameter is deprecated and ignored.
    """
    holding_days = (sell_date - buy_date).days
    return {
        "holding_days": holding_days,
        "is_short_term": holding_days < stcg_days,
    }
```

- [ ] **Step 4: Update compute_fy_realised_gains which calls classify_holding**

Find where `compute_fy_realised_gains` calls `classify_holding`:

```python
classification = classify_holding(asset_type, buy_date, sell_date)
```

This call passes `asset_type` as the first positional arg. Since `classify_holding` now expects `buy_date` first, update this call:

```python
from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS
stcg_days = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
classification = classify_holding(buy_date=buy_date, sell_date=sell_date, stcg_days=stcg_days)
```

- [ ] **Step 5: Update tax_service.py callers if any**

```bash
cd backend
grep -rn "classify_holding" app/
```

For each caller, update to pass `stcg_days` explicitly. If `asset_type` was being passed as the first positional arg, replace with keyword args:
```python
from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS
stcg_days = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
result = classify_holding(buy_date=buy_date, sell_date=sell_date, stcg_days=stcg_days)
```

- [ ] **Step 6: Run all tests**

```bash
cd backend
uv run pytest --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/engine/tax_engine.py app/services/
git commit -m "feat(engine): remove asset_type coupling from classify_holding; accept stcg_days directly"
```

---

## Task 5: Add ISchemeClassifier to mf_classifier.py

**Files:**
- Modify: `backend/app/engine/mf_classifier.py`
- Modify: `backend/tests/unit/test_mf_classifier.py`

- [ ] **Step 1: Add failing test**

Open `backend/tests/unit/test_mf_classifier.py` and append:

```python
def test_default_scheme_classifier_equity():
    from app.engine.mf_classifier import DefaultSchemeClassifier
    classifier = DefaultSchemeClassifier()
    result = classifier.classify("Large Cap Fund - Growth")
    assert result.value in ("EQUITY", "MIXED", "DEBT")  # not None


def test_default_scheme_classifier_debt():
    from app.engine.mf_classifier import DefaultSchemeClassifier
    classifier = DefaultSchemeClassifier()
    from app.models.asset import AssetClass
    result = classifier.classify("Liquid Fund - Direct Growth")
    assert result == AssetClass.DEBT


def test_ischeme_classifier_protocol():
    """Any class with a classify() method satisfies ISchemeClassifier."""
    from app.engine.mf_classifier import ISchemeClassifier, DefaultSchemeClassifier
    assert isinstance(DefaultSchemeClassifier(), ISchemeClassifier)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_mf_classifier.py::test_default_scheme_classifier_equity -v
```

Expected: `ImportError: cannot import name 'DefaultSchemeClassifier'`

- [ ] **Step 3: Read current mf_classifier.py**

```bash
cd backend
cat app/engine/mf_classifier.py
```

Note the existing `classify_mf(scheme_category: str) -> AssetClass` function.

- [ ] **Step 4: Add ISchemeClassifier and DefaultSchemeClassifier**

Append to the END of `backend/app/engine/mf_classifier.py`:

```python
# ---------------------------------------------------------------------------
# ISchemeClassifier protocol + DefaultSchemeClassifier wrapper
# ---------------------------------------------------------------------------
from typing import Protocol, runtime_checkable


@runtime_checkable
class ISchemeClassifier(Protocol):
    """Classifies an MF scheme category string into an AssetClass."""
    def classify(self, scheme_category: str) -> "AssetClass": ...


class DefaultSchemeClassifier:
    """Wraps the module-level classify_mf function for DI injection."""

    def classify(self, scheme_category: str) -> "AssetClass":
        return classify_mf(scheme_category)
```

> Note: `AssetClass` is already imported at the top of `mf_classifier.py`. If not, add `from app.models.asset import AssetClass` at the top.

- [ ] **Step 5: Run all tests**

```bash
cd backend
uv run pytest tests/unit/test_mf_classifier.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Run full suite**

```bash
cd backend
uv run pytest --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/engine/mf_classifier.py app/engine/tax_engine.py app/config/ tests/unit/test_mf_classifier.py
git commit -m "feat(engine): add ISchemeClassifier protocol + DefaultSchemeClassifier; add TaxRatePolicy YAML configs"
```

---

## Task 6: Verify engine coverage targets

- [ ] **Step 1: Run coverage report for engine/**

```bash
cd backend
uv run pytest tests/unit/ --cov=app/engine --cov-report=term-missing -q
```

Expected: `app/engine/` overall coverage ≥ 90%. If any line is uncovered, add a test.

Example: if `TaxRatePolicy.get_rate` when `asset_type` is missing shows as uncovered:

```python
def test_tax_rate_policy_missing_asset_type(temp_tax_config):
    from app.engine.tax_engine import TaxRatePolicy
    policy = TaxRatePolicy(temp_tax_config)
    with pytest.raises(ValueError, match="No tax rate for asset_type"):
        policy.get_rate("2024-25", "UNKNOWN_TYPE")
```

- [ ] **Step 2: Final commit if coverage tests added**

```bash
cd backend
git add tests/unit/test_tax_engine.py tests/unit/test_lot_engine.py tests/unit/test_mf_classifier.py
git commit -m "test(engine): add coverage tests to reach 90% engine coverage target"
```

---

## What's next

- **Plan 1 (Foundation)** — if not yet done, start it (required for Plans 3, 4)
- **Plan 4 (Services)** — uses parameterized lot engine and TaxRatePolicy; each strategy subclass will declare `stcg_days: ClassVar[int]` and pass it to `match_lots_fifo`

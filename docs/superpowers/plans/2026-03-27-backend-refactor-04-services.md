# Backend Refactoring — Plan 4: Services & API Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the Strategy pattern to the Returns service (one leaf class per asset type, 3-line files for simple cases); improve the Price service with self-registering fetchers that declare their own staleness threshold; clean up the API layer so no route calls a repository directly; and remove `db.commit()` from all repositories now that all services use `UnitOfWork`.

**Architecture:** `AssetReturnsStrategy` ABC with template method; `MarketBasedStrategy` and `ValuationBasedStrategy` as intermediate nodes; thin 3-line leaf classes for each asset type; `DefaultReturnsStrategyRegistry` for dispatch; thin `ReturnsService` coordinator; `BasePriceFetcher` ABC with `@register_fetcher` decorator; `AssetService` and `TransactionService` wrapping the repos to fix direct repo access in routes; `db.commit()` removed from all repos after all callers use UoW.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, pytest

**Prerequisites:** Plans 1, 2, and 3 must be complete.

**Git branch** Use git branch feature/refactor to commit code. Do not use main branch.
---

## File Map

**New files:**
- `backend/app/services/returns/__init__.py`
- `backend/app/services/returns/strategies/__init__.py`
- `backend/app/services/returns/strategies/base.py`
- `backend/app/services/returns/strategies/market_based.py`
- `backend/app/services/returns/strategies/valuation_based.py`
- `backend/app/services/returns/strategies/registry.py`
- `backend/app/services/returns/strategies/asset_types/stock_in.py`
- `backend/app/services/returns/strategies/asset_types/stock_us.py`
- `backend/app/services/returns/strategies/asset_types/rsu.py`
- `backend/app/services/returns/strategies/asset_types/mf.py`
- `backend/app/services/returns/strategies/asset_types/nps.py`
- `backend/app/services/returns/strategies/asset_types/gold.py`
- `backend/app/services/returns/strategies/asset_types/sgb.py`
- `backend/app/services/returns/strategies/asset_types/fd.py`
- `backend/app/services/returns/strategies/asset_types/rd.py`
- `backend/app/services/returns/strategies/asset_types/ppf.py`
- `backend/app/services/returns/strategies/asset_types/real_estate.py`
- `backend/app/services/returns/strategies/asset_types/epf.py`
- `backend/app/services/returns/returns_service.py`
- `backend/app/services/asset_service.py`
- `backend/app/services/transaction_service.py`
- `backend/tests/unit/test_returns_strategies.py`
- `backend/tests/unit/test_price_fetchers.py`

**Modified:**
- `backend/app/services/price_feed.py` — add `BasePriceFetcher` ABC + `@register_fetcher` decorator
- `backend/app/api/assets.py` — use `AssetService` via `Depends`
- `backend/app/api/transactions.py` — use `TransactionService` via `Depends`
- `backend/app/api/returns.py` — use new `ReturnsService` via `Depends`
- `backend/app/api/dependencies.py` — add all new service factories
- All repositories — remove `db.commit()` calls (final step)

---

## Task 1: Create AssetReturnsStrategy base + registry

**Files:**
- Create: `backend/app/services/returns/strategies/base.py`
- Create: `backend/app/services/returns/strategies/registry.py`
- Create: `backend/app/services/returns/__init__.py`
- Create: `backend/app/services/returns/strategies/__init__.py`
- Test: `backend/tests/unit/test_returns_strategies.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/unit/test_returns_strategies.py
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


def _make_uow(transactions=None, price=None, valuations=None):
    uow = MagicMock()
    uow.transactions.list_by_asset.return_value = transactions or []
    uow.price_cache.get_by_asset_id.return_value = price
    uow.valuations.list_by_asset.return_value = valuations or []
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
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_returns_strategies.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create services/returns/__init__.py and strategies/__init__.py**

```python
# backend/app/services/returns/__init__.py
# backend/app/services/returns/strategies/__init__.py
```

(Both empty.)

- [ ] **Step 4: Create strategies/base.py**

```python
# backend/app/services/returns/strategies/base.py
"""
AssetReturnsStrategy — template method pattern.

compute() orchestrates the calculation. Subclasses override only the hooks
that differ from the default. This keeps each leaf class to ~3 lines.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import ClassVar, Optional

from app.engine.returns import (
    compute_xirr, compute_cagr, compute_absolute_return,
    OUTFLOW_TYPES, INFLOW_TYPES, EXCLUDED_TYPES,
)
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse

# Registry for @register_strategy decorator
_STRATEGY_REGISTRY: dict[str, type["AssetReturnsStrategy"]] = {}


def register_strategy(asset_type: str):
    """Class decorator: register a strategy class for an asset type string."""
    def decorator(cls):
        _STRATEGY_REGISTRY[asset_type] = cls
        return cls
    return decorator


class AssetReturnsStrategy(ABC):
    """
    Template method: compute() orchestrates, hooks are overridden by subclasses.

    Default implementations:
        get_invested_value() → sum of outflow transaction amounts
        build_cashflows()    → standard inflow/outflow list for XIRR
        compute_lots()       → [] (not supported; override in MarketBasedStrategy)
    """

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        invested = self.get_invested_value(asset, uow)
        current = self.get_current_value(asset, uow)
        cashflows = self.build_cashflows(asset, uow)
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

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """Default: sum of outflow transaction amounts (in INR, converted from paise)."""
        txns = uow.transactions.list_by_asset(asset.id)
        outflows = [abs(t.amount_inr / 100) for t in txns if t.type.value in OUTFLOW_TYPES]
        return sum(outflows) if outflows else 0.0

    @abstractmethod
    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """Must be implemented by each strategy."""
        ...

    def build_cashflows(self, asset, uow: UnitOfWork) -> list[tuple[date, float]]:
        """Default: standard signed cashflows for XIRR computation."""
        txns = uow.transactions.list_by_asset(asset.id)
        cashflows = []
        for t in txns:
            if t.type.value in EXCLUDED_TYPES:
                continue
            amount_inr = t.amount_inr / 100  # paise → INR
            cashflows.append((t.date, -amount_inr))  # negative = outflow for XIRR
        return cashflows

    def compute_lots(self, asset, uow: UnitOfWork) -> list:
        """Default: lots not supported. Override in MarketBasedStrategy."""
        return []
```

- [ ] **Step 5: Create strategies/registry.py**

```python
# backend/app/services/returns/strategies/registry.py
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.services.returns.strategies.base import AssetReturnsStrategy


class IReturnsStrategyRegistry(Protocol):
    def get(self, asset_type: str) -> "AssetReturnsStrategy": ...


class DefaultReturnsStrategyRegistry:
    """
    Looks up the registered strategy for an asset type string.

    Importing all strategy modules triggers @register_strategy decorators,
    which populate _STRATEGY_REGISTRY. We import them lazily on first get().
    """

    def __init__(self):
        self._loaded = False
        self._map: dict[str, "AssetReturnsStrategy"] = {}

    def _ensure_loaded(self):
        if self._loaded:
            return
        # Import all strategy modules to trigger @register_strategy decorators
        import app.services.returns.strategies.asset_types.stock_in      # noqa: F401
        import app.services.returns.strategies.asset_types.stock_us      # noqa: F401
        import app.services.returns.strategies.asset_types.rsu           # noqa: F401
        import app.services.returns.strategies.asset_types.mf            # noqa: F401
        import app.services.returns.strategies.asset_types.nps           # noqa: F401
        import app.services.returns.strategies.asset_types.gold          # noqa: F401
        import app.services.returns.strategies.asset_types.sgb           # noqa: F401
        import app.services.returns.strategies.asset_types.fd            # noqa: F401
        import app.services.returns.strategies.asset_types.rd            # noqa: F401
        import app.services.returns.strategies.asset_types.ppf           # noqa: F401
        import app.services.returns.strategies.asset_types.real_estate   # noqa: F401
        import app.services.returns.strategies.asset_types.epf           # noqa: F401

        from app.services.returns.strategies.base import _STRATEGY_REGISTRY
        self._map = {at: cls() for at, cls in _STRATEGY_REGISTRY.items()}
        self._loaded = True

    def get(self, asset_type: str) -> "AssetReturnsStrategy":
        self._ensure_loaded()
        strategy = self._map.get(asset_type)
        if strategy is None:
            raise ValueError(
                f"No returns strategy for asset_type={asset_type!r}. "
                f"Registered: {sorted(self._map.keys())}"
            )
        return strategy
```

- [ ] **Step 6: Run tests (will fail until leaf classes exist)**

```bash
cd backend
uv run pytest tests/unit/test_returns_strategies.py::test_strategy_registry_raises_for_unknown_type -v
```

Expected: Fails with import error for asset_types module — that's expected at this stage.

- [ ] **Step 7: Commit base + registry**

```bash
cd backend
git add app/services/returns/ tests/unit/test_returns_strategies.py
git commit -m "feat(returns): add AssetReturnsStrategy ABC, @register_strategy, DefaultReturnsStrategyRegistry"
```

---

## Task 2: Create MarketBasedStrategy and ValuationBasedStrategy

**Files:**
- Create: `backend/app/services/returns/strategies/market_based.py`
- Create: `backend/app/services/returns/strategies/valuation_based.py`
- Create: `backend/app/services/returns/strategies/asset_types/__init__.py`

- [ ] **Step 1: Create market_based.py**

```python
# backend/app/services/returns/strategies/market_based.py
"""
MarketBasedStrategy — current value = units × price_cache NAV.

Subclasses declare stcg_days: ClassVar[int] and override only what's needed.
"""
from __future__ import annotations

from typing import ClassVar, Optional

from app.engine.lot_engine import (
    match_lots_fifo,
    compute_gains_summary,
    compute_lot_unrealised,
    GRANDFATHERING_CUTOFF,
)
from app.engine.returns import UNIT_ADD_TYPES, UNIT_SUB_TYPES
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse, LotComputedResponse
from app.services.returns.strategies.base import AssetReturnsStrategy
from datetime import date


class MarketBasedStrategy(AssetReturnsStrategy):
    """
    Intermediate: get_current_value = units × price_cache NAV.

    Subclasses must declare:
        stcg_days: ClassVar[int]

    Subclasses may override:
        get_invested_value()   — e.g. StockUSStrategy for USD→INR at vest
        build_cashflows()      — e.g. RSUStrategy for VEST unit calc
        get_current_value()    — e.g. MFStrategy for CAS snapshot
    """
    stcg_days: ClassVar[int]  # must be set by each leaf class

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """units × latest price_cache NAV, converted from paise to INR."""
        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        if price_entry is None or price_entry.price_inr is None:
            return None

        txns = uow.transactions.list_by_asset(asset.id)
        total_units = 0.0
        for t in txns:
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            units = t.units or 0.0
            if ttype in UNIT_ADD_TYPES:
                total_units += units
            elif ttype in UNIT_SUB_TYPES:
                total_units -= units

        price_inr = price_entry.price_inr / 100  # paise → INR
        return round(total_units * price_inr, 2)

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        """Override to include lot-based gain breakdown and price metadata."""
        base = super().compute(asset, uow)

        # Add lot gains
        lots_data = self._compute_lots_data(asset, uow)
        st_unrealised = sum(l["unrealised_gain"] for l in lots_data if not l["is_short_term"] is False and l.get("is_short_term"))
        lt_unrealised = sum(l["unrealised_gain"] for l in lots_data if l.get("is_short_term") is False)

        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        return AssetReturnsResponse(
            **base.model_dump(),
            st_unrealised_gain=st_unrealised if lots_data else None,
            lt_unrealised_gain=lt_unrealised if lots_data else None,
            price_is_stale=price_entry.is_stale if price_entry else None,
            price_fetched_at=price_entry.fetched_at.isoformat() if price_entry and price_entry.fetched_at else None,
        )

    def compute_lots(self, asset, uow: UnitOfWork) -> list[LotComputedResponse]:
        lots_data = self._compute_lots_data(asset, uow)
        return [
            LotComputedResponse(
                lot_id=l["lot_id"],
                buy_date=l["buy_date"],
                units=l["units"],
                buy_price_per_unit=l["buy_price_per_unit"],
                buy_amount_inr=l["buy_amount_inr"],
                current_price=l.get("current_price", 0.0),
                current_value=l.get("current_value", 0.0),
                holding_days=l["holding_days"],
                is_short_term=l["is_short_term"],
                unrealised_gain=l["unrealised_gain"],
                unrealised_gain_pct=l.get("unrealised_gain_pct", 0.0),
            )
            for l in lots_data
        ]

    def _compute_lots_data(self, asset, uow: UnitOfWork) -> list[dict]:
        """Raw lot dicts from lot_engine for this asset."""
        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        if price_entry is None:
            return []
        current_price = price_entry.price_inr / 100

        txns = uow.transactions.list_by_asset(asset.id)
        as_of = date.today()
        result = []
        for t in txns:
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            if ttype not in UNIT_ADD_TYPES:
                continue
            lot_data = compute_lot_unrealised(
                lot=t,
                current_price=current_price,
                stcg_days=self.stcg_days,
                grandfathering_cutoff=GRANDFATHERING_CUTOFF,
                as_of=as_of,
            )
            result.append(lot_data)
        return result
```

- [ ] **Step 2: Create valuation_based.py**

```python
# backend/app/services/returns/strategies/valuation_based.py
"""
ValuationBasedStrategy — current_value = latest Valuation entry (manual passbook).

Used for PPF and REAL_ESTATE. Subclasses override get_current_value() for FD/RD.
"""
from __future__ import annotations

from typing import Optional

from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import AssetReturnsStrategy


class ValuationBasedStrategy(AssetReturnsStrategy):
    """
    Intermediate: current_value = latest Valuation.value_inr.

    If no Valuation exists, current_value is None and xirr is None.
    """

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        valuations = uow.valuations.list_by_asset(asset.id)
        if not valuations:
            return None
        latest = sorted(valuations, key=lambda v: v.date, reverse=True)[0]
        return latest.value_inr / 100  # paise → INR

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        base = super().compute(asset, uow)
        if base.current_value is None:
            return AssetReturnsResponse(
                **base.model_dump(),
                message="No valuation entry found. Add one via /assets/{id}/valuations.",
            )
        return base
```

- [ ] **Step 3: Create asset_types/__init__.py**

```python
# backend/app/services/returns/strategies/asset_types/__init__.py
```

- [ ] **Step 4: Commit intermediate strategies**

```bash
cd backend
git add app/services/returns/strategies/
git commit -m "feat(returns): add MarketBasedStrategy and ValuationBasedStrategy intermediate classes"
```

---

## Task 3: Create all leaf strategy classes

**Files:** Create each of the 12 asset-type files.

- [ ] **Step 1: Create stock_in.py**

```python
# backend/app/services/returns/strategies/asset_types/stock_in.py
from typing import ClassVar
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("STOCK_IN")
class StockINStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 365
```

- [ ] **Step 2: Create stock_us.py**

```python
# backend/app/services/returns/strategies/asset_types/stock_us.py
from typing import ClassVar
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("STOCK_US")
class StockUSStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 730
```

- [ ] **Step 3: Create rsu.py**

```python
# backend/app/services/returns/strategies/asset_types/rsu.py
from typing import ClassVar
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("RSU")
class RSUStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 730
```

- [ ] **Step 4: Create nps.py**

```python
# backend/app/services/returns/strategies/asset_types/nps.py
from typing import ClassVar
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("NPS")
class NPSStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 365
```

- [ ] **Step 5: Create gold.py**

```python
# backend/app/services/returns/strategies/asset_types/gold.py
from typing import ClassVar
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("GOLD")
class GoldStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 1095
```

- [ ] **Step 6: Create sgb.py**

```python
# backend/app/services/returns/strategies/asset_types/sgb.py
from typing import ClassVar
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy


@register_strategy("SGB")
class SGBStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 1095
```

- [ ] **Step 7: Create mf.py**

```python
# backend/app/services/returns/strategies/asset_types/mf.py
"""
MFStrategy — uses CAS snapshot as source of truth for current value.

Snapshot < 30 days old → use snapshot.market_value directly.
Snapshot ≥ 30 days old → snapshot.closing_units × latest price_cache NAV.
"""
from typing import ClassVar, Optional
from datetime import date, timedelta
from app.repositories.unit_of_work import UnitOfWork
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.market_based import MarketBasedStrategy
from app.middleware.error_handler import ValidationError


SNAPSHOT_STALE_DAYS = 30


@register_strategy("MF")
class MFStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 365

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        snap = uow.cas_snapshots.get_latest_by_asset_id(asset.id)
        if snap is None:
            raise ValidationError(
                f"MF asset '{asset.name}' has no CAS snapshot. "
                "Import a CAS PDF to initialise holdings."
            )
        today = date.today()
        snap_age = (today - snap.date).days
        if snap_age < SNAPSHOT_STALE_DAYS:
            return snap.market_value_inr / 100  # paise → INR
        # Stale snapshot: recompute using latest NAV
        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        if price_entry is None:
            return snap.market_value_inr / 100  # best guess
        nav = price_entry.price_inr / 100
        return round(snap.closing_units * nav, 2)
```

- [ ] **Step 8: Create fd.py**

```python
# backend/app/services/returns/strategies/asset_types/fd.py
"""
FDStrategy — current_value = fd_engine formula (not latest valuation).
"""
from typing import Optional
from app.engine.fd_engine import compute_fd_current_value
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("FD")
class FDStrategy(ValuationBasedStrategy):

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail is None:
            return None
        result = compute_fd_current_value(fd_detail)
        return result.get("accrued_value_today")

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        base = super().compute(asset, uow)
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail:
            from app.engine.fd_engine import compute_fd_maturity
            maturity = compute_fd_maturity(fd_detail)
            txns = uow.transactions.list_by_asset(asset.id)
            interest_txns = [t for t in txns if t.type.value == "INTEREST"]
            taxable_interest = sum(abs(t.amount_inr / 100) for t in interest_txns)
            return AssetReturnsResponse(
                **base.model_dump(),
                maturity_amount=maturity.get("maturity_amount"),
                taxable_interest=taxable_interest,
                potential_tax_30pct=round(taxable_interest * 0.30, 2),
            )
        return base
```

- [ ] **Step 9: Create rd.py**

```python
# backend/app/services/returns/strategies/asset_types/rd.py
"""
RDStrategy — invested = sum of monthly installments (CONTRIBUTION txns),
             current_value = rd formula.
"""
from typing import Optional
from app.engine.fd_engine import compute_rd_maturity, compute_fd_current_value
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
        fd_detail = uow.fd.get_by_asset_id(asset.id)
        if fd_detail is None:
            return None
        result = compute_fd_current_value(fd_detail)
        return result.get("accrued_value_today")
```

- [ ] **Step 10: Create ppf.py**

```python
# backend/app/services/returns/strategies/asset_types/ppf.py
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("PPF")
class PPFStrategy(ValuationBasedStrategy):
    pass  # Default ValuationBasedStrategy behavior is correct for PPF
```

- [ ] **Step 11: Create real_estate.py**

```python
# backend/app/services/returns/strategies/asset_types/real_estate.py
from app.services.returns.strategies.base import register_strategy
from app.services.returns.strategies.valuation_based import ValuationBasedStrategy


@register_strategy("REAL_ESTATE")
class RealEstateStrategy(ValuationBasedStrategy):
    pass  # Default ValuationBasedStrategy behavior is correct
```

- [ ] **Step 12: Create epf.py**

```python
# backend/app/services/returns/strategies/asset_types/epf.py
"""
EPFStrategy — invested = sum of all CONTRIBUTION outflows (employee + employer + EPS).
              current_value = invested + sum of all INTEREST inflows − TDS.
"""
from typing import Optional
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
        txns = uow.transactions.list_by_asset(asset.id)
        interest = sum(t.amount_inr / 100 for t in txns if t.type.value == "INTEREST")
        return round(invested + interest, 2)
```

- [ ] **Step 13: Run all strategy tests**

```bash
cd backend
uv run pytest tests/unit/test_returns_strategies.py -v
```

Expected: All tests pass.

- [ ] **Step 14: Commit all leaf classes**

```bash
cd backend
git add app/services/returns/strategies/asset_types/
git commit -m "feat(returns): add all 12 leaf strategy classes (3-liner each where possible)"
```

---

## Task 4: Create thin ReturnsService

**Files:**
- Create: `backend/app/services/returns/returns_service.py`
- Modify: `backend/tests/unit/test_returns_strategies.py`

- [ ] **Step 1: Add test for ReturnsService**

Append to `backend/tests/unit/test_returns_strategies.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_returns_strategies.py::test_returns_service_get_asset_returns_dispatches_to_strategy -v
```

Expected: `ImportError`

- [ ] **Step 3: Create services/returns/returns_service.py**

```python
# backend/app/services/returns/returns_service.py
"""
ReturnsService — thin coordinator. Delegates all computation to the strategy registry.
"""
from __future__ import annotations

from typing import Optional

from app.middleware.error_handler import NotFoundError
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory
from app.schemas.responses.common import PaginatedResponse
from app.schemas.responses.returns import AssetReturnsResponse, LotComputedResponse, LotsPageResponse
from app.services.returns.strategies.registry import IReturnsStrategyRegistry


class ReturnsService:
    def __init__(
        self,
        uow_factory: IUnitOfWorkFactory,
        strategy_registry: IReturnsStrategyRegistry,
    ):
        self._uow_factory = uow_factory
        self._registry = strategy_registry

    def get_asset_returns(self, asset_id: int) -> AssetReturnsResponse:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            strategy = self._registry.get(asset.asset_type.value)
            return strategy.compute(asset, uow)

    def get_all_returns(self) -> list[AssetReturnsResponse]:
        with self._uow_factory() as uow:
            assets = uow.assets.list(active=None)
            results = []
            for asset in assets:
                try:
                    strategy = self._registry.get(asset.asset_type.value)
                    results.append(strategy.compute(asset, uow))
                except Exception:
                    # Skip assets that fail computation (e.g., missing snapshots)
                    pass
            return results

    def get_asset_lots(
        self, asset_id: int, page: int = 1, size: int = 50
    ) -> LotsPageResponse:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            strategy = self._registry.get(asset.asset_type.value)
            all_lots = strategy.compute_lots(asset, uow)
            start = (page - 1) * size
            end = start + size
            return LotsPageResponse(
                items=all_lots[start:end],
                total=len(all_lots),
                page=page,
                size=size,
            )
```

- [ ] **Step 4: Run all tests**

```bash
cd backend
uv run pytest tests/unit/test_returns_strategies.py -v
uv run pytest --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/services/returns/returns_service.py tests/unit/test_returns_strategies.py
git commit -m "feat(returns): add thin ReturnsService coordinator"
```

---

## Task 5: Improve PriceFeed with BasePriceFetcher and @register_fetcher

**Files:**
- Modify: `backend/app/services/price_feed.py`
- Test: `backend/tests/unit/test_price_fetchers.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/unit/test_price_fetchers.py
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
    from app.services.price_feed import YFinanceStockFetcher
    assert YFinanceStockFetcher.staleness_threshold == timedelta(hours=6)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_price_fetchers.py -v
```

Expected: Failures — `BasePriceFetcher`, `_FETCHER_REGISTRY`, etc. not yet defined.

- [ ] **Step 3: Add BasePriceFetcher and @register_fetcher to price_feed.py**

Open `backend/app/services/price_feed.py`. Add the following BEFORE the existing fetcher classes:

```python
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import ClassVar, Optional

# ---------------------------------------------------------------------------
# Self-registering fetcher infrastructure
# ---------------------------------------------------------------------------

_FETCHER_REGISTRY: dict[str, type["BasePriceFetcher"]] = {}


def register_fetcher(cls):
    """
    Class decorator: register a fetcher for each of its declared asset_types.
    """
    for at in cls.asset_types:
        _FETCHER_REGISTRY[at] = cls
    return cls


class BasePriceFetcher(ABC):
    """
    Abstract base class for all price fetchers.

    Class variables (must be set on each concrete subclass):
        asset_types:         list of AssetType strings this fetcher handles
        staleness_threshold: timedelta after which a cached price is stale
    """
    asset_types: ClassVar[list[str]]
    staleness_threshold: ClassVar[timedelta]

    @abstractmethod
    def fetch(self, asset) -> Optional["PriceResult"]: ...
```

Then add `@register_fetcher` decorator and `staleness_threshold` class var to each existing fetcher class:

- Find `class MFAPIFetcher` (or equivalent) and add:
  ```python
  @register_fetcher
  class MFAPIFetcher(BasePriceFetcher):
      asset_types = ["MF"]
      staleness_threshold = timedelta(days=1)
      # ... existing code unchanged
  ```

- Find `class YFinanceStockFetcher` (or equivalent) and add:
  ```python
  @register_fetcher
  class YFinanceStockFetcher(BasePriceFetcher):
      asset_types = ["STOCK_IN", "STOCK_US", "RSU", "GOLD", "SGB"]
      staleness_threshold = timedelta(hours=6)
      # ... existing code unchanged
  ```

- Find the NPS fetcher and add:
  ```python
  @register_fetcher
  class NPSNavFetcher(BasePriceFetcher):
      asset_types = ["NPS"]
      staleness_threshold = timedelta(days=1)
      # ... existing code unchanged
  ```

- [ ] **Step 4: Update PriceService to read staleness_threshold from fetcher**

In `backend/app/services/price_service.py`, find where `STALE_MINUTES` is checked and replace with the fetcher's `staleness_threshold`:

```python
from app.services.price_feed import _FETCHER_REGISTRY

def _is_stale(self, asset, price_cache_entry) -> bool:
    fetcher_cls = _FETCHER_REGISTRY.get(asset.asset_type.value)
    if fetcher_cls is None:
        return False
    threshold = fetcher_cls.staleness_threshold
    if price_cache_entry is None:
        return True
    age = datetime.utcnow() - price_cache_entry.fetched_at
    return age > threshold
```

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_price_fetchers.py -v
uv run pytest --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/services/price_feed.py app/services/price_service.py tests/unit/test_price_fetchers.py
git commit -m "feat(price): add BasePriceFetcher ABC, @register_fetcher decorator, staleness_threshold ClassVar"
```

---

## Task 6: Create AssetService and TransactionService

**Files:**
- Create: `backend/app/services/asset_service.py`
- Create: `backend/app/services/transaction_service.py`

These are thin wrappers that let API routes follow the rule: no route calls a repository directly.

- [ ] **Step 1: Create asset_service.py**

```python
# backend/app/services/asset_service.py
"""
AssetService — thin wrapper over AssetRepository + GoalRepository.
All business logic for asset CRUD lives here; routes call service methods only.
"""
from __future__ import annotations

from typing import Optional

from app.middleware.error_handler import NotFoundError
from app.models.asset import Asset, AssetType, AssetClass
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory
from app.schemas.asset import AssetCreate, AssetUpdate, AssetResponse


class AssetService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def create(self, body: AssetCreate) -> Asset:
        with self._uow_factory() as uow:
            return uow.assets.create(**body.model_dump())

    def list(
        self,
        asset_type: Optional[AssetType] = None,
        asset_class: Optional[AssetClass] = None,
        active: Optional[bool] = None,
    ) -> list[Asset]:
        with self._uow_factory() as uow:
            return uow.assets.list(asset_type=asset_type, asset_class=asset_class, active=active)

    def get_by_id(self, asset_id: int) -> Asset:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            allocations = uow.goals.list_allocations_for_asset(asset_id)
            asset.goals = [{"id": a.goal.id, "name": a.goal.name} for a in allocations]
            return asset

    def update(self, asset_id: int, body: AssetUpdate) -> Asset:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            return uow.assets.update(asset, **body.model_dump(exclude_none=True))

    def delete(self, asset_id: int) -> Asset:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            return uow.assets.soft_delete(asset)
```

- [ ] **Step 2: Create transaction_service.py**

```python
# backend/app/services/transaction_service.py
"""
TransactionService — thin wrapper over TransactionRepository.
"""
from __future__ import annotations

from app.middleware.error_handler import NotFoundError
from app.models.transaction import Transaction
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory
from app.schemas.transaction import TransactionCreate, TransactionUpdate


class TransactionService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def create(self, asset_id: int, body: TransactionCreate) -> Transaction:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            data = body.model_dump()
            data["asset_id"] = asset_id
            # Convert amount_inr from INR to paise
            data["amount_inr"] = int(data["amount_inr"] * 100)
            if data.get("charges_inr") is not None:
                data["charges_inr"] = int(data["charges_inr"] * 100)
            return uow.transactions.create(**data)

    def list_paginated(self, asset_id: int, page: int, page_size: int):
        with self._uow_factory() as uow:
            total = uow.transactions.count_by_asset(asset_id)
            txns = uow.transactions.list_by_asset_paginated(asset_id, page, page_size)
            return txns, total

    def update(self, asset_id: int, txn_id_int: int, body: TransactionUpdate) -> Transaction:
        with self._uow_factory() as uow:
            txn = uow.transactions.get_by_id(txn_id_int)
            if not txn or txn.asset_id != asset_id:
                raise NotFoundError(f"Transaction {txn_id_int} not found for asset {asset_id}")
            return uow.transactions.update(txn, **body.model_dump(exclude_none=True))

    def delete(self, asset_id: int, txn_id_int: int) -> None:
        with self._uow_factory() as uow:
            txn = uow.transactions.get_by_id(txn_id_int)
            if not txn or txn.asset_id != asset_id:
                raise NotFoundError(f"Transaction {txn_id_int} not found for asset {asset_id}")
            uow.transactions.delete(txn)
```

- [ ] **Step 3: Commit**

```bash
cd backend
git add app/services/asset_service.py app/services/transaction_service.py
git commit -m "feat(services): add AssetService and TransactionService wrappers for API layer cleanup"
```

---

## Task 7: Update api/assets.py and api/transactions.py to use services

**Files:**
- Modify: `backend/app/api/assets.py`
- Modify: `backend/app/api/transactions.py`
- Modify: `backend/app/api/dependencies.py`

- [ ] **Step 1: Add service factories to dependencies.py**

Append to `backend/app/api/dependencies.py`:

```python
from app.services.asset_service import AssetService
from app.services.transaction_service import TransactionService
from app.services.returns.returns_service import ReturnsService
from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry


def get_asset_service(db: Session = Depends(get_db)) -> AssetService:
    return AssetService(uow_factory=lambda: UnitOfWork(db))


def get_transaction_service(db: Session = Depends(get_db)) -> TransactionService:
    return TransactionService(uow_factory=lambda: UnitOfWork(db))


def get_returns_service(db: Session = Depends(get_db)) -> ReturnsService:
    return ReturnsService(
        uow_factory=lambda: UnitOfWork(db),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )
```

- [ ] **Step 2: Run existing integration tests BEFORE changing routes**

```bash
cd backend
uv run pytest tests/integration/test_assets_api.py tests/integration/test_transactions_api.py -v
```

Note all passing tests. After the route change, they must still pass.

- [ ] **Step 3: Update api/assets.py**

Replace the current implementation (which creates repos directly) with service calls:

```python
# backend/app/api/assets.py
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from app.api.dependencies import get_asset_service
from app.models.asset import AssetType, AssetClass
from app.schemas.asset import AssetCreate, AssetUpdate, AssetResponse
from app.services.asset_service import AssetService

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset(
    body: AssetCreate,
    service: AssetService = Depends(get_asset_service),
):
    return service.create(body)


@router.get("", response_model=list[AssetResponse])
def list_assets(
    type: Optional[AssetType] = Query(None),
    asset_class: Optional[AssetClass] = Query(None),
    active: Optional[bool] = Query(None),
    service: AssetService = Depends(get_asset_service),
):
    return service.list(asset_type=type, asset_class=asset_class, active=active)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: int, service: AssetService = Depends(get_asset_service)):
    return service.get_by_id(asset_id)


@router.put("/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: int,
    body: AssetUpdate,
    service: AssetService = Depends(get_asset_service),
):
    return service.update(asset_id, body)


@router.delete("/{asset_id}", response_model=AssetResponse)
def delete_asset(asset_id: int, service: AssetService = Depends(get_asset_service)):
    return service.delete(asset_id)
```

- [ ] **Step 4: Run integration tests for assets**

```bash
cd backend
uv run pytest tests/integration/test_assets_api.py -v
```

Expected: All tests pass (same behavior, different implementation).

- [ ] **Step 5: Update api/transactions.py similarly**

Replace direct repo calls in `api/transactions.py` with `TransactionService`:

```python
# backend/app/api/transactions.py (key route shapes — keep existing query params)
from app.api.dependencies import get_transaction_service
from app.services.transaction_service import TransactionService

# Replace: db: Session = Depends(get_db) → service: TransactionService = Depends(get_transaction_service)
# Replace: repo = TransactionRepository(db); repo.create(...) → service.create(asset_id, body)
```

The exact replacement depends on the current `api/transactions.py` content. Follow the same pattern as assets.py above.

- [ ] **Step 6: Run integration tests for transactions**

```bash
cd backend
uv run pytest tests/integration/test_transactions_api.py -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/api/assets.py app/api/transactions.py app/api/dependencies.py
git commit -m "feat(api): migrate assets and transactions routes to use services via Depends — no direct repo access"
```

---

## Task 8: Remove db.commit() from all repositories

**Files:** All repository files.

This is the final step. All services now use `UnitOfWork` which handles commits. The individual `db.commit()` calls in repos cause double-commits (harmless for SQLite, wasteful). Remove them.

- [ ] **Step 1: Run full test suite BEFORE making changes**

```bash
cd backend
uv run pytest --tb=short -q
```

All tests must pass. Record the count.

- [ ] **Step 2: Remove db.commit() from asset_repo.py**

In `backend/app/repositories/asset_repo.py`, replace each `create`, `update`, `soft_delete` method to use `db.flush()` instead of `db.commit()`:

```python
def create(self, **kwargs) -> Asset:
    asset = Asset(**kwargs)
    self.db.add(asset)
    self.db.flush()       # ← was db.commit()
    self.db.refresh(asset)
    return asset

def update(self, asset: Asset, **kwargs) -> Asset:
    for key, value in kwargs.items():
        if value is not None:
            setattr(asset, key, value)
    self.db.flush()       # ← was db.commit()
    self.db.refresh(asset)
    return asset

def soft_delete(self, asset: Asset) -> Asset:
    asset.is_active = False
    self.db.flush()       # ← was db.commit()
    self.db.refresh(asset)
    return asset
```

- [ ] **Step 3: Remove db.commit() from transaction_repo.py**

Same pattern: replace `db.commit()` with `db.flush()` in `create`, `update`, `delete`:

```python
def create(self, **kwargs) -> Transaction:
    txn = Transaction(**kwargs)
    self.db.add(txn)
    self.db.flush()
    self.db.refresh(txn)
    return txn

def update(self, txn: Transaction, **kwargs) -> Transaction:
    for key, value in kwargs.items():
        if value is not None:
            setattr(txn, key, value)
    self.db.flush()
    self.db.refresh(txn)
    return txn

def delete(self, txn: Transaction) -> None:
    self.db.delete(txn)
    self.db.flush()
```

- [ ] **Step 4: Remove db.commit() from remaining repos**

Apply the same `db.commit()` → `db.flush()` change to:
- `valuation_repo.py` (create, delete)
- `price_cache_repo.py` (upsert)
- `fd_repo.py` (create, update)
- `cas_snapshot_repo.py` (create)
- `goal_repo.py` (create, update, delete, create_allocation, delete_allocation)
- `snapshot_repo.py` (upsert)
- `important_data_repo.py` (create, update, delete)

For each repo, the pattern is the same:
```python
# Before:
self.db.commit()
# After:
self.db.flush()
```

`interest_rate_repo.py` is read-only — no changes needed.

- [ ] **Step 5: Run full test suite**

```bash
cd backend
uv run pytest --tb=short -q
```

Expected: All tests pass. Same count as Step 1.

> **If a test fails:** The failure means some code path is NOT going through UoW and is relying on repo commits. Find the failing test, trace which route/service it tests, and ensure that route uses a service that uses UoW. Do NOT revert the flush change — fix the caller instead.

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/repositories/
git commit -m "refactor(repos): replace db.commit() with db.flush() — UnitOfWork is the single commit point"
```

---

## Task 9: Final coverage check and cleanup

- [ ] **Step 1: Run full test suite with coverage**

```bash
cd backend
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=80 -q
```

Expected: Overall coverage ≥ 80%, engine ≥ 90%, importers ≥ 85%.

- [ ] **Step 2: Verify the no-direct-repo-in-routes rule**

```bash
cd backend
grep -rn "Repository(" app/api/ --include="*.py"
```

Expected: No matches. All routes should use service classes, not repos directly.

- [ ] **Step 3: Verify the no-Session-in-services rule**

```bash
cd backend
grep -rn "Session" app/services/ --include="*.py" | grep -v "unit_of_work\|#"
```

Expected: Only `unit_of_work.py` and `UnitOfWork` usage. No service should import `Session` directly.

- [ ] **Step 4: Final commit**

```bash
cd backend
git add -p
git commit -m "chore: plan 4 complete — strategy pattern, price fetchers, API cleanup, repo commits removed"
```

---

## Execution order summary

All 4 plans together complete the full refactoring:

| Plan | Sections | Can start when |
|------|----------|---------------|
| Plan 1 (Foundation) | 1, 2, 3 | Immediately |
| Plan 2 (Engine) | 10 | Immediately (independent) |
| Plan 3 (Importers) | 4, 7, 8 | After Plan 1 |
| Plan 4 (Services & API) | 5, 6, 9 | After Plans 1, 2, 3 |

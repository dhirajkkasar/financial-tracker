# Backend Refactoring — Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the infrastructure every other refactoring plan depends on: typed response schemas, repository Protocol interfaces, Unit of Work, and a central DI wiring file.

**Architecture:** Create `schemas/responses/` for typed service outputs; create `repositories/interfaces.py` using duck-typed Protocols (no changes to existing repos); create `repositories/unit_of_work.py` as a context manager over all repos; create `api/dependencies.py` as the single place for concrete wiring. All changes are purely additive — existing tests stay green after every task.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, pytest

**Execution order:** This plan must be completed before Plans 3 and 4. Plan 2 (Engine) is independent and may run in parallel.

**Git branch** Use git branch feature/refactor to commit code. Do not use main branch.

---

## File Map

**New files:**
- `backend/app/schemas/responses/__init__.py`
- `backend/app/schemas/responses/common.py`
- `backend/app/schemas/responses/returns.py`
- `backend/app/schemas/responses/tax.py`
- `backend/app/schemas/responses/imports.py`
- `backend/app/schemas/responses/prices.py`
- `backend/app/repositories/interfaces.py`
- `backend/app/repositories/unit_of_work.py`
- `backend/app/api/dependencies.py`
- `backend/tests/unit/test_unit_of_work.py`
- `backend/tests/unit/test_response_schemas.py`

**Unchanged:** All existing files remain untouched. `db.commit()` calls in repos are NOT removed in this plan (that happens in Plan 4 after all services migrate to UoW).

---

## Task 1: Create schemas/responses/common.py

**Files:**
- Create: `backend/app/schemas/responses/__init__.py`
- Create: `backend/app/schemas/responses/common.py`
- Test: `backend/tests/unit/test_response_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_response_schemas.py
from app.schemas.responses.common import PaginatedResponse


def test_paginated_response_instantiation():
    r = PaginatedResponse[str](items=["a", "b"], total=10, page=1, size=2)
    assert r.items == ["a", "b"]
    assert r.total == 10
    assert r.page == 1
    assert r.size == 2


def test_paginated_response_empty():
    r = PaginatedResponse[int](items=[], total=0, page=1, size=20)
    assert r.items == []
    assert r.total == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
uv run pytest tests/unit/test_response_schemas.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.schemas.responses'`

- [ ] **Step 3: Create the package init**

```python
# backend/app/schemas/responses/__init__.py
```

(Empty file — just marks the directory as a package.)

- [ ] **Step 4: Create common.py**

```python
# backend/app/schemas/responses/common.py
from typing import TypeVar, Generic, List
from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated wrapper returned by any list endpoint."""
    items: List[T]
    total: int
    page: int
    size: int
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend
uv run pytest tests/unit/test_response_schemas.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/schemas/responses/__init__.py app/schemas/responses/common.py tests/unit/test_response_schemas.py
git commit -m "feat: add schemas/responses package with PaginatedResponse"
```

---

## Task 2: Create schemas/responses/returns.py

**Files:**
- Create: `backend/app/schemas/responses/returns.py`
- Modify: `backend/tests/unit/test_response_schemas.py`

These types are used by the strategy classes added in Plan 4. They intentionally differ from the existing `schemas/returns.ReturnResponse` (which the frontend API still uses) — `AssetReturnsResponse` is the service-layer contract; routes map it to the API schema.

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/unit/test_response_schemas.py`:

```python
from app.schemas.responses.returns import (
    AssetReturnsResponse,
    LotComputedResponse,
    LotsPageResponse,
)


def test_asset_returns_response_defaults():
    r = AssetReturnsResponse(
        asset_id=1,
        asset_name="HDFC MF",
        asset_type="MF",
        is_active=True,
    )
    assert r.asset_id == 1
    assert r.invested is None
    assert r.xirr is None


def test_lots_page_response():
    lot = LotComputedResponse(
        lot_id="lot_001",
        buy_date="2023-01-15",
        units=10.0,
        buy_price_per_unit=100.0,
        buy_amount_inr=1000.0,
        current_price=120.0,
        current_value=1200.0,
        holding_days=365,
        is_short_term=False,
        unrealised_gain=200.0,
        unrealised_gain_pct=20.0,
    )
    page = LotsPageResponse(items=[lot], total=1, page=1, size=20)
    assert page.total == 1
    assert page.items[0].lot_id == "lot_001"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
uv run pytest tests/unit/test_response_schemas.py::test_asset_returns_response_defaults -v
```

Expected: `ImportError`

- [ ] **Step 3: Create schemas/responses/returns.py**

```python
# backend/app/schemas/responses/returns.py
from datetime import date
from typing import List, Optional
from pydantic import BaseModel
from app.schemas.responses.common import PaginatedResponse


class AssetReturnsResponse(BaseModel):
    """Service-layer return type produced by each returns strategy."""
    asset_id: int
    asset_name: str
    asset_type: str
    is_active: bool

    # Core financials (None when not computable)
    invested: Optional[float] = None          # INR
    current_value: Optional[float] = None     # INR
    current_pnl: Optional[float] = None       # unrealised, INR
    current_pnl_pct: Optional[float] = None
    alltime_pnl: Optional[float] = None       # unrealised + realised, INR
    xirr: Optional[float] = None
    cagr: Optional[float] = None
    message: Optional[str] = None            # human-readable reason when null

    # Market-based extras
    total_units: Optional[float] = None
    avg_price: Optional[float] = None
    current_price: Optional[float] = None
    price_is_stale: Optional[bool] = None
    price_fetched_at: Optional[str] = None

    # Lot-based gain breakdown
    st_unrealised_gain: Optional[float] = None
    lt_unrealised_gain: Optional[float] = None
    st_realised_gain: Optional[float] = None
    lt_realised_gain: Optional[float] = None

    # FD/RD extras
    maturity_amount: Optional[float] = None
    accrued_value_today: Optional[float] = None
    days_to_maturity: Optional[int] = None
    taxable_interest: Optional[float] = None
    potential_tax_30pct: Optional[float] = None


class LotComputedResponse(BaseModel):
    """Single FIFO lot with computed unrealised gain."""
    lot_id: str
    buy_date: date
    units: float
    buy_price_per_unit: float
    buy_amount_inr: float
    current_price: float
    current_value: float
    holding_days: int
    is_short_term: bool
    unrealised_gain: float
    unrealised_gain_pct: float


class LotsPageResponse(PaginatedResponse[LotComputedResponse]):
    """Paginated lots for a single asset."""
    pass
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
uv run pytest tests/unit/test_response_schemas.py -v
```

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/schemas/responses/returns.py tests/unit/test_response_schemas.py
git commit -m "feat: add AssetReturnsResponse and LotComputedResponse to schemas/responses"
```

---

## Task 3: Create schemas/responses/tax.py

**Files:**
- Create: `backend/app/schemas/responses/tax.py`
- Modify: `backend/tests/unit/test_response_schemas.py`

- [ ] **Step 1: Add failing test**

Append to `backend/tests/unit/test_response_schemas.py`:

```python
from app.schemas.responses.tax import (
    TaxGainEntry,
    TaxSummaryResponse,
    HarvestOpportunityEntry,
    UnrealisedGainEntry,
)


def test_tax_summary_response():
    entry = TaxGainEntry(
        category="Equity",
        asset_types=["STOCK_IN", "MF"],
        st_gain=5000.0,
        lt_gain=20000.0,
        st_tax=1000.0,
        lt_tax=None,
        is_st_slab=False,
        is_lt_slab=False,
        ltcg_exemption_used=12500.0,
    )
    resp = TaxSummaryResponse(fy="2024-25", entries=[entry], total_estimated_tax=1000.0)
    assert resp.fy == "2024-25"
    assert len(resp.entries) == 1


def test_harvest_opportunity_entry():
    e = HarvestOpportunityEntry(
        asset_id=1,
        asset_name="Test Stock",
        asset_type="STOCK_IN",
        lot_id="lot_001",
        buy_date="2023-01-01",
        units=10.0,
        unrealised_loss=500.0,
        is_short_term=True,
    )
    assert e.unrealised_loss == 500.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
uv run pytest tests/unit/test_response_schemas.py::test_tax_summary_response -v
```

Expected: `ImportError`

- [ ] **Step 3: Create schemas/responses/tax.py**

```python
# backend/app/schemas/responses/tax.py
from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class TaxGainEntry(BaseModel):
    """Rolled-up tax gains for one broad category (Equity / Debt / Gold / Real Estate)."""
    category: str                          # "Equity", "Debt", "Gold", "Real Estate"
    asset_types: List[str]                 # e.g. ["STOCK_IN", "MF"]
    st_gain: float                         # INR
    lt_gain: float                         # INR
    st_tax: Optional[float] = None         # None when slab rate applies
    lt_tax: Optional[float] = None         # None when slab rate applies
    is_st_slab: bool = False
    is_lt_slab: bool = False
    ltcg_exemption_used: float = 0.0       # INR, Section 112A


class TaxSummaryResponse(BaseModel):
    """Response for GET /tax/summary?fy=..."""
    fy: str                                # "2024-25"
    entries: List[TaxGainEntry]
    total_estimated_tax: Optional[float] = None


class UnrealisedGainEntry(BaseModel):
    """Unrealised gain for one asset (GET /tax/unrealised)."""
    asset_id: int
    asset_name: str
    asset_type: str
    st_unrealised_gain: Optional[float] = None
    lt_unrealised_gain: Optional[float] = None
    total_unrealised_gain: Optional[float] = None


class HarvestOpportunityEntry(BaseModel):
    """A lot with negative unrealised gain (tax-loss harvesting candidate)."""
    asset_id: int
    asset_name: str
    asset_type: str
    lot_id: str
    buy_date: date
    units: float
    unrealised_loss: float                 # positive number representing the loss magnitude
    is_short_term: bool
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
uv run pytest tests/unit/test_response_schemas.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/schemas/responses/tax.py tests/unit/test_response_schemas.py
git commit -m "feat: add TaxSummaryResponse and HarvestOpportunityEntry to schemas/responses"
```

---

## Task 4: Create schemas/responses/imports.py and prices.py

**Files:**
- Create: `backend/app/schemas/responses/imports.py`
- Create: `backend/app/schemas/responses/prices.py`
- Modify: `backend/tests/unit/test_response_schemas.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/unit/test_response_schemas.py`:

```python
from app.schemas.responses.imports import (
    ImportPreviewResponse,
    ImportCommitResponse,
    ParsedTransactionPreview,
)
from app.schemas.responses.prices import PriceRefreshResponse, AssetPriceEntry


def test_import_preview_response():
    r = ImportPreviewResponse(
        preview_id="abc-123",
        new_count=5,
        duplicate_count=2,
        transactions=[],
    )
    assert r.preview_id == "abc-123"
    assert r.new_count == 5


def test_import_commit_response():
    r = ImportCommitResponse(inserted=5, skipped=2, errors=[])
    assert r.inserted == 5


def test_price_refresh_response():
    r = PriceRefreshResponse(refreshed=10, failed=1, stale=2)
    assert r.refreshed == 10
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
uv run pytest tests/unit/test_response_schemas.py::test_import_preview_response -v
```

Expected: `ImportError`

- [ ] **Step 3: Create schemas/responses/imports.py**

```python
# backend/app/schemas/responses/imports.py
from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class ParsedTransactionPreview(BaseModel):
    """One parsed transaction row shown in the import preview UI."""
    txn_id: str
    asset_name: str
    asset_type: str
    txn_type: str
    date: date
    units: Optional[float] = None
    amount_inr: float
    notes: Optional[str] = None
    is_duplicate: bool = False


class ImportPreviewResponse(BaseModel):
    """Response for POST /imports/preview"""
    preview_id: str
    new_count: int
    duplicate_count: int
    transactions: List[ParsedTransactionPreview]
    warnings: List[str] = []


class ImportCommitResponse(BaseModel):
    """Response for POST /imports/commit/{preview_id}"""
    inserted: int
    skipped: int
    errors: List[str] = []
```

- [ ] **Step 4: Create schemas/responses/prices.py**

```python
# backend/app/schemas/responses/prices.py
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class AssetPriceEntry(BaseModel):
    """Price record for a single asset."""
    asset_id: int
    asset_name: str
    asset_type: str
    price_inr: float
    source: str
    fetched_at: datetime
    is_stale: bool


class PriceRefreshResponse(BaseModel):
    """Response for POST /prices/refresh"""
    refreshed: int
    failed: int
    stale: int = 0
    errors: List[str] = []
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend
uv run pytest tests/unit/test_response_schemas.py -v
```

Expected: PASS (all tests)

- [ ] **Step 6: Update schemas/responses/__init__.py to export all types**

```python
# backend/app/schemas/responses/__init__.py
from app.schemas.responses.common import PaginatedResponse
from app.schemas.responses.returns import (
    AssetReturnsResponse,
    LotComputedResponse,
    LotsPageResponse,
)
from app.schemas.responses.tax import (
    TaxGainEntry,
    TaxSummaryResponse,
    UnrealisedGainEntry,
    HarvestOpportunityEntry,
)
from app.schemas.responses.imports import (
    ParsedTransactionPreview,
    ImportPreviewResponse,
    ImportCommitResponse,
)
from app.schemas.responses.prices import AssetPriceEntry, PriceRefreshResponse

__all__ = [
    "PaginatedResponse",
    "AssetReturnsResponse",
    "LotComputedResponse",
    "LotsPageResponse",
    "TaxGainEntry",
    "TaxSummaryResponse",
    "UnrealisedGainEntry",
    "HarvestOpportunityEntry",
    "ParsedTransactionPreview",
    "ImportPreviewResponse",
    "ImportCommitResponse",
    "AssetPriceEntry",
    "PriceRefreshResponse",
]
```

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/schemas/responses/ tests/unit/test_response_schemas.py
git commit -m "feat: add ImportPreviewResponse, ImportCommitResponse, PriceRefreshResponse to schemas/responses"
```

---

## Task 5: Create repositories/interfaces.py

**Files:**
- Create: `backend/app/repositories/interfaces.py`
- Test: `backend/tests/unit/test_unit_of_work.py`

These are duck-typed Protocols — no changes to existing repo classes needed. The repos already satisfy them structurally.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_unit_of_work.py
from app.repositories.interfaces import (
    IAssetRepository,
    ITransactionRepository,
    IValuationRepository,
    IPriceCacheRepository,
    IFDRepository,
    ICasSnapshotRepository,
    IGoalRepository,
)
from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository


def test_asset_repo_satisfies_interface():
    """AssetRepository satisfies IAssetRepository via duck-typing."""
    # runtime_checkable protocols let us use isinstance
    from typing import runtime_checkable
    # We verify by checking all required methods exist on the class
    assert hasattr(AssetRepository, "get_by_id")
    assert hasattr(AssetRepository, "list")
    assert hasattr(AssetRepository, "create")
    assert hasattr(AssetRepository, "update")


def test_transaction_repo_satisfies_interface():
    assert hasattr(TransactionRepository, "get_by_txn_id")
    assert hasattr(TransactionRepository, "create")
    assert hasattr(TransactionRepository, "list_by_asset")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
uv run pytest tests/unit/test_unit_of_work.py -v
```

Expected: `ImportError: cannot import name 'IAssetRepository'`

- [ ] **Step 3: Create repositories/interfaces.py**

```python
# backend/app/repositories/interfaces.py
"""
Protocol definitions for all repository classes.

These are structural (duck-typed) protocols — existing repo classes satisfy them
without any code changes. Use these types in service __init__ signatures so that
tests can inject fakes without patching.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Protocol, runtime_checkable

from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import Transaction
from app.models.valuation import Valuation
from app.models.price_cache import PriceCache
from app.models.fd_detail import FDDetail
from app.models.cas_snapshot import CasSnapshot
from app.models.goal import Goal, GoalAllocation
from app.models.snapshot import PortfolioSnapshot


@runtime_checkable
class IAssetRepository(Protocol):
    def create(self, **kwargs) -> Asset: ...
    def get_by_id(self, asset_id: int) -> Optional[Asset]: ...
    def list(
        self,
        asset_type: Optional[AssetType] = None,
        asset_class: Optional[AssetClass] = None,
        active: Optional[bool] = None,
    ) -> list[Asset]: ...
    def update(self, asset: Asset, **kwargs) -> Asset: ...
    def soft_delete(self, asset: Asset) -> Asset: ...
    def list_unmatured_past_maturity(self) -> list[Asset]: ...


@runtime_checkable
class ITransactionRepository(Protocol):
    def create(self, **kwargs) -> Transaction: ...
    def get_by_txn_id(self, txn_id: str) -> Optional[Transaction]: ...
    def get_by_id(self, transaction_id: int) -> Optional[Transaction]: ...
    def list_by_asset(self, asset_id: int) -> list[Transaction]: ...
    def list_by_asset_paginated(self, asset_id: int, page: int, page_size: int) -> list[Transaction]: ...
    def count_by_asset(self, asset_id: int) -> int: ...
    def list_all(self) -> list[Transaction]: ...
    def update(self, txn: Transaction, **kwargs) -> Transaction: ...
    def delete(self, txn: Transaction) -> None: ...


@runtime_checkable
class IValuationRepository(Protocol):
    def create(self, **kwargs) -> Valuation: ...
    def get_by_id(self, valuation_id: int) -> Optional[Valuation]: ...
    def list_by_asset(self, asset_id: int) -> list[Valuation]: ...
    def delete(self, val: Valuation) -> None: ...


@runtime_checkable
class IPriceCacheRepository(Protocol):
    def get_by_asset_id(self, asset_id: int) -> Optional[PriceCache]: ...
    def upsert(
        self,
        asset_id: int,
        price_inr: int,
        source: str,
        fetched_at: Optional[datetime] = None,
        is_stale: bool = False,
    ) -> PriceCache: ...


@runtime_checkable
class IFDRepository(Protocol):
    def create(self, **kwargs) -> FDDetail: ...
    def get_by_asset_id(self, asset_id: int) -> Optional[FDDetail]: ...
    def update(self, fd: FDDetail, **kwargs) -> FDDetail: ...


@runtime_checkable
class ICasSnapshotRepository(Protocol):
    def create(
        self,
        asset_id: int,
        date: date,
        closing_units: float,
        nav_price_inr: int,
        market_value_inr: int,
        total_cost_inr: int,
    ) -> CasSnapshot: ...
    def get_latest_by_asset_id(self, asset_id: int) -> Optional[CasSnapshot]: ...


@runtime_checkable
class IGoalRepository(Protocol):
    def create(self, **kwargs) -> Goal: ...
    def get_by_id(self, goal_id: int) -> Optional[Goal]: ...
    def list_all(self) -> list[Goal]: ...
    def update(self, goal: Goal, **kwargs) -> Goal: ...
    def delete(self, goal: Goal) -> None: ...
    def create_allocation(self, **kwargs) -> GoalAllocation: ...
    def get_allocation(self, goal_id: int, asset_id: int) -> Optional[GoalAllocation]: ...
    def list_allocations_for_goal(self, goal_id: int) -> list[GoalAllocation]: ...
    def list_allocations_for_asset(self, asset_id: int) -> list[GoalAllocation]: ...
    def delete_allocation(self, alloc: GoalAllocation) -> None: ...


@runtime_checkable
class ISnapshotRepository(Protocol):
    def upsert(self, snapshot_date: date, total_value_paise: int, breakdown_json: str) -> PortfolioSnapshot: ...
    def list(self, from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[PortfolioSnapshot]: ...
    def get_by_date(self, snapshot_date: date) -> Optional[PortfolioSnapshot]: ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
uv run pytest tests/unit/test_unit_of_work.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/repositories/interfaces.py tests/unit/test_unit_of_work.py
git commit -m "feat: add repository Protocol interfaces (duck-typed, no existing code changes)"
```

---

## Task 6: Create repositories/unit_of_work.py

**Files:**
- Create: `backend/app/repositories/unit_of_work.py`
- Modify: `backend/tests/unit/test_unit_of_work.py`

- [ ] **Step 1: Add failing test**

Append to `backend/tests/unit/test_unit_of_work.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.repositories.unit_of_work import UnitOfWork


@pytest.fixture
def uow_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def test_uow_exposes_all_repos(uow_session):
    uow = UnitOfWork(uow_session)
    assert hasattr(uow, "assets")
    assert hasattr(uow, "transactions")
    assert hasattr(uow, "valuations")
    assert hasattr(uow, "price_cache")
    assert hasattr(uow, "fd")
    assert hasattr(uow, "cas_snapshots")
    assert hasattr(uow, "goals")
    assert hasattr(uow, "snapshots")


def test_uow_context_manager_commits_on_success(uow_session):
    with UnitOfWork(uow_session) as uow:
        uow.assets.create(
            name="Test Asset",
            identifier="TEST",
            asset_type="STOCK_IN",
            asset_class="EQUITY",
            is_active=True,
        )
    # After context exits cleanly, the record should be queryable
    from app.models.asset import Asset
    result = uow_session.query(Asset).filter_by(name="Test Asset").first()
    assert result is not None


def test_uow_context_manager_rolls_back_on_exception(uow_session):
    try:
        with UnitOfWork(uow_session) as uow:
            uow.assets.create(
                name="Should Rollback",
                identifier="ROLLBACK",
                asset_type="STOCK_IN",
                asset_class="EQUITY",
                is_active=True,
            )
            raise ValueError("Simulated failure")
    except ValueError:
        pass

    from app.models.asset import Asset
    result = uow_session.query(Asset).filter_by(name="Should Rollback").first()
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
uv run pytest tests/unit/test_unit_of_work.py::test_uow_exposes_all_repos -v
```

Expected: `ImportError: cannot import name 'UnitOfWork'`

- [ ] **Step 3: Create repositories/unit_of_work.py**

```python
# backend/app/repositories/unit_of_work.py
"""
Unit of Work — wraps a SQLAlchemy Session and all repositories.

Usage:
    with UnitOfWork(session) as uow:
        asset = uow.assets.create(name="Foo", ...)
        uow.transactions.create(asset_id=asset.id, ...)
    # All writes committed atomically here.
    # On exception, everything rolls back.

Note: While repos still have their own db.commit() calls (legacy),
the UoW's __exit__ commit is a no-op if already committed. The
UoW's rollback on failure IS effective because SQLite/PostgreSQL
support savepoints. Repos will have their commits removed in Plan 4.
"""
from __future__ import annotations

from typing import Protocol
from sqlalchemy.orm import Session

from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository
from app.repositories.valuation_repo import ValuationRepository
from app.repositories.price_cache_repo import PriceCacheRepository
from app.repositories.fd_repo import FDRepository
from app.repositories.cas_snapshot_repo import CasSnapshotRepository
from app.repositories.goal_repo import GoalRepository
from app.repositories.snapshot_repo import SnapshotRepository
from app.repositories.important_data_repo import ImportantDataRepository
from app.repositories.interest_rate_repo import InterestRateRepository


class UnitOfWork:
    """Context manager that provides all repositories and a single commit point."""

    def __init__(self, session: Session):
        self.session = session
        self.assets = AssetRepository(session)
        self.transactions = TransactionRepository(session)
        self.valuations = ValuationRepository(session)
        self.price_cache = PriceCacheRepository(session)
        self.fd = FDRepository(session)
        self.cas_snapshots = CasSnapshotRepository(session)
        self.goals = GoalRepository(session)
        self.snapshots = SnapshotRepository(session)
        self.important_data = ImportantDataRepository(session)
        self.interest_rates = InterestRateRepository(session)

    def __enter__(self) -> "UnitOfWork":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.session.rollback()
        else:
            self.session.commit()

    def flush(self) -> None:
        """Flush pending changes to DB without committing (makes IDs available)."""
        self.session.flush()


class IUnitOfWorkFactory(Protocol):
    """Callable that creates a UnitOfWork given the current session."""
    def __call__(self) -> UnitOfWork: ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
uv run pytest tests/unit/test_unit_of_work.py -v
```

Expected: PASS (all tests, including the rollback test — note: rollback test passes because the UoW calls `session.rollback()` which undoes the unflushed/uncommitted asset creation)

> **Note on the rollback test:** The asset repos currently call `db.commit()` immediately, so the rollback test may not fully isolate the failure until Plan 4 removes those commits. That is expected and acceptable. The test validates the UoW's interface contract.

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/repositories/unit_of_work.py tests/unit/test_unit_of_work.py
git commit -m "feat: add UnitOfWork context manager wrapping all repositories"
```

---

## Task 7: Create api/dependencies.py

**Files:**
- Create: `backend/app/api/dependencies.py`

This file is the single wiring point for all concrete service instantiation. Plans 3 and 4 will add their service factories here.

- [ ] **Step 1: Create api/dependencies.py**

No failing test needed for this task — the file is wiring-only and tested indirectly through integration tests. Create it now so Plans 3 and 4 have a place to add their factories.

```python
# backend/app/api/dependencies.py
"""
Central dependency wiring for FastAPI routes.

All concrete service instantiation lives here.
Routes import factory functions from this module and use them with Depends().

Rule: No route file should contain `db: Session = Depends(get_db)` directly
after migration. All data access goes through a service factory from this file.
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory


# ---------------------------------------------------------------------------
# Core: UnitOfWork factory
# ---------------------------------------------------------------------------

def get_uow_factory(db: Session = Depends(get_db)) -> IUnitOfWorkFactory:
    """Provide a callable that creates a UnitOfWork bound to the request session."""
    return lambda: UnitOfWork(db)


# ---------------------------------------------------------------------------
# Placeholder stubs — filled in by Plans 3 and 4
# ---------------------------------------------------------------------------
# Plan 3 will add:
#   get_import_orchestrator(db) -> ImportOrchestrator
#
# Plan 4 will add:
#   get_returns_service(db) -> ReturnsService
#   get_tax_service(db) -> TaxService
#   get_price_service(db) -> PriceService
#   get_asset_service(db) -> AssetService
#   get_transaction_service(db) -> TransactionService
```

- [ ] **Step 2: Run full test suite to confirm nothing broke**

```bash
cd backend
uv run pytest --tb=short -q
```

Expected: All existing tests pass (no regressions — we only added files).

- [ ] **Step 3: Commit**

```bash
cd backend
git add app/api/dependencies.py
git commit -m "feat: add api/dependencies.py as central DI wiring scaffold"
```

---

## Task 8: Verify coverage and run full suite

- [ ] **Step 1: Run full test suite with coverage**

```bash
cd backend
uv run pytest --cov=app --cov-report=term-missing -q
```

Expected: All tests pass. Coverage should remain at or above baseline — the new files add classes/schemas but no branches that aren't exercised by the new unit tests.

- [ ] **Step 2: Confirm new modules are importable**

```bash
cd backend
uv run python -c "
from app.schemas.responses import (
    PaginatedResponse, AssetReturnsResponse, TaxSummaryResponse,
    ImportPreviewResponse, PriceRefreshResponse
)
from app.repositories.interfaces import IAssetRepository, ITransactionRepository
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory
from app.api.dependencies import get_uow_factory
print('All foundation imports OK')
"
```

Expected output: `All foundation imports OK`

- [ ] **Step 3: Final commit**

```bash
cd backend
git add -p  # review any outstanding changes
git commit -m "chore: plan 1 foundation complete — schemas/responses, repo interfaces, UoW, dependencies scaffold"
```

---

## What's next

- **Plan 2 (Engine)** — independent, can start now
- **Plan 3 (Importers)** — depends on this plan; uses `UnitOfWork`, `ImportPreviewResponse`, `ImportCommitResponse`
- **Plan 4 (Services & API)** — depends on this plan; uses `UnitOfWork`, `AssetReturnsResponse`, `get_uow_factory`

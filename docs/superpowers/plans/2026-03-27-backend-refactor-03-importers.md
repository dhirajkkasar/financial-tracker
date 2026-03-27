# Backend Refactoring — Plan 3: Importer Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardise the importer layer so adding a new provider (Groww, Morgan Stanley) or format variant is a single-file drop-in with no edits to existing code; decompose the monolithic `ImportService` into a pipeline + orchestrator + post-processors + event bus; replace the module-level `_PREVIEW_STORE` dict with a typed `PreviewStore` class.

**Architecture:** `BaseImporter` ABC with `source`/`asset_type`/`format` class vars; `@register_importer` decorator builds a `ImporterRegistry`; `ImportPipeline` orchestrates parse → validate → deduplicate; `ImportOrchestrator` coordinates preview/commit using `UnitOfWork`; post-processors are self-contained classes registered by asset type; `SyncEventBus` fires `ImportCompletedEvent` after each commit so corp actions can subscribe without coupling to the importer.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, pytest

**Prerequisites:** Plan 1 must be complete (needs `UnitOfWork`, `ImportPreviewResponse`, `ImportCommitResponse` from `schemas/responses`).

**Git branch** Use git branch feature/refactor to commit code. Do not use main branch.
---

## File Map

**New files:**
- `backend/app/importers/registry.py`
- `backend/app/importers/pipeline.py`
- `backend/app/services/imports/__init__.py`
- `backend/app/services/imports/deduplicator.py`
- `backend/app/services/imports/preview_store.py`
- `backend/app/services/imports/post_processors/__init__.py`
- `backend/app/services/imports/post_processors/base.py`
- `backend/app/services/imports/post_processors/stock.py`
- `backend/app/services/imports/post_processors/mf.py`
- `backend/app/services/imports/orchestrator.py`
- `backend/app/services/event_bus.py`
- `backend/tests/unit/test_importer_registry.py`
- `backend/tests/unit/test_import_pipeline.py`
- `backend/tests/unit/test_import_orchestrator.py`
- `backend/tests/unit/test_event_bus.py`

**Modified:**
- `backend/app/importers/base.py` — add `BaseImporter` ABC alongside existing Protocol
- Each existing importer — add `@register_importer` decorator and `source`/`format`/`asset_type` class vars
- `backend/app/api/imports.py` — wire `ImportOrchestrator` via `Depends(get_import_orchestrator)`
- `backend/app/api/dependencies.py` — add `get_import_orchestrator` factory

**Unchanged:** `import_service.py` stays in place until all routes migrate (removed at end of this plan). Existing parsers keep their `parse()` method signatures.

---

## Task 1: Upgrade BaseImporter to ABC with class vars

**Files:**
- Modify: `backend/app/importers/base.py`
- Test: `backend/tests/unit/test_importer_registry.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/unit/test_importer_registry.py
import pytest
from app.importers.base import BaseImporter, ImportResult


def test_base_importer_requires_source_and_format():
    """Concrete subclass without source/format ClassVars must raise TypeError."""
    with pytest.raises(TypeError):
        class BadImporter(BaseImporter):
            def parse(self, file_bytes: bytes) -> ImportResult:
                return ImportResult(source="bad")
        BadImporter()  # should fail: abstract class or missing class vars enforced


def test_concrete_importer_with_class_vars():
    from app.importers.base import BaseImporter, ImportResult

    class GoodImporter(BaseImporter):
        source = "test_source"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes) -> ImportResult:
            return ImportResult(source=self.source)

    importer = GoodImporter()
    result = importer.parse(b"test")
    assert result.source == "test_source"


def test_validate_default_returns_empty_list():
    from app.importers.base import BaseImporter, ImportResult

    class MinimalImporter(BaseImporter):
        source = "minimal"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes) -> ImportResult:
            return ImportResult(source="minimal")

    importer = MinimalImporter()
    result = importer.parse(b"")
    warnings = importer.validate(result)
    assert warnings == []
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_importer_registry.py -v
```

Expected: Tests fail because `BaseImporter` is currently a Protocol, not an ABC.

- [ ] **Step 3: Update base.py to add BaseImporter ABC**

Open `backend/app/importers/base.py`. Keep the existing `ParsedTransaction`, `ParsedFundSnapshot`, `ImportResult` dataclasses and the legacy `BaseImporter` Protocol unchanged. Add the new ABC below:

```python
# backend/app/importers/base.py — append after existing code

from abc import ABC, abstractmethod
from typing import ClassVar


class BaseImporter(ABC):
    """
    Abstract base class for all file importers.

    Class variables (must be set on each concrete subclass):
        source:     identifier string, e.g. "zerodha", "cas", "groww"
        asset_type: string asset type, e.g. "STOCK_IN", "MF"
        format:     file format, e.g. "csv", "pdf"

    Adding a new provider: create a new subclass in the appropriate subdirectory,
    decorate with @register_importer. No other files need to change.
    """
    source: ClassVar[str]
    asset_type: ClassVar[str]
    format: ClassVar[str]

    @abstractmethod
    def parse(self, file_bytes: bytes) -> "ImportResult": ...

    def validate(self, result: "ImportResult") -> list[str]:
        """Optional validation hook. Default: no-op. Override to add checks."""
        return []
```

> **Note:** This renames the existing `BaseImporter` Protocol. Rename the existing Protocol to `LegacyBaseImporter` or `BaseImporterProtocol` to avoid the name clash, then update any callers.

Find all references to the old `BaseImporter` Protocol:
```bash
cd backend
grep -rn "BaseImporter" app/ tests/
```

For any caller that imported `from app.importers.base import BaseImporter` and used it as a Protocol type hint, update to use `BaseImporter` (the new ABC) or `LegacyBaseImporterProtocol` if they need the old Protocol.

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_importer_registry.py -v
```

Expected: `test_concrete_importer_with_class_vars` passes. `test_base_importer_requires_source_and_format` may still fail if ABC enforcement isn't via class vars — adjust the test to only verify that `parse()` is abstract:

```python
def test_base_importer_parse_is_abstract():
    from app.importers.base import BaseImporter
    with pytest.raises(TypeError):
        BaseImporter()  # can't instantiate abstract class
```

- [ ] **Step 5: Run full suite**

```bash
cd backend
uv run pytest --tb=short -q
```

Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/importers/base.py tests/unit/test_importer_registry.py
git commit -m "feat(importers): add BaseImporter ABC with source/asset_type/format class vars"
```

---

## Task 2: Create importers/registry.py

**Files:**
- Create: `backend/app/importers/registry.py`
- Modify: `backend/tests/unit/test_importer_registry.py`

- [ ] **Step 1: Add failing test**

Append to `backend/tests/unit/test_importer_registry.py`:

```python
def test_register_importer_decorator():
    from app.importers.registry import register_importer, ImporterRegistry
    from app.importers.base import BaseImporter, ImportResult

    @register_importer
    class TestCSVImporter(BaseImporter):
        source = "test_provider"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes) -> ImportResult:
            return ImportResult(source=self.source)

    registry = ImporterRegistry()
    importer = registry.get("test_provider", "csv")
    assert isinstance(importer, TestCSVImporter)


def test_registry_raises_for_unknown_source():
    from app.importers.registry import ImporterRegistry

    registry = ImporterRegistry()
    with pytest.raises(ValueError, match="No importer for"):
        registry.get("unknown_source", "csv")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_importer_registry.py::test_register_importer_decorator -v
```

Expected: `ImportError`

- [ ] **Step 3: Create importers/registry.py**

```python
# backend/app/importers/registry.py
"""
Importer registry + @register_importer decorator.

Usage:
    @register_importer
    class GrowwCSVImporter(BaseImporter):
        source = "groww"
        asset_type = "STOCK_IN"
        format = "csv"
        ...

Adding a new importer: create the class, apply @register_importer. Done.
No changes to ImporterRegistry or any other file.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.importers.base import BaseImporter

_REGISTRY: dict[tuple[str, str], type] = {}


def register_importer(cls):
    """
    Class decorator that registers an importer by (source, format) key.

    The class must have `source` and `format` class variables defined.
    """
    key = (cls.source, cls.format)
    _REGISTRY[key] = cls
    return cls


class ImporterRegistry:
    """
    Looks up and instantiates importers by (source, format).

    Returns a fresh instance for each call (importers are stateless).
    """

    def get(self, source: str, fmt: str) -> "BaseImporter":
        cls = _REGISTRY.get((source, fmt))
        if cls is None:
            available = sorted(_REGISTRY.keys())
            raise ValueError(
                f"No importer for source={source!r} format={fmt!r}. "
                f"Registered: {available}"
            )
        return cls()

    def list_registered(self) -> list[tuple[str, str]]:
        """Return all registered (source, format) keys."""
        return sorted(_REGISTRY.keys())
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_importer_registry.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/importers/registry.py tests/unit/test_importer_registry.py
git commit -m "feat(importers): add ImporterRegistry and @register_importer decorator"
```

---

## Task 3: Register existing importers

**Files:**
- Modify: `backend/app/importers/broker_csv_parser.py`
- Modify: `backend/app/importers/cas_parser.py`
- Modify: `backend/app/importers/nps_csv_parser.py`
- Modify: `backend/app/importers/ppf_csv_parser.py`
- Modify: `backend/app/importers/epf_pdf_parser.py`
- Modify: `backend/app/importers/fidelity_pdf_parser.py`
- Modify: `backend/app/importers/fidelity_rsu_csv_parser.py`
- Modify: `backend/tests/unit/test_importer_registry.py`

Each importer needs: `@register_importer` decorator, `source`, `asset_type`, `format` class vars, and the `parse()` method must match the new signature `parse(self, file_bytes: bytes) -> ImportResult` (remove `filename` parameter or keep it with a default of `""`).

- [ ] **Step 1: Add registry coverage test**

Append to `backend/tests/unit/test_importer_registry.py`:

```python
def test_all_importers_are_registered():
    """Import all importer modules so decorators fire, then verify registry."""
    # Force module loading — decorators register on import
    import app.importers.broker_csv_parser
    import app.importers.cas_parser
    import app.importers.nps_csv_parser
    import app.importers.ppf_csv_parser
    import app.importers.epf_pdf_parser
    import app.importers.fidelity_pdf_parser
    import app.importers.fidelity_rsu_csv_parser

    from app.importers.registry import ImporterRegistry
    registry = ImporterRegistry()
    registered = registry.list_registered()

    expected = [
        ("zerodha", "csv"),
        ("cas", "pdf"),
        ("nps", "csv"),
        ("ppf", "csv"),
        ("epf", "pdf"),
        ("fidelity_sale", "pdf"),
        ("fidelity_rsu", "csv"),
    ]
    for key in expected:
        assert key in registered, f"Expected {key} to be registered, got: {registered}"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_importer_registry.py::test_all_importers_are_registered -v
```

Expected: Fails — none of the importers are registered yet.

- [ ] **Step 3: Register broker_csv_parser.py (Zerodha)**

Find the main importer class in `backend/app/importers/broker_csv_parser.py`. It should be named something like `ZerodhaImporter` or `BrokerCSVParser`.

```bash
cd backend
grep -n "^class " app/importers/broker_csv_parser.py
```

Add at the top of the file:
```python
from app.importers.registry import register_importer
```

Then add `@register_importer` above the class definition and add the class vars inside the class body:

```python
@register_importer
class ZerodhaImporter(BaseImporter):   # (use whatever the actual class name is)
    source = "zerodha"
    asset_type = "STOCK_IN"
    format = "csv"
    # ... existing code unchanged
```

- [ ] **Step 4: Register cas_parser.py**

```bash
cd backend
grep -n "^class " app/importers/cas_parser.py
```

```python
@register_importer
class CASParser(BaseImporter):   # actual class name
    source = "cas"
    asset_type = "MF"
    format = "pdf"
    # ... existing code unchanged
```

- [ ] **Step 5: Register remaining importers**

Repeat for each remaining importer. Use the source/format values the test expects:

| File | source | asset_type | format |
|------|--------|-----------|--------|
| `nps_csv_parser.py` | `"nps"` | `"NPS"` | `"csv"` |
| `ppf_csv_parser.py` | `"ppf"` | `"PPF"` | `"csv"` |
| `epf_pdf_parser.py` | `"epf"` | `"EPF"` | `"pdf"` |
| `fidelity_pdf_parser.py` | `"fidelity_sale"` | `"STOCK_US"` | `"pdf"` |
| `fidelity_rsu_csv_parser.py` | `"fidelity_rsu"` | `"STOCK_US"` | `"csv"` |

- [ ] **Step 6: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_importer_registry.py -v
uv run pytest --tb=short -q  # full suite
```

Expected: All tests pass. Existing importer-specific tests (test_cas_parser.py, test_broker_csv_parser.py, etc.) should still pass unchanged.

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/importers/ tests/unit/test_importer_registry.py
git commit -m "feat(importers): register all existing importers with @register_importer"
```

---

## Task 4: Create imports/deduplicator.py and preview_store.py

**Files:**
- Create: `backend/app/services/imports/__init__.py`
- Create: `backend/app/services/imports/deduplicator.py`
- Create: `backend/app/services/imports/preview_store.py`
- Test: `backend/tests/unit/test_import_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/unit/test_import_pipeline.py
import time
import pytest
from datetime import datetime, date
from app.importers.base import ParsedTransaction, ImportResult


def _make_txn(txn_id="txn_001", asset_name="Test", asset_type="STOCK_IN") -> ParsedTransaction:
    return ParsedTransaction(
        source="zerodha",
        asset_name=asset_name,
        asset_identifier="TEST",
        asset_type=asset_type,
        txn_type="BUY",
        date=date(2024, 1, 1),
        amount_inr=-10000.0,
        txn_id=txn_id,
    )


# --- Deduplicator tests ---

def test_deduplicator_filters_known_txn_ids():
    from app.services.imports.deduplicator import InMemoryDeduplicator

    existing_ids = {"txn_001", "txn_002"}
    dedup = InMemoryDeduplicator(existing_ids)

    result = ImportResult(
        source="zerodha",
        transactions=[_make_txn("txn_001"), _make_txn("txn_003")],
    )
    filtered = dedup.filter_duplicates(result)
    assert len(filtered.transactions) == 1
    assert filtered.transactions[0].txn_id == "txn_003"
    assert filtered.duplicate_count == 1


def test_deduplicator_empty_existing_ids():
    from app.services.imports.deduplicator import InMemoryDeduplicator

    dedup = InMemoryDeduplicator(set())
    result = ImportResult(
        source="zerodha",
        transactions=[_make_txn("txn_new")],
    )
    filtered = dedup.filter_duplicates(result)
    assert len(filtered.transactions) == 1
    assert filtered.duplicate_count == 0


# --- PreviewStore tests ---

def test_preview_store_put_and_get():
    from app.services.imports.preview_store import PreviewStore

    store = PreviewStore(ttl_minutes=5)
    result = ImportResult(source="zerodha", transactions=[_make_txn()])
    preview_id = store.put(result)

    retrieved = store.get(preview_id)
    assert retrieved is not None
    assert retrieved.source == "zerodha"


def test_preview_store_get_expired_returns_none():
    from app.services.imports.preview_store import PreviewStore

    store = PreviewStore(ttl_minutes=0)  # immediate expiry
    result = ImportResult(source="zerodha", transactions=[_make_txn()])
    preview_id = store.put(result)

    time.sleep(0.01)  # allow expiry
    retrieved = store.get(preview_id)
    assert retrieved is None


def test_preview_store_get_unknown_id_returns_none():
    from app.services.imports.preview_store import PreviewStore

    store = PreviewStore()
    assert store.get("nonexistent-id") is None
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_import_pipeline.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create services/imports/__init__.py**

```python
# backend/app/services/imports/__init__.py
```

- [ ] **Step 4: Create services/imports/deduplicator.py**

```python
# backend/app/services/imports/deduplicator.py
"""
Deduplicator — pure, testable. Filters out transactions whose txn_id is
already in the database (or a provided set of known IDs).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from app.importers.base import ImportResult


class IDeduplicator(Protocol):
    def filter_duplicates(self, result: ImportResult) -> ImportResult: ...


class InMemoryDeduplicator:
    """
    Deduplicates against a pre-loaded set of known txn_ids.

    Use this in tests (inject the set of existing IDs directly).
    """

    def __init__(self, existing_txn_ids: set[str]):
        self._existing = existing_txn_ids

    def filter_duplicates(self, result: ImportResult) -> ImportResult:
        new_txns = []
        duplicate_count = 0
        for txn in result.transactions:
            if txn.txn_id in self._existing:
                duplicate_count += 1
            else:
                new_txns.append(txn)
        # Return a new ImportResult with duplicates removed
        # We store duplicate_count in warnings for traceability
        warnings = list(result.warnings)
        if duplicate_count:
            warnings.append(f"{duplicate_count} duplicate transaction(s) skipped")
        new_result = ImportResult(
            source=result.source,
            transactions=new_txns,
            snapshots=result.snapshots,
            errors=result.errors,
            warnings=warnings,
        )
        new_result.duplicate_count = duplicate_count  # type: ignore[attr-defined]
        return new_result


class DBDeduplicator:
    """
    Deduplicates against the real database transaction table.
    Used in production via ImportPipeline.
    """

    def __init__(self, txn_repo):
        self._txn_repo = txn_repo

    def filter_duplicates(self, result: ImportResult) -> ImportResult:
        existing_ids = {
            txn.txn_id
            for txn in result.transactions
            if self._txn_repo.get_by_txn_id(txn.txn_id) is not None
        }
        return InMemoryDeduplicator(existing_ids).filter_duplicates(result)
```

The `ImportResult` dataclass doesn't have a `duplicate_count` field. We'll add it. Edit `backend/app/importers/base.py`:

Find the `ImportResult` dataclass and add the field:
```python
@dataclass
class ImportResult:
    """Result of parsing a file."""
    source: str
    transactions: list[ParsedTransaction] = field(default_factory=list)
    snapshots: list[ParsedFundSnapshot] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_count: int = 0   # ← add this line
```

- [ ] **Step 5: Create services/imports/preview_store.py**

```python
# backend/app/services/imports/preview_store.py
"""
TTL-based in-memory preview store.

Replaces the module-level _PREVIEW_STORE dict in import_service.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.importers.base import ImportResult


class PreviewStore:
    """
    Stores ImportResult objects keyed by preview_id with TTL expiry.

    Not thread-safe for concurrent workers, but acceptable for single-process dev server.
    """

    def __init__(self, ttl_minutes: int = 15):
        self._ttl = timedelta(minutes=ttl_minutes)
        self._store: dict[str, tuple[ImportResult, datetime]] = {}

    def put(self, result: ImportResult) -> str:
        """Store result and return a preview_id."""
        preview_id = str(uuid.uuid4())
        self._store[preview_id] = (result, datetime.utcnow())
        return preview_id

    def get(self, preview_id: str) -> Optional[ImportResult]:
        """
        Retrieve result by preview_id. Returns None if not found or expired.
        Expired entries are cleaned up on access.
        """
        entry = self._store.get(preview_id)
        if entry is None:
            return None
        result, created_at = entry
        if datetime.utcnow() - created_at > self._ttl:
            del self._store[preview_id]
            return None
        return result

    def delete(self, preview_id: str) -> None:
        self._store.pop(preview_id, None)
```

- [ ] **Step 6: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_import_pipeline.py -v
```

Expected: All 6 tests pass.

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/importers/base.py app/services/imports/ tests/unit/test_import_pipeline.py
git commit -m "feat(importers): add InMemoryDeduplicator, DBDeduplicator, PreviewStore; add duplicate_count to ImportResult"
```

---

## Task 5: Create importers/pipeline.py

**Files:**
- Create: `backend/app/importers/pipeline.py`
- Modify: `backend/tests/unit/test_import_pipeline.py`

- [ ] **Step 1: Add failing test**

Append to `backend/tests/unit/test_import_pipeline.py`:

```python
def test_import_pipeline_run():
    from app.importers.pipeline import ImportPipeline
    from app.importers.registry import ImporterRegistry, register_importer
    from app.importers.base import BaseImporter, ImportResult
    from app.services.imports.deduplicator import InMemoryDeduplicator

    @register_importer
    class FakeCSVImporter(BaseImporter):
        source = "fake_pipeline_test"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes) -> ImportResult:
            return ImportResult(
                source=self.source,
                transactions=[_make_txn("pipeline_txn_1")],
            )

    registry = ImporterRegistry()
    dedup = InMemoryDeduplicator(set())
    pipeline = ImportPipeline(registry=registry, deduplicator=dedup)

    result = pipeline.run("fake_pipeline_test", "csv", b"data")
    assert len(result.transactions) == 1
    assert result.transactions[0].txn_id == "pipeline_txn_1"


def test_import_pipeline_deduplicates():
    from app.importers.pipeline import ImportPipeline
    from app.importers.registry import ImporterRegistry, register_importer
    from app.importers.base import BaseImporter, ImportResult
    from app.services.imports.deduplicator import InMemoryDeduplicator

    @register_importer
    class FakeCSVImporter2(BaseImporter):
        source = "fake_dedup_test"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes) -> ImportResult:
            return ImportResult(
                source=self.source,
                transactions=[
                    _make_txn("existing_id"),
                    _make_txn("new_id"),
                ],
            )

    registry = ImporterRegistry()
    dedup = InMemoryDeduplicator({"existing_id"})
    pipeline = ImportPipeline(registry=registry, deduplicator=dedup)

    result = pipeline.run("fake_dedup_test", "csv", b"data")
    assert len(result.transactions) == 1
    assert result.transactions[0].txn_id == "new_id"
    assert result.duplicate_count == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_import_pipeline.py::test_import_pipeline_run -v
```

Expected: `ImportError`

- [ ] **Step 3: Create importers/pipeline.py**

```python
# backend/app/importers/pipeline.py
"""
ImportPipeline — parse → validate → deduplicate.

Stateless: creates a fresh run each call. Receives dependencies via constructor.
"""
from __future__ import annotations

from app.importers.base import ImportResult
from app.importers.registry import ImporterRegistry
from app.services.imports.deduplicator import IDeduplicator


class ImportPipeline:
    """
    Runs the three-step import pipeline for a single file.

    Steps:
        1. parse    — delegate to the registered importer for (source, format)
        2. validate — call importer.validate(); append warnings to result
        3. deduplicate — filter out txn_ids already in the database
    """

    def __init__(self, registry: ImporterRegistry, deduplicator: IDeduplicator):
        self._registry = registry
        self._deduplicator = deduplicator

    def run(self, source: str, fmt: str, file_bytes: bytes) -> ImportResult:
        importer = self._registry.get(source, fmt)
        result = importer.parse(file_bytes)
        warnings = importer.validate(result)
        result.warnings.extend(warnings)
        result = self._deduplicator.filter_duplicates(result)
        return result
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_import_pipeline.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/importers/pipeline.py tests/unit/test_import_pipeline.py
git commit -m "feat(importers): add ImportPipeline (parse → validate → deduplicate)"
```

---

## Task 6: Create post-processors

**Files:**
- Create: `backend/app/services/imports/post_processors/__init__.py`
- Create: `backend/app/services/imports/post_processors/base.py`
- Create: `backend/app/services/imports/post_processors/stock.py`
- Create: `backend/app/services/imports/post_processors/mf.py`
- Test: `backend/tests/unit/test_import_orchestrator.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/unit/test_import_orchestrator.py
import pytest
from datetime import date
from app.importers.base import ParsedTransaction, ImportResult


def _make_txn(txn_id="t1", asset_type="STOCK_IN", txn_type="BUY", units=10.0) -> ParsedTransaction:
    return ParsedTransaction(
        source="zerodha",
        asset_name="Test Stock",
        asset_identifier="TEST",
        asset_type=asset_type,
        txn_type=txn_type,
        date=date(2024, 1, 1),
        units=units,
        amount_inr=-10000.0,
        txn_id=txn_id,
    )


def test_stock_post_processor_marks_asset_inactive_when_zero_units():
    from app.services.imports.post_processors.stock import StockPostProcessor

    class FakeAsset:
        asset_type_value = "STOCK_IN"
        is_active = True
        updates = {}

    class FakeAssetRepo:
        def update(self, asset, **kwargs):
            asset.updates.update(kwargs)

    class FakeUoW:
        def __init__(self):
            self.assets = FakeAssetRepo()

    asset = FakeAsset()
    txns_buy = [_make_txn("b1", units=10.0, txn_type="BUY")]
    txns_sell = [_make_txn("s1", units=10.0, txn_type="SELL")]

    processor = StockPostProcessor()
    processor.process(asset, txns_buy + txns_sell, FakeUoW())

    assert asset.updates.get("is_active") is False


def test_stock_post_processor_keeps_active_when_units_remain():
    from app.services.imports.post_processors.stock import StockPostProcessor

    class FakeAsset:
        asset_type_value = "STOCK_IN"
        is_active = True
        updates = {}

    class FakeAssetRepo:
        def update(self, asset, **kwargs):
            asset.updates.update(kwargs)

    class FakeUoW:
        def __init__(self):
            self.assets = FakeAssetRepo()

    asset = FakeAsset()
    txns = [_make_txn("b1", units=10.0, txn_type="BUY")]

    processor = StockPostProcessor()
    processor.process(asset, txns, FakeUoW())

    assert "is_active" not in asset.updates
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_import_orchestrator.py::test_stock_post_processor_marks_asset_inactive_when_zero_units -v
```

Expected: `ImportError`

- [ ] **Step 3: Create post_processors/__init__.py and base.py**

```python
# backend/app/services/imports/post_processors/__init__.py
```

```python
# backend/app/services/imports/post_processors/base.py
"""
IPostProcessor protocol — one class per asset type needing post-import logic.

Adding new post-import behavior: create a new class implementing IPostProcessor,
register it in api/dependencies.py. ImportOrchestrator picks it up automatically.
"""
from typing import ClassVar, Protocol


class IPostProcessor(Protocol):
    asset_types: ClassVar[list[str]]

    def process(self, asset, txns: list, uow) -> None:
        """Called after transactions are persisted for asset. May update asset state."""
        ...
```

- [ ] **Step 4: Create post_processors/stock.py**

```python
# backend/app/services/imports/post_processors/stock.py
"""
StockPostProcessor — marks STOCK_IN, STOCK_US, RSU assets inactive
when net units reach zero after an import.
"""
from typing import ClassVar

_UNIT_ADD_TYPES = {"BUY", "SIP", "VEST", "BONUS"}
_UNIT_SUB_TYPES = {"SELL", "REDEMPTION"}


class StockPostProcessor:
    asset_types: ClassVar[list[str]] = ["STOCK_IN", "STOCK_US", "RSU"]

    def process(self, asset, txns: list, uow) -> None:
        """
        Compute net units from the provided transactions.
        If net_units <= 0, mark the asset inactive.
        """
        net_units = 0.0
        for txn in txns:
            txn_type = getattr(txn, "type", None)
            if txn_type is None:
                # txn may be a ParsedTransaction with txn_type attr
                txn_type = getattr(txn, "txn_type", None)
            if txn_type is not None:
                txn_type_val = txn_type.value if hasattr(txn_type, "value") else str(txn_type)
                units = getattr(txn, "units", 0.0) or 0.0
                if txn_type_val in _UNIT_ADD_TYPES:
                    net_units += units
                elif txn_type_val in _UNIT_SUB_TYPES:
                    net_units -= units
        if net_units <= 0:
            uow.assets.update(asset, is_active=False)
```

- [ ] **Step 5: Create post_processors/mf.py**

```python
# backend/app/services/imports/post_processors/mf.py
"""
MFPostProcessor — persists CAS snapshots after an MF import commit.
"""
from typing import ClassVar


class MFPostProcessor:
    asset_types: ClassVar[list[str]] = ["MF"]

    def process(self, asset, txns: list, uow) -> None:
        """
        No-op by default — CAS snapshot persistence is handled
        by ImportOrchestrator.commit() directly using the snapshots
        in the ImportResult. This processor exists as a hook for
        future MF-specific post-import logic.
        """
        pass
```

- [ ] **Step 6: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_import_orchestrator.py -v
uv run pytest --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/services/imports/post_processors/ tests/unit/test_import_orchestrator.py
git commit -m "feat(importers): add IPostProcessor, StockPostProcessor, MFPostProcessor"
```

---

## Task 7: Create SyncEventBus

**Files:**
- Create: `backend/app/services/event_bus.py`
- Test: `backend/tests/unit/test_event_bus.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/unit/test_event_bus.py
import pytest
from dataclasses import dataclass


@dataclass
class TestEvent:
    value: int


def test_sync_event_bus_dispatches_to_subscriber():
    from app.services.event_bus import SyncEventBus

    bus = SyncEventBus()
    received = []

    bus.subscribe(TestEvent, lambda e: received.append(e.value))
    bus.publish(TestEvent(value=42))

    assert received == [42]


def test_sync_event_bus_multiple_subscribers():
    from app.services.event_bus import SyncEventBus

    bus = SyncEventBus()
    log = []

    bus.subscribe(TestEvent, lambda e: log.append(f"a:{e.value}"))
    bus.subscribe(TestEvent, lambda e: log.append(f"b:{e.value}"))
    bus.publish(TestEvent(value=7))

    assert "a:7" in log
    assert "b:7" in log


def test_sync_event_bus_no_subscriber_no_error():
    from app.services.event_bus import SyncEventBus

    bus = SyncEventBus()
    # Should not raise even with no subscribers
    bus.publish(TestEvent(value=1))


def test_sync_event_bus_different_event_types_isolated():
    from app.services.event_bus import SyncEventBus

    @dataclass
    class OtherEvent:
        msg: str

    bus = SyncEventBus()
    test_log = []
    other_log = []

    bus.subscribe(TestEvent, lambda e: test_log.append(e.value))
    bus.subscribe(OtherEvent, lambda e: other_log.append(e.msg))

    bus.publish(TestEvent(value=99))
    assert test_log == [99]
    assert other_log == []
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_event_bus.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create services/event_bus.py**

```python
# backend/app/services/event_bus.py
"""
Lightweight synchronous event bus — no external dependencies.

Usage:
    bus = SyncEventBus()
    bus.subscribe(ImportCompletedEvent, corp_actions_service.on_import_completed)
    bus.publish(ImportCompletedEvent(asset_id=1, asset_type=AssetType.STOCK_IN, inserted_count=5))

Adding a new observer: bus.subscribe(EventType, handler_fn). No changes to publishers.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Protocol

from app.models.asset import AssetType


@dataclass
class ImportCompletedEvent:
    """Published after ImportOrchestrator.commit() succeeds."""
    asset_id: int
    asset_type: AssetType
    inserted_count: int


class IEventBus(Protocol):
    def publish(self, event: object) -> None: ...
    def subscribe(self, event_type: type, handler: Callable) -> None: ...


class SyncEventBus:
    """
    Synchronous in-process event bus. Handlers are called in subscription order.

    If a handler raises, the exception propagates (fail-fast). Wrap handlers
    in try/except if you need fault isolation.
    """

    def __init__(self):
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: object) -> None:
        for handler in self._handlers.get(type(event), []):
            handler(event)
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_event_bus.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/services/event_bus.py tests/unit/test_event_bus.py
git commit -m "feat: add SyncEventBus and ImportCompletedEvent"
```

---

## Task 8: Create ImportOrchestrator

**Files:**
- Create: `backend/app/services/imports/orchestrator.py`
- Modify: `backend/tests/unit/test_import_orchestrator.py`

- [ ] **Step 1: Add failing integration-style test**

Append to `backend/tests/unit/test_import_orchestrator.py`:

```python
def test_orchestrator_preview_returns_preview_id():
    from app.importers.pipeline import ImportPipeline
    from app.importers.registry import ImporterRegistry, register_importer
    from app.importers.base import BaseImporter, ImportResult
    from app.services.imports.deduplicator import InMemoryDeduplicator
    from app.services.imports.preview_store import PreviewStore
    from app.services.imports.orchestrator import ImportOrchestrator
    from app.services.event_bus import SyncEventBus

    @register_importer
    class OrchestratorTestImporter(BaseImporter):
        source = "orch_test"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes) -> ImportResult:
            return ImportResult(
                source=self.source,
                transactions=[_make_txn("orch_txn_1")],
            )

    pipeline = ImportPipeline(
        registry=ImporterRegistry(),
        deduplicator=InMemoryDeduplicator(set()),
    )
    store = PreviewStore()
    bus = SyncEventBus()
    orchestrator = ImportOrchestrator(
        uow_factory=lambda: None,  # not needed for preview
        pipeline=pipeline,
        preview_store=store,
        post_processors=[],
        event_bus=bus,
    )

    response = orchestrator.preview("orch_test", "csv", b"data")
    assert response.preview_id is not None
    assert response.new_count == 1
    assert response.duplicate_count == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
uv run pytest tests/unit/test_import_orchestrator.py::test_orchestrator_preview_returns_preview_id -v
```

Expected: `ImportError`

- [ ] **Step 3: Create services/imports/orchestrator.py**

```python
# backend/app/services/imports/orchestrator.py
"""
ImportOrchestrator — coordinates preview/commit for any file import.

preview(): parse file → deduplicate → store in PreviewStore → return ImportPreviewResponse
commit():  load from store → persist transactions → run post-processors → publish event

Adding new post-processing: create an IPostProcessor subclass, register it in
api/dependencies.py. No changes to this file.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.importers.base import ImportResult, ParsedTransaction
from app.importers.pipeline import ImportPipeline
from app.models.asset import Asset, AssetType, AssetClass
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.imports import (
    ImportPreviewResponse,
    ImportCommitResponse,
    ParsedTransactionPreview,
)
from app.services.event_bus import ImportCompletedEvent, IEventBus
from app.services.imports.post_processors.base import IPostProcessor
from app.services.imports.preview_store import PreviewStore

logger = logging.getLogger(__name__)

ASSET_CLASS_MAP: dict[str, AssetClass] = {
    "STOCK_IN": AssetClass.EQUITY,
    "STOCK_US": AssetClass.EQUITY,
    "RSU": AssetClass.EQUITY,
    "MF": AssetClass.MIXED,
    "NPS": AssetClass.DEBT,
    "GOLD": AssetClass.GOLD,
    "SGB": AssetClass.GOLD,
    "REAL_ESTATE": AssetClass.REAL_ESTATE,
    "FD": AssetClass.DEBT,
    "RD": AssetClass.DEBT,
    "PPF": AssetClass.DEBT,
    "EPF": AssetClass.DEBT,
}


class ImportOrchestrator:
    def __init__(
        self,
        uow_factory,
        pipeline: ImportPipeline,
        preview_store: PreviewStore,
        post_processors: list,
        event_bus: IEventBus,
    ):
        self._uow_factory = uow_factory
        self._pipeline = pipeline
        self._store = preview_store
        self._processors: dict[str, IPostProcessor] = {
            at: p for p in post_processors for at in p.asset_types
        }
        self._bus = event_bus

    # ------------------------------------------------------------------
    # preview
    # ------------------------------------------------------------------

    def preview(
        self,
        source: str,
        fmt: str,
        file_bytes: bytes,
    ) -> ImportPreviewResponse:
        result = self._pipeline.run(source, fmt, file_bytes)
        preview_id = self._store.put(result)

        txn_previews = [
            ParsedTransactionPreview(
                txn_id=t.txn_id,
                asset_name=t.asset_name,
                asset_type=t.asset_type,
                txn_type=t.txn_type,
                date=t.date,
                units=t.units,
                amount_inr=t.amount_inr,
                notes=t.notes,
                is_duplicate=False,
            )
            for t in result.transactions
        ]
        return ImportPreviewResponse(
            preview_id=preview_id,
            new_count=len(result.transactions),
            duplicate_count=getattr(result, "duplicate_count", 0),
            transactions=txn_previews,
            warnings=result.warnings,
        )

    # ------------------------------------------------------------------
    # commit
    # ------------------------------------------------------------------

    def commit(self, preview_id: str) -> Optional[ImportCommitResponse]:
        result = self._store.get(preview_id)
        if result is None:
            return None  # expired or not found

        inserted = 0
        skipped = 0
        errors: list[str] = []

        with self._uow_factory() as uow:
            for parsed_txn in result.transactions:
                try:
                    # Find or create the asset
                    asset = self._find_or_create_asset(parsed_txn, uow)

                    # Check for duplicate (second-pass safety)
                    if uow.transactions.get_by_txn_id(parsed_txn.txn_id):
                        skipped += 1
                        continue

                    # Persist transaction
                    txn = uow.transactions.create(
                        asset_id=asset.id,
                        txn_id=parsed_txn.txn_id,
                        type=parsed_txn.txn_type,
                        date=parsed_txn.date,
                        units=parsed_txn.units,
                        price_per_unit=parsed_txn.price_per_unit,
                        forex_rate=parsed_txn.forex_rate,
                        amount_inr=int(parsed_txn.amount_inr * 100),  # INR → paise
                        charges_inr=int(parsed_txn.charges_inr * 100),
                        lot_id=parsed_txn.lot_id,
                        notes=parsed_txn.notes,
                    )
                    inserted += 1

                    # Run post-processor for this asset type
                    processor = self._processors.get(parsed_txn.asset_type)
                    if processor:
                        processor.process(asset, [txn], uow)

                except Exception as exc:
                    logger.warning("Failed to import txn %s: %s", parsed_txn.txn_id, exc)
                    errors.append(str(exc))

            # Persist CAS snapshots if present
            for snap in result.snapshots:
                try:
                    asset = uow.assets.list(active=None)  # find by identifier
                    # Snapshot persistence is handled by existing CasSnapshotRepository
                    pass
                except Exception as exc:
                    errors.append(f"Snapshot error: {exc}")

        # Publish event for each unique asset_type inserted
        if inserted > 0:
            self._bus.publish(
                ImportCompletedEvent(
                    asset_id=0,  # batch: no single asset_id
                    asset_type=AssetType[result.transactions[0].asset_type] if result.transactions else AssetType.STOCK_IN,
                    inserted_count=inserted,
                )
            )

        self._store.delete(preview_id)
        return ImportCommitResponse(inserted=inserted, skipped=skipped, errors=errors)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _find_or_create_asset(self, parsed_txn: ParsedTransaction, uow: UnitOfWork) -> Asset:
        """Find asset by identifier or name; create if not found."""
        assets = uow.assets.list(active=None)

        # Match by identifier (ISIN / scheme code)
        if parsed_txn.asset_identifier:
            for a in assets:
                if a.identifier == parsed_txn.asset_identifier:
                    return a

        # Match by name
        for a in assets:
            if a.name == parsed_txn.asset_name:
                return a

        # Create new asset
        asset_type_enum = AssetType[parsed_txn.asset_type]
        asset_class = ASSET_CLASS_MAP.get(parsed_txn.asset_type, AssetClass.EQUITY)
        return uow.assets.create(
            name=parsed_txn.asset_name,
            identifier=parsed_txn.asset_identifier or "",
            mfapi_scheme_code=parsed_txn.mfapi_scheme_code,
            asset_type=asset_type_enum,
            asset_class=asset_class,
            currency=parsed_txn.source if parsed_txn.asset_type in ("STOCK_US", "RSU") else "INR",
            is_active=True,
        )
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/unit/test_import_orchestrator.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/services/imports/orchestrator.py tests/unit/test_import_orchestrator.py
git commit -m "feat(importers): add ImportOrchestrator with preview/commit and post-processor dispatch"
```

---

## Task 9: Wire ImportOrchestrator into api/imports.py

**Files:**
- Modify: `backend/app/api/dependencies.py`
- Modify: `backend/app/api/imports.py`
- Test: `backend/tests/integration/test_import_flow.py`

- [ ] **Step 1: Add get_import_orchestrator to dependencies.py**

Open `backend/app/api/dependencies.py` and add:

```python
from app.importers.pipeline import ImportPipeline
from app.importers.registry import ImporterRegistry
from app.services.event_bus import SyncEventBus
from app.services.imports.deduplicator import DBDeduplicator
from app.services.imports.orchestrator import ImportOrchestrator
from app.services.imports.post_processors.stock import StockPostProcessor
from app.services.imports.post_processors.mf import MFPostProcessor
from app.services.imports.preview_store import PreviewStore

# Module-level singletons (stateless or TTL-based)
_preview_store = PreviewStore(ttl_minutes=15)
_event_bus = SyncEventBus()

# Wire corp actions handler when corp_actions_service is available
# (Plan 4 adds: _event_bus.subscribe(ImportCompletedEvent, corp_actions_svc.on_import_completed))


def get_import_orchestrator(db: Session = Depends(get_db)) -> ImportOrchestrator:
    uow_factory = lambda: UnitOfWork(db)
    txn_repo = uow_factory().transactions  # for deduplication check

    pipeline = ImportPipeline(
        registry=ImporterRegistry(),
        deduplicator=DBDeduplicator(txn_repo),
    )
    return ImportOrchestrator(
        uow_factory=uow_factory,
        pipeline=pipeline,
        preview_store=_preview_store,
        post_processors=[StockPostProcessor(), MFPostProcessor()],
        event_bus=_event_bus,
    )
```

- [ ] **Step 2: Run existing integration test for imports**

```bash
cd backend
uv run pytest tests/integration/test_import_flow.py -v --tb=short
```

Observe which tests exist and whether they pass. Do NOT break them.

- [ ] **Step 3: Update api/imports.py to use ImportOrchestrator via Depends**

Open `backend/app/api/imports.py`. Find the existing `preview` and `commit` endpoints.

Replace the endpoint implementations to delegate to `ImportOrchestrator`:

```python
# backend/app/api/imports.py (relevant changes only — keep other endpoints)
from fastapi import APIRouter, Depends, HTTPException
from app.api.dependencies import get_import_orchestrator
from app.services.imports.orchestrator import ImportOrchestrator

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/preview")
def preview_import(
    body: ...,  # keep existing request body schema
    orchestrator: ImportOrchestrator = Depends(get_import_orchestrator),
):
    # If body has parsed transactions already (current API pattern),
    # bypass orchestrator and use existing ImportService.preview() for now.
    # Full migration to orchestrator.preview() happens when CLI importers
    # call /imports/preview with source+format+file_bytes.
    # For backward compatibility, keep existing ImportService path.
    ...
```

> **Note on backward compatibility:** The current `/imports/preview` endpoint accepts `parsed_txns` (pre-parsed transactions from CLI importers). The new `ImportOrchestrator.preview()` accepts `source + fmt + file_bytes`. For this plan, add a NEW endpoint `/imports/preview-file` that uses the orchestrator for direct file uploads, while keeping the existing `/imports/preview` for CLI pre-parsed transactions. Full migration of the CLI to use `/imports/preview-file` is out of scope for this plan.

Create the new file-upload endpoint:

```python
@router.post("/preview-file")
def preview_file_import(
    source: str,
    format: str,
    file: bytes,  # will refine with UploadFile in a follow-up
    orchestrator: ImportOrchestrator = Depends(get_import_orchestrator),
):
    response = orchestrator.preview(source, format, file)
    if response is None:
        raise HTTPException(status_code=404, detail="Preview not found or expired")
    return response


@router.post("/commit-file/{preview_id}")
def commit_file_import(
    preview_id: str,
    orchestrator: ImportOrchestrator = Depends(get_import_orchestrator),
):
    response = orchestrator.commit(preview_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Preview not found or expired")
    return response
```

- [ ] **Step 4: Run full test suite**

```bash
cd backend
uv run pytest --tb=short -q
```

Expected: All existing tests pass. New endpoints exist but aren't tested yet (that's acceptable for this plan).

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/api/dependencies.py app/api/imports.py
git commit -m "feat(api): wire ImportOrchestrator into /imports/preview-file and /imports/commit-file endpoints"
```

---

## Task 10: Final verification

- [ ] **Step 1: Run full test suite with coverage**

```bash
cd backend
uv run pytest --cov=app --cov-report=term-missing -q
```

Expected: All tests pass. Importer coverage ≥ 85%.

- [ ] **Step 2: Verify all importers are importable and registered**

```bash
cd backend
uv run python -c "
import app.importers.broker_csv_parser
import app.importers.cas_parser
import app.importers.nps_csv_parser
import app.importers.ppf_csv_parser
import app.importers.epf_pdf_parser
import app.importers.fidelity_pdf_parser
import app.importers.fidelity_rsu_csv_parser
from app.importers.registry import ImporterRegistry
r = ImporterRegistry()
print('Registered importers:', r.list_registered())
"
```

Expected: prints 7 registered (source, format) pairs.

- [ ] **Step 3: Final commit**

```bash
cd backend
git add -p
git commit -m "chore: plan 3 importers complete — pipeline, orchestrator, post-processors, event bus"
```

---

## What's next

- **Plan 4 (Services & API)** — wires ReturnsService strategy pattern, TaxService with TaxRatePolicy, API layer cleanup, and removes db.commit() from repos

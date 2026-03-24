# MF Scheme Category Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically classify MF assets as EQUITY or DEBT using mfapi.in scheme_category, fix NPS assets to be stored as DEBT, and display fund sub-type in the MF holdings table.

**Architecture:** Add `scheme_category` column to `assets` table; fix `ASSET_CLASS_MAP` for NPS; migrate existing NPS DB rows; extend `MFAPIFetcher` to capture `scheme_category` from the non-`/latest` endpoint; `PriceService` persists it and updates `asset_class` via a pure `classify_mf()` engine function; frontend adds a "Category" column to the MF holdings table.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Alembic, pytest; Next.js App Router, TypeScript.

**Spec:** `docs/superpowers/specs/2026-03-24-mf-scheme-category-design.md`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `backend/app/engine/mf_classifier.py` | **Create** | Pure `classify_mf(scheme_category)` function |
| `backend/tests/unit/test_mf_classifier.py` | **Create** | Unit tests for `classify_mf` |
| `backend/app/models/asset.py` | **Modify** | Add `scheme_category` column |
| `backend/alembic/versions/xxxx_add_scheme_category_fix_nps.py` | **Create** | ADD COLUMN + data-fix NPS rows |
| `backend/app/services/import_service.py` | **Modify** | `ASSET_CLASS_MAP`: NPS → DEBT |
| `backend/app/services/price_feed.py` | **Modify** | Switch to non-`/latest` URL, set `_resolved_scheme_category` |
| `backend/tests/unit/test_price_feed.py` | **Modify** | Tests for scheme_category capture + URL change |
| `backend/app/services/price_service.py` | **Modify** | Persist `_resolved_scheme_category` in both `refresh_asset` and `refresh_all` |
| `backend/tests/integration/test_mf_classification_api.py` | **Create** | Integration tests |
| `backend/app/schemas/asset.py` | **Modify** | Add `scheme_category` to `AssetResponse` |
| `frontend/types/index.ts` | **Modify** | Add `scheme_category: string \| null` to `Asset` |
| `frontend/lib/formatters.ts` | **Modify** | Add `formatMFCategory()` |
| `frontend/components/domain/HoldingsTable.tsx` | **Modify** | Add `showCategory` prop + Category column |
| `frontend/app/mutual-funds/page.tsx` | **Modify** | Pass `showCategory` to `<HoldingsTable>` |

---

## Task 1: Pure `classify_mf` engine function (TDD)

**Files:**
- Create: `backend/app/engine/mf_classifier.py`
- Create: `backend/tests/unit/test_mf_classifier.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_mf_classifier.py`:

```python
import pytest
from app.engine.mf_classifier import classify_mf
from app.models.asset import AssetClass


def test_debt_scheme_returns_debt():
    assert classify_mf("Debt Scheme - Liquid Fund") == AssetClass.DEBT

def test_equity_scheme_returns_equity():
    assert classify_mf("Equity Scheme - Large Cap Fund") == AssetClass.EQUITY

def test_hybrid_scheme_returns_equity():
    assert classify_mf("Hybrid Scheme - Balanced Advantage Fund") == AssetClass.EQUITY

def test_other_scheme_returns_equity():
    assert classify_mf("Other Scheme - Index Funds") == AssetClass.EQUITY

def test_solution_oriented_returns_equity():
    assert classify_mf("Solution Oriented Scheme - Childrens Fund") == AssetClass.EQUITY

def test_none_returns_equity():
    assert classify_mf(None) == AssetClass.EQUITY

def test_empty_string_returns_equity():
    assert classify_mf("") == AssetClass.EQUITY

def test_case_insensitive():
    assert classify_mf("DEBT SCHEME - Gilt Fund") == AssetClass.DEBT
```

- [ ] **Step 2: Run to confirm RED**

```bash
cd backend && pytest tests/unit/test_mf_classifier.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — file doesn't exist yet.

- [ ] **Step 3: Implement `mf_classifier.py`**

Create `backend/app/engine/mf_classifier.py`:

```python
from app.models.asset import AssetClass


def classify_mf(scheme_category: str | None) -> AssetClass:
    """Derive AssetClass from mfapi.in scheme_category string.

    Debt Scheme → DEBT.
    Everything else (Equity, Hybrid, Other, Solution Oriented, unknown) → EQUITY.
    """
    if not scheme_category:
        return AssetClass.EQUITY
    if scheme_category.lower().startswith("debt scheme"):
        return AssetClass.DEBT
    return AssetClass.EQUITY
```

- [ ] **Step 4: Run to confirm GREEN**

```bash
cd backend && pytest tests/unit/test_mf_classifier.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/engine/mf_classifier.py tests/unit/test_mf_classifier.py
git commit -m "feat: add classify_mf engine function for MF asset class derivation"
```

---

## Task 2: DB migration — add `scheme_category` column + fix NPS rows

**Files:**
- Modify: `backend/app/models/asset.py`
- Create: `backend/alembic/versions/<rev>_add_scheme_category_fix_nps.py`

- [ ] **Step 1: Add `scheme_category` to the Asset model**

In `backend/app/models/asset.py`, add after line 37 (`mfapi_scheme_code`):

```python
scheme_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

- [ ] **Step 2: Generate Alembic migration**

```bash
cd backend && alembic revision --autogenerate -m "add_scheme_category_fix_nps_asset_class"
```

This creates a new file in `backend/alembic/versions/`. Open it.

- [ ] **Step 3: Edit the migration to also fix NPS rows**

The autogenerated `upgrade()` will contain the `add_column`. Add the data migration immediately after:

```python
def upgrade() -> None:
    op.add_column('assets', sa.Column('scheme_category', sa.String(length=100), nullable=True))
    # Fix existing NPS assets: MIXED → DEBT
    op.execute("UPDATE assets SET asset_class = 'DEBT' WHERE asset_type = 'NPS'")


def downgrade() -> None:
    op.execute("UPDATE assets SET asset_class = 'MIXED' WHERE asset_type = 'NPS'")
    op.drop_column('assets', 'scheme_category')
```

- [ ] **Step 4: Apply migration**

```bash
cd backend && alembic upgrade head
```

Expected: no errors.

- [ ] **Step 5: Verify migration correctness (NPS rows fixed)**

```bash
cd backend && python -c "
from app.database import SessionLocal
from app.models.asset import Asset, AssetType, AssetClass
db = SessionLocal()
nps = db.query(Asset).filter(Asset.asset_type == AssetType.NPS).all()
for a in nps:
    assert a.asset_class == AssetClass.DEBT, f'{a.name} still has {a.asset_class}'
print(f'OK: {len(nps)} NPS assets all have DEBT class')
db.close()
"
```

Expected: prints `OK: N NPS assets all have DEBT class` (or `OK: 0` if no NPS assets exist yet — which is fine for a fresh DB).

- [ ] **Step 6: Commit**

```bash
git add app/models/asset.py alembic/versions/
git commit -m "feat: add scheme_category column and fix NPS asset_class to DEBT via migration"
```

---

## Task 3: Fix `ASSET_CLASS_MAP` for NPS at import time

**Files:**
- Modify: `backend/app/services/import_service.py:33`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_import_service.py` with:

> **Note:** `POST /assets` requires explicit `asset_class`, so the automatic classification via `ASSET_CLASS_MAP` can only be tested by querying the map directly. `test_mf_maps_to_mixed` is a guard/regression test (already GREEN before any code change) — it ensures we don't accidentally break MF classification while fixing NPS.

```python
from app.services.import_service import ASSET_CLASS_MAP
from app.models.asset import AssetClass

def test_nps_maps_to_debt():
    assert ASSET_CLASS_MAP["NPS"] == AssetClass.DEBT

def test_mf_maps_to_mixed():
    """MF stays MIXED in the map; classification happens via price feed."""
    assert ASSET_CLASS_MAP["MF"] == AssetClass.MIXED
```

- [ ] **Step 2: Run to confirm RED**

```bash
cd backend && pytest tests/unit/test_import_service.py::test_nps_maps_to_debt -v
```

Expected: `AssertionError` — currently `MIXED`.

- [ ] **Step 3: Fix `ASSET_CLASS_MAP`**

In `backend/app/services/import_service.py`, change line 34:

```python
# Before:
"NPS": AssetClass.MIXED,
# After:
"NPS": AssetClass.DEBT,
```

- [ ] **Step 4: Run to confirm GREEN**

```bash
cd backend && pytest tests/unit/test_import_service.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/import_service.py tests/unit/test_import_service.py
git commit -m "fix: set NPS asset_class to DEBT in ASSET_CLASS_MAP"
```

---

## Task 4: `MFAPIFetcher` — switch endpoint + capture `scheme_category`

**Files:**
- Modify: `backend/app/services/price_feed.py:48-56`
- Modify: `backend/tests/unit/test_price_feed.py`

- [ ] **Step 1: Write failing tests**

In `backend/tests/unit/test_price_feed.py`, add to `TestMFAPIFetcher`:

```python
def test_fetch_uses_non_latest_url(self):
    """Fetcher must call /{scheme_code} not /{scheme_code}/latest to get meta."""
    asset = make_mock_asset(asset_type=AssetType.MF, mfapi_scheme_code="125497")
    mock_response = {
        "status": "SUCCESS",
        "meta": {"scheme_category": "Equity Scheme - Large Cap Fund"},
        "data": [{"date": "19-03-2026", "nav": "19.855"}]
    }
    with patch("app.services.price_feed.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        fetcher = MFAPIFetcher()
        fetcher.fetch(asset)
    called_url = mock_get.call_args[0][0]
    assert called_url.endswith("/125497"), f"Expected URL ending in /125497, got: {called_url}"
    assert "/latest" not in called_url

def test_fetch_sets_resolved_scheme_category(self):
    """fetch() sets asset._resolved_scheme_category when meta.scheme_category present."""
    asset = make_mock_asset(asset_type=AssetType.MF, mfapi_scheme_code="125497")
    mock_response = {
        "status": "SUCCESS",
        "meta": {"scheme_category": "Equity Scheme - Large Cap Fund"},
        "data": [{"date": "19-03-2026", "nav": "19.855"}]
    }
    with patch("app.services.price_feed.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        fetcher = MFAPIFetcher()
        fetcher.fetch(asset)
    assert asset._resolved_scheme_category == "Equity Scheme - Large Cap Fund"

def test_fetch_no_scheme_category_in_meta_does_not_set_attribute(self):
    """fetch() does not set _resolved_scheme_category when meta lacks scheme_category."""
    asset = make_mock_asset(asset_type=AssetType.MF, mfapi_scheme_code="125497")
    mock_response = {
        "status": "SUCCESS",
        "meta": {},
        "data": [{"date": "19-03-2026", "nav": "19.855"}]
    }
    with patch("app.services.price_feed.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        fetcher = MFAPIFetcher()
        fetcher.fetch(asset)
    assert not hasattr(asset, "_resolved_scheme_category")
```

- [ ] **Step 2: Run to confirm RED**

```bash
cd backend && pytest tests/unit/test_price_feed.py::TestMFAPIFetcher::test_fetch_uses_non_latest_url tests/unit/test_price_feed.py::TestMFAPIFetcher::test_fetch_sets_resolved_scheme_category -v
```

Expected: `AssertionError` on URL check (still uses `/latest`); attribute not set.

- [ ] **Step 3: Update `MFAPIFetcher.fetch()` in `price_feed.py`**

Replace lines 48-56 in `backend/app/services/price_feed.py`:

```python
            resp = httpx.get(f"{self.BASE_URL}/{scheme_code}", timeout=10)
            if resp.status_code != 200:
                logger.warning("MFAPIFetcher: HTTP %s for scheme %s", resp.status_code, scheme_code)
                return None
            data = resp.json()
            if data.get("status") != "SUCCESS" or not data.get("data"):
                return None
            nav = float(data["data"][0]["nav"])
            scheme_category = data.get("meta", {}).get("scheme_category")
            if scheme_category:
                asset._resolved_scheme_category = scheme_category
            return PriceResult(price_inr=nav, source="mfapi")
```

- [ ] **Step 4: Fix existing tests broken by the URL change**

After the URL switch, `data.get("status") != "SUCCESS"` is now checked on the nav response. The existing `test_fetch_falls_back_to_search_when_no_scheme_code` has a `nav_response` without a `"status"` key — it will now return `None` (status check fails). Fix by adding `"status": "SUCCESS"` to its `nav_response`:

Find in `test_price_feed.py` (around line 51-53):
```python
        nav_response = {
            "status": "SUCCESS",  # ← ensure this is present
            "data": [{"date": "19-03-2026", "nav": "19.855"}]
        }
```

Also update the comment on line 39 of `test_fetch_success_with_scheme_code`:
```python
        # Should call /mf/125497 directly (scheme_code known)
```

- [ ] **Step 5: Run full `TestMFAPIFetcher` suite to confirm all GREEN**

```bash
cd backend && pytest tests/unit/test_price_feed.py::TestMFAPIFetcher -v
```

Expected: all tests PASS (including the 3 new ones).

- [ ] **Step 6: Commit**

```bash
git add app/services/price_feed.py tests/unit/test_price_feed.py
git commit -m "feat: MFAPIFetcher captures scheme_category from non-latest endpoint"
```

---

## Task 5: `PriceService` — persist `scheme_category` + update `asset_class`

**Files:**
- Modify: `backend/app/services/price_service.py:54-57` (refresh_asset) and `:118-121` (refresh_all)
- Create: `backend/tests/integration/test_mf_classification_api.py`

- [ ] **Step 1: Write failing integration tests**

Create `backend/tests/integration/test_mf_classification_api.py`:

```python
"""Integration tests for MF scheme_category classification via price refresh."""
from unittest.mock import patch
from tests.factories import make_asset, make_transaction
from app.services.price_feed import PriceResult


def _mf_nav_response(scheme_category: str) -> dict:
    return {
        "status": "SUCCESS",
        "meta": {"scheme_category": scheme_category},
        "data": [{"date": "01-01-2024", "nav": "50.0"}],
    }


def test_price_refresh_sets_debt_class_for_debt_mf(client, db):
    """After refresh, MF with Debt scheme_category gets asset_class=DEBT."""
    asset = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="MIXED", name="HDFC Liquid Fund",
        identifier="INF179L", mfapi_scheme_code="119551"
    )).json()

    with patch("app.services.price_feed.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = _mf_nav_response("Debt Scheme - Liquid Fund")
        client.post(f"/prices/{asset['id']}/refresh")

    refreshed = client.get(f"/assets/{asset['id']}").json()
    assert refreshed["asset_class"] == "DEBT"
    assert refreshed["scheme_category"] == "Debt Scheme - Liquid Fund"


def test_price_refresh_sets_equity_class_for_hybrid_mf(client, db):
    """After refresh, MF with Hybrid scheme_category gets asset_class=EQUITY."""
    asset = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="MIXED", name="HDFC Balanced Fund",
        identifier="INF179H", mfapi_scheme_code="119552"
    )).json()

    with patch("app.services.price_feed.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = _mf_nav_response("Hybrid Scheme - Balanced Advantage Fund")
        client.post(f"/prices/{asset['id']}/refresh")

    refreshed = client.get(f"/assets/{asset['id']}").json()
    assert refreshed["asset_class"] == "EQUITY"
    assert refreshed["scheme_category"] == "Hybrid Scheme - Balanced Advantage Fund"


def test_scheme_category_in_asset_response(client, db):
    """scheme_category field is present in GET /assets/{id} response."""
    asset = client.post("/assets", json=make_asset(
        asset_type="MF", asset_class="MIXED", name="Test MF",
        identifier="INF999X", mfapi_scheme_code="999999"
    )).json()
    assert "scheme_category" in asset
    assert asset["scheme_category"] is None  # before any refresh


def test_scheme_category_not_writable_via_create(client):
    """scheme_category sent in POST /assets is silently ignored.

    Guard test: `scheme_category` is not in AssetCreate, so it is never
    written via the API. This test never produces a RED signal — it verifies
    correct structural behaviour rather than a code change.
    """
    payload = make_asset(asset_type="MF", asset_class="MIXED", name="Test MF2", identifier="INF999Y")
    payload["scheme_category"] = "Equity Scheme - Injected"
    asset = client.post("/assets", json=payload).json()
    assert asset.get("scheme_category") is None
```

- [ ] **Step 2: Run to confirm RED**

```bash
cd backend && pytest tests/integration/test_mf_classification_api.py -v
```

Expected: The first three tests fail (`scheme_category` not in response yet). `test_scheme_category_not_writable_via_create` may pass immediately — that is expected (it's a guard test, not a TDD test).

- [ ] **Step 3: Add `scheme_category` to `AssetResponse` schema**

In `backend/app/schemas/asset.py`, add to `AssetResponse`:

```python
scheme_category: Optional[str] = None
```

(Do NOT add to `AssetCreate` or `AssetUpdate`.)

- [ ] **Step 4: Update `PriceService.refresh_asset()` to persist `scheme_category`**

In `backend/app/services/price_service.py`, there are two existing blocks in `refresh_asset()`:
- Lines 54-57: persist `_resolved_scheme_code`
- Lines 59-62: persist `_resolved_nps_scheme_code`

Add the new block **after line 62** (after the NPS block, not before it):

```python
        # Persist scheme_category and reclassify asset_class for MF assets
        if hasattr(asset, "_resolved_scheme_category") and asset._resolved_scheme_category:
            from app.engine.mf_classifier import classify_mf
            asset.scheme_category = asset._resolved_scheme_category
            asset.asset_class = classify_mf(asset.scheme_category)
            self.db.commit()
```

- [ ] **Step 5: Update `PriceService.refresh_all()` to persist `scheme_category`**

In `backend/app/services/price_service.py`, inside the Phase 2 DB write loop (around line 118-121), after the existing `_resolved_scheme_code` and `_resolved_nps_scheme_code` blocks, add:

```python
            if hasattr(asset, "_resolved_scheme_category") and asset._resolved_scheme_category:
                from app.engine.mf_classifier import classify_mf
                asset.scheme_category = asset._resolved_scheme_category
                asset.asset_class = classify_mf(asset.scheme_category)
```

(This runs before the `self.db.commit()` at line 134 — no extra commit needed.)

- [ ] **Step 6: Run integration tests to confirm GREEN**

```bash
cd backend && pytest tests/integration/test_mf_classification_api.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
cd backend && pytest --tb=short -q
```

Expected: all existing tests continue to pass.

- [ ] **Step 8: Commit**

```bash
git add app/schemas/asset.py app/services/price_service.py tests/integration/test_mf_classification_api.py
git commit -m "feat: persist scheme_category and reclassify MF asset_class on price refresh"
```

---

## Task 6: Frontend — `scheme_category` in types + `formatMFCategory` formatter

**Files:**
- Modify: `frontend/types/index.ts`
- Modify: `frontend/lib/formatters.ts`

- [ ] **Step 1: Add `scheme_category` to the `Asset` type**

In `frontend/types/index.ts`, find the `Asset` interface and add:

```typescript
scheme_category: string | null
```

After `is_active: boolean`.

- [ ] **Step 2: Add `formatMFCategory` to `lib/formatters.ts`**

In `frontend/lib/formatters.ts`, append:

```typescript
/** Strip mfapi.in scheme_category prefix and return the sub-type label.
 *  "Equity Scheme - Large Cap Fund" → "Large Cap Fund"
 *  "Debt Scheme - Liquid Fund"      → "Liquid Fund"
 *  null / undefined                 → "—"
 */
export function formatMFCategory(raw: string | null | undefined): string {
  if (!raw) return '—'
  const match = raw.match(/^[^-]+-\s*(.+)$/)
  return match ? match[1].trim() : raw
}
```

- [ ] **Step 3: Verify via TypeScript build (no frontend test framework in project)**

> **Note:** This project has no Jest/Vitest setup for frontend. `npm run build` is the verification — TypeScript compilation catches type errors. `formatMFCategory` is a pure string function; correctness is verified by the backend's end-to-end integration test which reads `scheme_category` from the API and confirms the field is correct.

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build completes with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
cd frontend && git add types/index.ts lib/formatters.ts
git commit -m "feat: add scheme_category to Asset type and formatMFCategory formatter"
```

---

## Task 7: Frontend — `showCategory` prop in `HoldingsTable` + MF page

**Files:**
- Modify: `frontend/components/domain/HoldingsTable.tsx`
- Modify: `frontend/app/mutual-funds/page.tsx`

- [ ] **Step 1: Add `showCategory` prop to `HoldingsTableProps`**

In `frontend/components/domain/HoldingsTable.tsx`, find `HoldingsTableProps` (line 42) and add:

```typescript
interface HoldingsTableProps {
  assets: HoldingRow[]
  loading: boolean
  variant?: HoldingsVariant
  showUnits?: boolean
  showCategory?: boolean   // ← add this
}
```

- [ ] **Step 2: Destructure `showCategory` in the component**

In `export function HoldingsTable(...)` (line 142), add `showCategory = false` to destructuring:

```typescript
export function HoldingsTable({ assets, loading, variant = 'default', showUnits = false, showCategory = false }: HoldingsTableProps) {
```

- [ ] **Step 3: Add the Category column header**

In the `<thead>` section, after the Name `th` call (line 186), add:

```tsx
{showCategory && (
  <th className="pb-2.5 pr-4 text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">
    Category
  </th>
)}
```

- [ ] **Step 4: Add the Category cell in each row**

In the `<tbody>` row, after the Name `<td>` (line 230), add:

```tsx
{showCategory && (
  <td className="py-3 pr-4 text-sm text-secondary">
    {formatMFCategory(a.scheme_category)}
  </td>
)}
```

Import `formatMFCategory` at the top of the file:

```typescript
import { formatPct, formatMFCategory } from '@/lib/formatters'
```

(Replace the existing `import { formatPct } from '@/lib/formatters'`.)

- [ ] **Step 5: Pass `showCategory` from the MF page**

In `frontend/app/mutual-funds/page.tsx`, update the `<HoldingsTable>` call:

```tsx
<HoldingsTable assets={assets} loading={loading} showCategory />
```

- [ ] **Step 6: Build to verify no type errors**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: clean build.

- [ ] **Step 7: Commit**

```bash
cd frontend && git add components/domain/HoldingsTable.tsx app/mutual-funds/page.tsx
git commit -m "feat: add Category column to MF holdings table via showCategory prop"
```

---

## Task 8: Final verification

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && pytest --tb=short -q
```

Expected: all tests GREEN, no regressions.

- [ ] **Step 2: Run frontend lint**

```bash
cd frontend && npm run lint
```

Expected: no new errors.

- [ ] **Step 3: Verify migration chain is intact**

```bash
cd backend && alembic history --verbose | head -30
```

Expected: new migration appears at the top of the chain.

- [ ] **Step 4: Final commit if any cleanup needed, otherwise done.**

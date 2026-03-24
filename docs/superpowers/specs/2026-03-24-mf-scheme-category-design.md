# MF Scheme Category Classification & Asset Class Correctness — Design Spec

**Date:** 2026-03-24
**Status:** Approved

## Problem

1. All mutual fund assets are assigned `AssetClass.MIXED` at import time regardless of fund type, causing them to appear as a fifth "MIXED" slice in the allocation donut.
2. NPS assets are also assigned `AssetClass.MIXED` at import time but should be `DEBT`.
3. The MF holdings table has no way to show fund sub-type.

All other asset types (STOCK_IN, STOCK_US, RSU, FD, RD, PPF, EPF, GOLD, SGB, REAL_ESTATE) are already correctly classified at import time and require no changes.

## Goal

1. Automatically fetch and store mfapi.in `scheme_category` for each MF asset and use it to set the correct `asset_class` (EQUITY or DEBT).
2. Fix NPS `asset_class` at import time (MIXED → DEBT) and backfill existing NPS assets in the DB.
3. Display a short category label in the MF holdings table.
4. Ensure the allocation donut shows only 4 classes (EQUITY/DEBT/GOLD/REAL_ESTATE) with accurate stored values.

---

## Backend Design

### 1. DB — new `scheme_category` column

Add `scheme_category: str | None` to the `Asset` model:

```python
scheme_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

Single Alembic migration `add_scheme_category_fix_nps_asset_class` that does two things:
1. `ADD COLUMN scheme_category VARCHAR(100)` on the `assets` table.
2. Data migration: `UPDATE assets SET asset_class = 'DEBT' WHERE asset_type = 'NPS'` — fixes all existing NPS assets.

`scheme_category` is **read-only from the API consumer's perspective** — written only by the price feed, never via `AssetCreate` or `AssetUpdate`.

### 2. Fix `ASSET_CLASS_MAP` in `import_service.py`

Change `"NPS": AssetClass.MIXED` → `"NPS": AssetClass.DEBT` so newly imported NPS assets get the correct class at creation time.

### 3. Classification helper (`engine/mf_classifier.py`)

Pure function, no DB dependency:

```python
def classify_mf(scheme_category: str | None) -> AssetClass:
    if not scheme_category:
        return AssetClass.EQUITY  # default for null or empty string
    cat = scheme_category.lower()
    if cat.startswith("debt scheme"):
        return AssetClass.DEBT
    # Equity, Hybrid, Other, Solution Oriented → all EQUITY
    return AssetClass.EQUITY
```

### 4. `MFAPIFetcher` — switch to non-`/latest` endpoint + capture `scheme_category`

The current fetcher calls `{BASE_URL}/{scheme_code}/latest`. The `/latest` endpoint returns only NAV data with no `meta` field. Switch to the bare `{BASE_URL}/{scheme_code}` endpoint, which returns:

```json
{
  "meta": { "scheme_category": "Equity Scheme - Large Cap Fund", ... },
  "data": [{"date": "...", "nav": "..."}, ...]
}
```

Response shape is compatible — `data[0]["nav"]` continues to work. After reading NAV, also read:

```python
scheme_category = data.get("meta", {}).get("scheme_category")
if scheme_category:
    asset._resolved_scheme_category = scheme_category
```

No extra HTTP calls.

### 5. `PriceService` — persist `scheme_category` and update `asset_class`

Both `refresh_all` and `refresh_asset` paths must persist `_resolved_scheme_category` after calling `MFAPIFetcher.fetch()`, mirroring the existing `_resolved_scheme_code` persistence pattern:

```python
if hasattr(asset, "_resolved_scheme_category"):
    asset.scheme_category = asset._resolved_scheme_category
    asset.asset_class = classify_mf(asset.scheme_category)
```

This corrects existing MIXED-class MFs on the next startup price refresh and on any single-asset refresh via `POST /prices/{id}/refresh`.

### 6. `AssetResponse` schema

Add `scheme_category: Optional[str] = None` to `AssetResponse`. Not added to `AssetCreate` or `AssetUpdate`.

### 7. `get_allocation()` in `returns_service`

The existing `MIXED → EQUITY` and `NPS → DEBT` runtime remaps remain as safety nets. Once assets are corrected (NPS via migration, MFs via price refresh), these fallbacks become no-ops but are harmless to keep.

---

## Frontend Design

### 1. `types/index.ts`

Add `scheme_category: string | null` to the `Asset` interface. `HoldingRow` in `HoldingsTable.tsx` extends `Asset` and inherits the field automatically.

### 2. `formatMFCategory` in `lib/formatters.ts`

Per project conventions (CLAUDE.md: "never format inline in JSX"):

```typescript
export function formatMFCategory(raw: string | null | undefined): string {
  if (!raw) return '—'
  // Strip prefix: "Equity Scheme - ", "Debt Scheme - ", "Hybrid Scheme - ", etc.
  const match = raw.match(/^[^-]+-\s*(.+)$/)
  return match ? match[1].trim() : raw
}
```

### 3. `HoldingsTable` — `showCategory` prop

- Add `showCategory?: boolean` prop (default `false`).
- When true, render a "Category" column after "Name" showing `formatMFCategory(a.scheme_category)`.
- Only the Mutual Funds page passes `showCategory`.

### 4. `mutual-funds/page.tsx`

Pass `showCategory` to `<HoldingsTable>`.

### 5. Allocation donut

No change. `get_allocation()` already returns 4 canonical classes. Once asset_class values are corrected (NPS via migration, MFs via price refresh), the donut naturally reflects the right distribution.

---

## Classification Mapping

### MF (`scheme_category` from mfapi.in)

| `scheme_category` prefix | `asset_class` |
|---|---|
| `Debt Scheme - ...` | `DEBT` |
| `Equity Scheme - ...` | `EQUITY` |
| `Hybrid Scheme - ...` | `EQUITY` |
| `Other Scheme - ...` (Index, ETF, FOF) | `EQUITY` |
| `Solution Oriented Scheme - ...` | `EQUITY` |
| `null` / `""` / unknown | `EQUITY` (default) |

### All other asset types (no change needed)

| Asset Type | `asset_class` |
|---|---|
| STOCK_IN, STOCK_US, RSU | EQUITY ✅ |
| FD, RD, PPF, EPF | DEBT ✅ |
| NPS | DEBT (was MIXED — fixed by migration + `ASSET_CLASS_MAP` change) |
| GOLD, SGB | GOLD ✅ |
| REAL_ESTATE | REAL_ESTATE ✅ |

---

## Testing

### Unit tests (`tests/unit/test_mf_classifier.py`)
- `classify_mf("Debt Scheme - Liquid Fund")` → `DEBT`
- `classify_mf("Equity Scheme - Large Cap Fund")` → `EQUITY`
- `classify_mf("Hybrid Scheme - Balanced Advantage Fund")` → `EQUITY`
- `classify_mf("Other Scheme - Index Funds")` → `EQUITY`
- `classify_mf(None)` → `EQUITY`
- `classify_mf("")` → `EQUITY`

### Unit tests (`tests/unit/test_price_feed.py`)
- `MFAPIFetcher.fetch()` sets `asset._resolved_scheme_category` when `meta.scheme_category` is present.
- `MFAPIFetcher.fetch()` does not set `_resolved_scheme_category` when `meta` is absent (graceful).
- `MFAPIFetcher.fetch()` calls `{BASE_URL}/{scheme_code}` (not `/latest`) — verify URL in mock.

### Integration tests (new `tests/integration/test_mf_classification_api.py`)
- After price refresh, MF asset with mock `scheme_category = "Debt Scheme - Liquid Fund"` has `asset_class = DEBT`.
- After price refresh, MF asset with mock `scheme_category = "Hybrid Scheme - ..."` has `asset_class = EQUITY`.
- `scheme_category` field appears in `GET /assets/{id}` response.
- `scheme_category` is not accepted in `POST /assets` or `PATCH /assets/{id}` (or silently ignored).

### Integration tests (`tests/integration/test_assets_api.py`)
- Newly created NPS asset via `POST /assets` has `asset_class = DEBT`.

### Migration test (unit test or manual verification)
- After running migration, all existing NPS assets have `asset_class = 'DEBT'` in the DB.

---

## Migration Notes

- **NPS assets:** Fixed immediately by Alembic data migration — no price refresh needed.
- **MF assets:** `scheme_category = NULL` and `asset_class = MIXED` until the next price refresh. Startup refresh handles all active MFs automatically.
- `get_allocation()` runtime remaps (MIXED→EQUITY, NPS→DEBT) remain as safety nets indefinitely — harmless once stores values are correct.

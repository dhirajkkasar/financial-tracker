# MF Scheme Category Classification — Design Spec

**Date:** 2026-03-24
**Status:** Approved

## Problem

All mutual fund assets are currently assigned `AssetClass.MIXED` at import time regardless of fund type. This causes all MFs to appear as a fifth "MIXED" slice in the allocation donut instead of being correctly bucketed into EQUITY or DEBT. The MF holdings table also has no way to show fund sub-type.

## Goal

1. Automatically fetch and store the mfapi.in `scheme_category` for each MF asset.
2. Use it to set the correct `asset_class` (EQUITY or DEBT) on the asset.
3. Display a short category label in the MF holdings table.
4. Ensure the allocation donut shows only 4 classes (EQUITY/DEBT/GOLD/REAL_ESTATE).

---

## Backend Design

### 1. DB — new `scheme_category` column

Add `scheme_category: str | None` to the `Asset` model:

```python
scheme_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

Alembic migration: `add_scheme_category_to_assets` — simple `ADD COLUMN` (no-op for SQLite, ALTER TABLE for PostgreSQL).

`scheme_category` is **read-only from the API consumer's perspective** — it is written only by the price feed, never via `AssetCreate` or `AssetUpdate`. No changes to those schemas are needed.

### 2. Classification helper (`engine/mf_classifier.py`)

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

### 3. `MFAPIFetcher` — switch to non-`/latest` endpoint + capture `scheme_category`

The current fetcher calls `{BASE_URL}/{scheme_code}/latest`. The `/latest` endpoint returns only NAV data with no `meta` field. To get `scheme_category`, the fetcher must switch to the bare `{BASE_URL}/{scheme_code}` endpoint, which returns:

```json
{
  "meta": { "scheme_category": "Equity Scheme - Large Cap Fund", ... },
  "data": [{"date": "...", "nav": "..."}, ...]
}
```

The response shape is compatible — `data[0]["nav"]` continues to work. After reading NAV, also read:

```python
scheme_category = data.get("meta", {}).get("scheme_category")
if scheme_category:
    asset._resolved_scheme_category = scheme_category
```

No extra HTTP calls.

### 4. `PriceService` — persist `scheme_category` and update `asset_class`

Both `refresh_all` and `refresh_asset` paths must persist `_resolved_scheme_category` after calling `MFAPIFetcher.fetch()`, mirroring the existing `_resolved_scheme_code` persistence pattern:

```python
if hasattr(asset, "_resolved_scheme_category"):
    asset.scheme_category = asset._resolved_scheme_category
    asset.asset_class = classify_mf(asset.scheme_category)
```

This corrects existing MIXED-class MFs automatically on the next startup price refresh and on any single-asset refresh via `POST /prices/{id}/refresh`.

### 5. `AssetResponse` schema

Add `scheme_category: Optional[str] = None` to `AssetResponse`. Not added to `AssetCreate` or `AssetUpdate` — the field is price-feed managed only.

### 6. `get_allocation()` in `returns_service`

The existing `MIXED → EQUITY` fallback remains as a safety net for assets not yet refreshed. Once an MF is refreshed, its stored `asset_class` will already be correct.

---

## Frontend Design

### 1. `types/index.ts`

Add `scheme_category: string | null` to the `Asset` interface. `HoldingRow` in `HoldingsTable.tsx` extends `Asset` and will inherit the field automatically.

### 2. `formatMFCategory` in `lib/formatters.ts`

Per project conventions (CLAUDE.md: "never format inline in JSX"), this belongs in `lib/formatters.ts`:

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
- Also add `'scheme_category'` to the `SortKey` type for future sortability (optional — can be non-sortable initially).
- Only the Mutual Funds page passes `showCategory`.

### 4. `mutual-funds/page.tsx`

Pass `showCategory` to `<HoldingsTable>`.

### 5. Allocation donut

No change. `get_allocation()` already returns 4 canonical classes. Once MF `asset_class` values are corrected by the price refresh, the donut naturally reflects the right distribution.

---

## Classification Mapping

| `scheme_category` prefix | `asset_class` |
|---|---|
| `Debt Scheme - ...` | `DEBT` |
| `Equity Scheme - ...` | `EQUITY` |
| `Hybrid Scheme - ...` | `EQUITY` |
| `Other Scheme - ...` (Index, ETF, FOF) | `EQUITY` |
| `Solution Oriented Scheme - ...` | `EQUITY` |
| `null` / `""` / unknown | `EQUITY` (default) |

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
- `MFAPIFetcher.fetch()` sets `asset._resolved_scheme_category` when `meta.scheme_category` is present in response.
- `MFAPIFetcher.fetch()` does not set `_resolved_scheme_category` when `meta` is absent (graceful).
- `MFAPIFetcher.fetch()` calls `{BASE_URL}/{scheme_code}` (not `/latest`) — verify URL in mock.

### Integration tests (new `tests/integration/test_mf_classification_api.py`)
- After price refresh, MF asset whose mock response has `scheme_category = "Debt Scheme - Liquid Fund"` has `asset_class = DEBT`.
- After price refresh, MF asset whose mock response has `scheme_category = "Hybrid Scheme - ..."` has `asset_class = EQUITY`.
- `scheme_category` field appears in `GET /assets/{id}` response.
- `scheme_category` is not accepted in `POST /assets` or `PATCH /assets/{id}` (or silently ignored).

---

## Migration Notes

- Existing MF assets have `scheme_category = NULL` and `asset_class = MIXED` until the next price refresh.
- `get_allocation()` continues to remap `MIXED → EQUITY` as a safety net throughout the migration window.
- No data backfill script needed — startup price refresh handles all active MF assets automatically.

# Realised Gain Breakdown — Design Spec

**Date:** 2026-04-04
**Status:** Approved

---

## Overview

Add a collapsible per-asset breakdown to the Realised Gains section of the Tax Summary page. Each tax category row (Equity, Debt, Gold, Real Estate) expands to show which individual assets contributed to its ST/LT gains, with estimated tax per asset. The backend is restructured to group by `asset_class` (from DB) instead of `asset_type`, fixing the Debt MF miscategorisation and making classification data-driven.

---

## Section 1 — Backend: Gains Strategy Hierarchy

### New module: `services/tax/`

Introduce a `TaxGainsStrategy` ABC with a single public method:

```python
def compute(asset, uow: UnitOfWork, fy_start: date, fy_end: date, slab_rate_pct: float) -> AssetTaxGainsResult
```

Returns a dataclass `AssetTaxGainsResult`:

```python
@dataclass
class AssetTaxGainsResult:
    asset_id: int
    asset_name: str
    asset_type: str
    asset_class: str
    st_gain: float
    lt_gain: float
    st_tax_estimate: float      # never null — slab items use injected slab_rate_pct
    lt_tax_estimate: float      # never null
    ltcg_exemption_used: float
    has_slab: bool              # true if slab_rate_pct was used for any gain
```

### Strategy hierarchy

```
TaxGainsStrategy (ABC)
├── FifoTaxGainsStrategy           FIFO lot matching base; no rates defined here
│   ├── IndianEquityTaxGainsStrategy   stcg_rate=20%, ltcg_rate=12.5%, ltcg_exempt=₹1.25L, stcg_days=365
│   │   ├── StockINTaxGainsStrategy    @register (STOCK_IN, *)
│   │   └── EquityMFTaxGainsStrategy   @register (MF, EQUITY)
│   ├── ForeignEquityTaxGainsStrategy  @register (STOCK_US, *)   stcg=slab, ltcg=12.5%, stcg_days=730
│   ├── GoldTaxGainsStrategy           @register (GOLD, *)       stcg=slab, ltcg=12.5%, stcg_days=1095
│   └── DebtMFTaxGainsStrategy         @register (MF, DEBT)      stcg=slab, ltcg=slab,   stcg_days=365
├── AccruedInterestTaxGainsStrategy    @register (FD, *), (RD, *)
└── RealEstateTaxGainsStrategy         @register (REAL_ESTATE, *) stcg=slab, ltcg=12.5%, stcg_days=730
```

### Strategy registration

A `TaxStrategyRegistry` maps `(asset_type, asset_class)` → strategy instance. The `asset_class` key is `"*"` for strategies that apply regardless of class; `"EQUITY"` or `"DEBT"` for MF variants. Lookup: try `(asset_type, asset_class)` first, fall back to `(asset_type, "*")`.

### `IndianEquityTaxGainsStrategy` (shared base for STOCK_IN + equity MF)

All logic lives here — FIFO matching, rate application. `StockINTaxGainsStrategy` and `EquityMFTaxGainsStrategy` are 3-line leaf classes (`@register` + `pass`). No code duplication.

**₹1.25L LTCG exemption (Section 112A):** The exemption is an annual per-individual limit shared across ALL EXEMPTION_ELIGIBLE assets (STOCK_IN + equity MF combined). Strategies do NOT apply it individually. Instead, strategies return raw `lt_gain`; `get_tax_summary()` applies `apply_ltcg_exemption()` once against the aggregated EQUITY entry `lt_gain` after all assets in the class are accumulated. `ltcg_exemption_used` at the per-asset breakdown level is set to `0` — only the class-level entry carries the exemption figure.

### `FifoTaxGainsStrategy` — lot matching

Uses `match_lots_fifo` from `engine/lot_engine.py`. Filters matched sells to those with `sell_date` in `[fy_start, fy_end]`. Classifies ST/LT using the subclass's `stcg_days` ClassVar. The interim `_build_lots_for_asset` code in `tax_service.py` is deleted (see Section 4 for full lot helper refactoring).

### `AccruedInterestTaxGainsStrategy` — FD/RD

Computes interest accrued in the FY using the existing `compute_fd_current_value` from `engine/fd_engine.py`:

```
fy_interest = value_at(min(fy_end, fd.maturity_date))
            − value_at(max(fy_start, fd.start_date))
```

Both bounds are clamped so FDs starting mid-FY or maturing mid-FY are handled correctly. All interest goes into `st_gain` at slab rate. Reads `fd_detail` via `uow.fd.get_by_asset_id(asset.id)`.

### `RealEstateTaxGainsStrategy` — REAL_ESTATE

Real estate is not unit-based, so no FIFO. Looks for `SELL` / `WITHDRAWAL` transactions for the asset within the FY. Gain = sum of proceeds − cost basis (total invested via `CONTRIBUTION` transactions). Holding period = `sell_date − earliest CONTRIBUTION date`. Classified ST (< 730 days) or LT (≥ 730 days). STCG at slab, LTCG at 12.5%.

### Skipped asset types

`EPF`, `PPF` — EEE exempt. `NPS` — complex pension withdrawal rules, excluded for now. `SGB` — tax-exempt at maturity. `RSU` — legacy enum value, not used in data.

### Slab rate

`SLAB_RATE` env var (float, default `30.0`) is read in `dependencies.py` and injected into `TaxService(uow_factory, slab_rate_pct)`. Strategies receive `slab_rate_pct` in `compute()`. Tax is always a numeric estimate — `null` is never returned for slab items.

---

## Section 2 — API Response Shape + `get_tax_summary()` Restructure

### `TaxService` constructor change

```python
# Before
def __init__(self, db: Session):
    self.asset_repo = AssetRepository(db)
    ...

# After
def __init__(self, uow_factory: IUnitOfWorkFactory, slab_rate_pct: float = 30.0):
    self._uow_factory = uow_factory
    self._slab_rate_pct = slab_rate_pct
```

All methods use `with self._uow_factory() as uow:`. No direct repo access.

### `get_tax_summary()` restructure

```
1. open uow
2. uow.assets.list(active=None)  — include inactive (fully sold) assets
3. for each asset:
   a. skip exempt types (EPF, PPF, NPS, SGB, RSU)
   b. resolve strategy via TaxStrategyRegistry(asset.asset_type, asset.asset_class)
   c. strategy.compute(asset, uow, fy_start, fy_end, slab_rate_pct) → AssetTaxGainsResult
   d. skip if st_gain == 0 and lt_gain == 0
   e. accumulate into asset_class bucket
4. build entry per asset_class: aggregate gains + breakdown list
5. sort entries by abs(total_gain) desc
```

### New response shape

```json
{
  "fy": "2024-25",
  "entries": [
    {
      "asset_class": "EQUITY",
      "st_gain": 50000.0,
      "lt_gain": 200000.0,
      "total_gain": 250000.0,
      "ltcg_exemption_used": 125000.0,
      "st_tax_estimate": 10000.0,
      "lt_tax_estimate": 9375.0,
      "total_tax_estimate": 19375.0,
      "slab_rate_pct": null,
      "asset_breakdown": [
        {
          "asset_id": 1,
          "asset_name": "Reliance Industries",
          "asset_type": "STOCK_IN",
          "st_gain": 30000.0,
          "lt_gain": 150000.0,
          "st_tax_estimate": 6000.0,
          "lt_tax_estimate": 3125.0,
          "ltcg_exemption_used": 125000.0
        }
      ]
    },
    {
      "asset_class": "DEBT",
      "st_gain": 15000.0,
      "lt_gain": 0.0,
      "total_gain": 15000.0,
      "ltcg_exemption_used": 0.0,
      "st_tax_estimate": 4500.0,
      "lt_tax_estimate": 0.0,
      "total_tax_estimate": 4500.0,
      "slab_rate_pct": 30.0,
      "asset_breakdown": [...]
    }
  ],
  "totals": {
    "total_st_gain": 65000.0,
    "total_lt_gain": 200000.0,
    "total_gain": 265000.0,
    "total_st_tax": 14500.0,
    "total_lt_tax": 9375.0,
    "total_tax": 23875.0,
    "has_slab_rate_items": true
  }
}
```

Key changes from current shape:
- `asset_type` → `asset_class` on each entry
- `asset_breakdown` list added to each entry
- `slab_rate_pct: float | null` on each entry (non-null when slab rate was applied)
- Tax estimates are always numeric (never `null`)
- `is_st_slab`, `is_lt_slab`, `is_lt_exempt` removed from entry (subsumed by `slab_rate_pct` + `ltcg_exemption_used`)

### `get_unrealised_summary()` and `get_harvest_opportunities()`

Both migrated to use `uow_factory` (currently hold direct repo references). Logic unchanged.

---

## Section 3 — Frontend: Collapsible Breakdown UI

### New types (`frontend/types/index.ts`)

```typescript
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
  asset_class: AssetClass          // replaces asset_type
  st_gain: number
  lt_gain: number
  total_gain: number
  ltcg_exemption_used: number
  st_tax_estimate: number          // always numeric now
  lt_tax_estimate: number
  total_tax_estimate: number
  slab_rate_pct: number | null     // null = no slab rate in this class
  asset_breakdown: AssetGainBreakdown[]
}

export type AssetClass = 'EQUITY' | 'DEBT' | 'GOLD' | 'REAL_ESTATE'
```

### `rollupRealised()` removed

The frontend no longer maps `asset_type → class`. `summary.entries` is already grouped by `asset_class` — render directly. `TAX_CLASS_MAP` is deleted.

### Collapsible state

```typescript
const [expandedClasses, setExpandedClasses] = useState<Set<string>>(new Set())

function toggleClass(cls: string) {
  setExpandedClasses(prev => {
    const next = new Set(prev)
    next.has(cls) ? next.delete(cls) : next.add(cls)
    return next
  })
}
```

### Table structure

Category row: renders a `+` / `−` toggle button (12×12 rounded, muted border) in the first cell. Only shown when `asset_breakdown.length > 0`.

When expanded, sub-rows render immediately below the category row — same `<tbody>`, slightly indented, `bg-accent-subtle/20` background to visually nest them.

Sub-row columns: asset name (`<Link href="/assets/{id}">` in `text-accent`), asset type label (from existing `ASSET_TYPE_LABELS`, `text-xs text-tertiary`), ST gain, LT gain, combined tax estimate.

Category row tax column: shows the numeric estimate. When `slab_rate_pct` is non-null, a sub-text `{slab_rate_pct}% slab (est.)` renders below the amount in `text-[10px] text-tertiary`. This label is on the category row only — not on expanded sub-rows.

### Visual sketch

```
┌──────────────────────────────────────────────────────────────────────┐
│  Category    ST Gain     LT Gain    Exemption    ST Tax    LT Tax    │
├──────────────────────────────────────────────────────────────────────┤
│ − Equity    ₹50,000   ₹2,00,000   ₹1,25,000    ₹10,000   ₹9,375    │
│   · Reliance Industries   STOCK_IN  ₹30,000  ₹1,50,000   ₹9,125    │
│   · HDFC Flexi Cap Fund   MF        ₹20,000  ₹  50,000   ₹  250    │
│ + Debt      ₹15,000        —             —     ₹ 4,500        —     │
│                                              30% slab (est.)        │
│ + Gold           —    ₹80,000             —        —     ₹10,000    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Section 4 — Lot Helper Refactoring (Last Step)

### Problem

`tax_service._build_lots_for_asset()` duplicates `MarketBasedStrategy._build_lots_sells()` and `_match_and_get_open_lots()`. Any change to FIFO logic requires two edits.

### Solution

Extract `LotHelper` into `engine/lot_helper.py` — pure class, no DB access:

```python
class LotHelper:
    def __init__(self, stcg_days: int): ...
    def build_lots_sells(self, txns) -> tuple[list[_Lot], list[_Sell]]: ...
    def match(self, lots, sells) -> tuple[list[_OpenLot], list[dict]]: ...
```

### Callers after refactoring

- `MarketBasedStrategy` — delegates `_build_lots_sells` / `_match_and_get_open_lots` to `LotHelper`; external behaviour unchanged
- `FifoTaxGainsStrategy` — uses `LotHelper` directly; `tax_service._build_lots_for_asset()` is deleted

### Ordering

Done after the new tax feature is working end-to-end. Returns engine is not touched until the new tax code is verified in tests.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SLAB_RATE` | `30.0` | Income tax slab rate (%) applied to slab-rate gains for estimation |

Add to `backend/.env`.

---

## Files Affected

### New
- `backend/app/services/tax/strategies/base.py` — `TaxGainsStrategy` ABC + registry
- `backend/app/services/tax/strategies/fifo_base.py` — `FifoTaxGainsStrategy`
- `backend/app/services/tax/strategies/indian_equity.py` — `IndianEquityTaxGainsStrategy` + leaf classes
- `backend/app/services/tax/strategies/foreign_equity.py` — `ForeignEquityTaxGainsStrategy`
- `backend/app/services/tax/strategies/gold.py` — `GoldTaxGainsStrategy`
- `backend/app/services/tax/strategies/debt_mf.py` — `DebtMFTaxGainsStrategy`
- `backend/app/services/tax/strategies/accrued_interest.py` — `AccruedInterestTaxGainsStrategy`
- `backend/app/services/tax/strategies/real_estate.py` — `RealEstateTaxGainsStrategy`
- `backend/app/engine/lot_helper.py` — `LotHelper` (Section 4, last)

### Modified
- `backend/app/services/tax_service.py` — restructured (UoW, strategy dispatch, new response shape)
- `backend/app/api/dependencies.py` — inject `slab_rate_pct` + `uow_factory` into `TaxService`
- `backend/.env` — add `SLAB_RATE=30`
- `frontend/types/index.ts` — new types, `TaxSummaryEntry` updated
- `frontend/app/tax/page.tsx` — collapsible rows, `TAX_CLASS_MAP` removed, slab label
- `backend/app/services/returns/strategies/market_based.py` — delegate to `LotHelper` (Section 4)

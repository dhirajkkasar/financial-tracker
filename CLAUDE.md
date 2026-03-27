# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Financial Portfolio Tracker — Claude Context

## Project Overview
Personal, local-first, single-user investment portfolio tracker.
- **Backend:** Python 3.11+ FastAPI + SQLAlchemy + Alembic (`backend/`)
- **Frontend:** Next.js App Router + Recharts + axios (`frontend/`)
- **DB:** SQLite locally → PostgreSQL in cloud (one `DATABASE_URL` env var switches)
- **Execution plan:** `execution_plan.md` (7 phases; Phases 1–5 complete)

## Commands

### Backend
```bash
cd backend

# Install dependencies (uses uv lockfile — recommended)
uv sync --all-extras

# Run dev server (seeds interest rates + auto-matures past-due FDs on startup)
uvicorn app.main:app --reload

# Run all tests (use uv run — bare pytest/python/python3 are not on PATH)
uv run pytest

# Run a single test file
uv run pytest tests/unit/test_fd_engine.py

# Run a single test by name
uv run pytest tests/unit/test_fd_engine.py::test_function_name -v

# Run with coverage report
uv run pytest --cov=app --cov-report=term-missing

# Run only unit or integration tests
uv run pytest tests/unit/
uv run pytest tests/integration/

# Create a new Alembic migration
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1

# CLI helper (server must be running)
python cli.py import ppf <file>
python cli.py import epf <file>
python cli.py import cas <file>
python cli.py import nps <file>
python cli.py import zerodha <file>
python cli.py import fidelity-rsu <file>   # Fidelity RSU holding CSV (MARKET_TICKER.csv)
python cli.py import fidelity-sale <file>  # Fidelity tax-cover sale PDF (NetBenefits)
python cli.py list assets
python cli.py refresh-prices
python cli.py snapshot
python cli.py backup                     # Backup SQLite DB to Google Drive (gzip-compressed)
python cli.py backup --folder my-folder  # Override Drive folder name
python cli.py add goal --name "Retirement" --target 10000000 --date 2040-01-01 --asset "HDFC MF:50" --asset "PPF SBI:50" --assumed-return 12.0
python cli.py update goal-allocation --goal "Retirement" --asset "HDFC MF" --pct 30
python cli.py remove goal-allocation --goal "Retirement" --asset "HDFC MF"
python cli.py delete goal --name "Retirement"
```

### Frontend
```bash
cd frontend

npm install
npm run dev       # dev server at http://localhost:3000
npm run build     # production build
npm run lint      # ESLint
```

### Environment Variables
- **Backend** (`backend/.env`): `DATABASE_URL=sqlite:///./portfolio.db`
- **Frontend** (`frontend/.env.local`): `NEXT_PUBLIC_API_URL=http://localhost:8000`
- **CLI**: `PORTFOLIO_API=http://localhost:8000` (override default)

## Authoritative Docs (in repo root)
| File | Authority |
|---|---|
| `requirements.md` (v0.3) | Schema, asset types, tax rules, UI tab structure |
| `api-routes.md` | API contract — backend + frontend must match exactly |
| `data_model.md` | Idempotency strategy, data shapes |
| `tech_decisions.md` | Monorepo layout, design principles |
| `execution_plan.md` | Phase status, architecture decisions, what's done/pending |
| `ui.md` | Component-level layout only (NOT tab structure — use requirements.md) |

---

## Critical Architecture Decisions

### Monetary Amounts
- **DB:** Signed integers in **paise** (1 INR = 100 paise)
  - Negative = outflow: `BUY`, `SIP`, `CONTRIBUTION`, `VEST`
  - Positive = inflow: `SELL`, `REDEMPTION`, `DIVIDEND`, `INTEREST`, `WITHDRAWAL`, `BONUS`
- **API:** Decimal INR (schema layer converts to/from paise — never expose raw paise to frontend)

### Transaction Deduplication (`txn_id`)
Use native IDs from source systems where available; fall back to SHA-256 hash:

| Source | `txn_id` Strategy |
|---|---|
| Zerodha tradebook CSV | Native `trade_id` from file |
| NSDL NPS CSV | Native transaction reference number |
| CAS PDF (CAMS/KFintech) | Check for reference number in PDF text first; fall back to `SHA256(folio + isin + date + units + type + amount_paise)` |
| Manual entry (FD, PPF, EPF, Gold, Real Estate) | `SHA256(asset_id + date + amount_paise + type + user_ref_if_any)` |

Hash must be **stable across re-imports** — never include internal DB IDs in the hash.

### Asset Types
`STOCK_IN`, `STOCK_US`, `MF`, `FD`, `RD`, `PPF`, `EPF`, `NPS`, `GOLD`, `SGB`, `REAL_ESTATE`, `RSU`

### Transaction Types
`BUY`, `SELL`, `SIP`, `REDEMPTION`, `DIVIDEND`, `INTEREST`, `CONTRIBUTION`, `WITHDRAWAL`, `SWITCH_IN`, `SWITCH_OUT`, `BONUS`, `SPLIT`, `VEST`, `TRANSFER`

- `SWITCH_IN` / `SWITCH_OUT` / `SPLIT` → excluded from XIRR calculations
- `VEST` → RSU vesting event (treated as `STOCK_US`); perquisite tax noted in `notes` field
- `TRANSFER` → EPF withdrawal/transfer out (Claim: Against PARA 57(1)); positive amount (inflow)

### RSUs
- Asset type: `STOCK_US`
- Transaction type: `VEST` (distinct from `BUY` to preserve vesting history)
- Perquisite tax at vest (income tax on FMV) tracked in `notes` field only — no separate tax module

### Returns Engine — Asset Type Routing
Returns are computed via the **strategy pattern** (`services/returns/strategies/`). Each asset type has a leaf strategy class. The routing table below reflects the strategy hierarchy:

```
MARKET_BASED  = STOCK_IN, STOCK_US, MF, RSU, GOLD, SGB, NPS
                → current_value = total_units × price_cache NAV
                → stcg_days declared as ClassVar on each strategy; passed to lot_engine
FD_BASED      = FD, RD
                → current_value = formula (compound interest)
EPF_BASED     = EPF
                → total_invested = sum of CONTRIBUTION outflows (employee + employer + EPS + transfer-ins)
                → current_value  = total_invested + sum of INTEREST inflows (employee + employer + EPS − TDS)
                → EPF asset always is_active=True (never auto-set inactive)
VALUATION_BASED = PPF, REAL_ESTATE
                → current_value = latest Valuation entry (manual passbook)
```
- NPS: MARKET_BASED — units via CONTRIBUTION, NAV auto-fetched from npsnav.in
- VALUATION_BASED with no Valuation entry: `total_invested` shows; `current_value`/XIRR/P&L are null

**Strategy hierarchy:**
```
AssetReturnsStrategy (ABC, template method)
├── MarketBasedStrategy          stcg_days: ClassVar[int]; compute_lots = FIFO lot engine
│   ├── StockINStrategy          stcg_days=365
│   ├── StockUSStrategy          stcg_days=730; override get_invested_value (USD→INR at vest)
│   ├── RSUStrategy              stcg_days=730; override build_cashflows (VEST unit calc)
│   ├── MFStrategy               stcg_days=365; override get_current_value (CAS snapshot first)
│   ├── NPSStrategy              stcg_days=365
│   ├── GoldStrategy             stcg_days=1095
│   └── SGBStrategy              stcg_days=1095; maturity tax-free check
└── ValuationBasedStrategy       get_current_value = latest Valuation entry
    ├── PPFStrategy
    ├── RealEstateStrategy
    ├── FDStrategy               override get_current_value (fd_engine formula)
    ├── RDStrategy               override get_current_value + get_invested_value
    └── EPFStrategy              override both invested and current_value
```

Adding a new asset type: create a 3-line leaf class in `services/returns/strategies/asset_types/` with `@register_strategy(AssetType.NEW)`.

### NPS Price Feed (npsnav.in)
- **Source:** `https://npsnav.in/api`
- **Bulk scheme resolution (once per `refresh_all`):**
  1. `GET /api/schemes` → all 150+ scheme codes + names
  2. Fuzzy-match each NPS asset name via `SequenceMatcher` (threshold 0.6)
  3. Persist resolved SM code to `asset.identifier`; always overwrites with latest
- **Per-asset NAV:** `GET /api/{scheme_code}` → plain-text float
- **Staleness:** 1 day (same as MF)
- If `asset.identifier` already starts with `SM`, used directly without scheme lookup

### GoalAllocation Rules
- `allocation_pct` is set explicitly per `(asset, goal)` pair
- **Sum of `allocation_pct` across ALL goals for one asset must equal exactly 100%** (or 0 if no allocations exist)
- Must be a **whole number and a multiple of 10** (10, 20, 30 ... 100)
- Violation → API returns 422
- `current_value_toward_goal = asset_current_value × allocation_pct / 100`
- `find_goal()` in `cli.py` fuzzy-matches goal names via `difflib.get_close_matches(cutoff=0.4)`
- `--asset "Name:pct"` parsed with `rsplit(":", 1)` to handle colons in asset names
- Allocation POST failures in `add goal` are non-fatal — goal still created, error printed
- `_api()` handles 204 No Content (DELETE endpoints) by returning `{}` when response has no content

### Tax Module (Phase 5 — complete)
- **Rates are config-driven:** `config/tax_rates/2024-25.yaml`, `config/tax_rates/2025-26.yaml`
  - Adding a new FY = drop a new YAML file; zero code changes
  - `TaxRatePolicy` (in `engine/tax_engine.py`) reads and caches per-FY YAML files
  - `TaxRate` dataclass returned: `stcg_rate_pct`, `ltcg_rate_pct`, `is_stcg_slab`, `is_ltcg_slab`, `ltcg_exemption_inr`, `is_exempt`, `maturity_exempt`
- **FY2024-25 rules:**
  - `STOCK_IN` / equity `MF`: STCG 20% (<1yr), LTCG 12.5% (≥1yr), ₹1.25L exemption
  - `STOCK_US` / `RSU`: STCG slab (<2yr), LTCG 12.5% (≥2yr)
  - Debt `MF` (post Apr 2023): slab rate regardless of holding period
  - `GOLD` / `SGB`: STCG slab (<3yr), LTCG 12.5% (≥3yr); SGB held to maturity = tax-free
  - `REAL_ESTATE`: STCG slab (<2yr), LTCG 12.5% (≥2yr)
  - `FD` / `RD` / `EPF` (above threshold): slab rate; `PPF`: EEE (fully exempt)
- **API endpoints:** `GET /tax/summary?fy=2024-25`, `GET /tax/unrealised`, `GET /tax/harvest-opportunities`

### Price Fetchers (`services/price_feed.py`)
Self-registering via `@register_fetcher` decorator. `staleness_threshold` is a `ClassVar` on each fetcher — no per-type hardcoding in the service.

| Asset | Fetcher class | `staleness_threshold` |
|---|---|---|
| MF NAV | `MFAPIFetcher` | 1 day |
| NPS NAV | `NPSNavFetcher` | 1 day |
| NSE/BSE stocks | `YFinanceStockFetcher` | 6 hours |
| US stocks + forex | `YFinanceStockFetcher` | 6 hours |
| Gold | `YFinanceStockFetcher` | 6 hours |

Adding a new price source: create a new `@register_fetcher` class with `asset_types` and `staleness_threshold` ClassVars. No edits to existing files.

### Startup Behaviour
- FastAPI lifespan event on startup:
  1. Seeds interest rates (idempotent)
  2. Runs `DepositsService.mark_matured_fds()` — marks FDs/RDs past maturity date as `is_matured=True` / `is_active=False`, back-fills `maturity_amount` if missing
- Price refresh is **on-demand only** via `python cli.py refresh-prices`

### DepositsService (`backend/app/services/deposits_service.py`)
- `mark_matured_fds()` — queries active FD/RD assets whose `maturity_date < today` and `is_matured=False`; computes `maturity_amount` from `fd_engine`; sets `is_matured=True`, `is_active=False`; commits once at the end
- Called automatically on startup; idempotent

### FD vs RD in FDDetail
- `fd_type = FD` → `principal_amount` = lump-sum deposit (paise)
- `fd_type = RD` → `principal_amount` = **monthly installment** (paise); total principal from `CONTRIBUTION` transactions

### PPF/EPF XIRR
- Requires at least one `Valuation` entry; returns `null` XIRR with message if none exists

---

## Backend Architecture

```
api/
  routes/          → HTTP only: parse request → call service → return response model
                     No db: Session. No repo imports. No business logic.
  dependencies.py  → ALL concrete wiring. Every service factory lives here.
                     Rule: no other file may instantiate a concrete service or repo.

services/
  returns/
    strategies/
      base.py          → AssetReturnsStrategy ABC (template method)
      market_based.py  → MarketBasedStrategy (units × price NAV, FIFO lots)
      valuation_based.py → ValuationBasedStrategy (latest Valuation entry)
      asset_types/     → One 3-line leaf class per asset type (@register_strategy)
      registry.py      → DefaultReturnsStrategyRegistry; IReturnsStrategyRegistry protocol
    returns_service.py → Thin coordinator: looks up strategy, calls compute()
  imports/
    orchestrator.py    → ImportOrchestrator: preview/commit flow; fires ImportCompletedEvent
    deduplicator.py    → InMemoryDeduplicator / DBDeduplicator (pure, injectable)
    preview_store.py   → TTL store for pending previews
    post_processors/
      base.py          → IPostProcessor protocol
      stock.py         → marks asset inactive when net_units ≤ 0
      mf.py            → persists CAS snapshots
  event_bus.py         → SyncEventBus + IEventBus protocol + ImportCompletedEvent
  price_feed.py        → BasePriceFetcher ABC + @register_fetcher; staleness on class
  tax_service.py       → receives TaxRatePolicy via DI
  snapshot_service.py
  deposits_service.py

repositories/
  interfaces.py       → Protocol definitions (duck-typed; existing repos satisfy without changes)
  unit_of_work.py     → UnitOfWork context manager; exposes all repos as attributes
                        On success: commits. On exception: rolls back. Repos have NO db.commit().
  *.py                → All DB queries here. No db.commit() calls — UoW commits.

importers/
  base.py             → BaseImporter ABC (source / format / asset_type ClassVars)
  registry.py         → @register_importer decorator + ImporterRegistry
  pipeline.py         → ImportPipeline: parse → validate → deduplicate
  *_parser.py         → Concrete importers; each decorated with @register_importer

engine/
  lot_engine.py       → stcg_days accepted as parameter (not hardcoded per asset type)
  tax_engine.py       → TaxRatePolicy + TaxRate dataclass; reads config/tax_rates/{FY}.yaml
  mf_classifier.py    → ISchemeClassifier protocol + DefaultSchemeClassifier
  returns.py          → Pure XIRR/CAGR functions
  fd_engine.py, ppf_epf_engine.py, allocation.py → pure functions, no coupling

schemas/
  responses/          → Typed Pydantic response models (service-layer contract)
    common.py         → PaginatedResponse[T]
    returns.py        → AssetReturnsResponse, LotComputedResponse, LotsPageResponse
    tax.py            → TaxSummaryResponse, HarvestOpportunityEntry, UnrealisedGainEntry
    imports.py        → ImportPreviewResponse, ImportCommitResponse, ParsedTransactionPreview
    prices.py         → PriceRefreshResponse, AssetPriceEntry
  requests/           → (existing, unchanged)

config/
  tax_rates/
    2024-25.yaml      → per-asset-type STCG/LTCG rates and flags
    2025-26.yaml      → add new FY = drop file here, zero code changes
```

---

## Coding Standards

### TDD Workflow (mandatory)
```
1. Write failing test  →  2. pytest (RED)  →  3. Write minimum code  →  4. pytest (GREEN)  →  5. Refactor
```
- **No code without a failing test first.**
- Coverage targets: `pytest --cov=app --cov-fail-under=80`; engine ≥ 90%; importers ≥ 85%
- Test deps: `pytest`, `pytest-cov`, `pytest-mock`, `httpx`, `factory-boy`

### Dependency Injection
- **All wiring in `api/dependencies.py`** — the only file where concrete service/repo types appear
- Services declare abstract dependencies (`IUnitOfWorkFactory`, `IReturnsStrategyRegistry`, etc.) in `__init__` — never instantiate anything internally
- **Rule:** No service file may contain the word `Session` or import a concrete repo class
- `api/dependencies.py` factory pattern:
  ```python
  def get_returns_service(db: Session = Depends(get_db)) -> ReturnsService:
      return ReturnsService(
          uow_factory=lambda: UnitOfWork(db),
          strategy_registry=DefaultReturnsStrategyRegistry(),
      )
  ```
- **Testing:** inject fakes directly — no `dependency_overrides`, no `monkeypatch`:
  ```python
  service = ReturnsService(
      uow_factory=lambda: FakeUnitOfWork(assets=[sample_asset]),
      strategy_registry=FakeStrategyRegistry(...),
  )
  ```

### UnitOfWork Pattern
- Services use `with self._uow_factory() as uow:` for all DB access
- `uow` exposes: `uow.assets`, `uow.transactions`, `uow.valuations`, `uow.price_cache`, `uow.fd`, `uow.cas_snapshots`, `uow.goals`, `uow.snapshots`, `uow.interest_rates`, `uow.important_data`
- All writes in the block commit atomically on exit; any exception triggers full rollback
- `uow.flush()` makes IDs available mid-block without committing
- Repositories have **no `db.commit()` calls** — commit is solely the UoW's responsibility

### Import Architecture
- **Adding a new importer:** create `importers/new_source_parser.py` extending `BaseImporter` with `@register_importer`. No other files change.
- **`ImportOrchestrator`** (`services/imports/orchestrator.py`): preview → store result → commit → run post-processors → fire `ImportCompletedEvent`
- **`ImportPipeline`** (`importers/pipeline.py`): `parse → validate → deduplicate` — called by orchestrator
- **Post-processors** (`services/imports/post_processors/`): implement `IPostProcessor` protocol; registered per asset type in `api/dependencies.py`
- **`SyncEventBus`** (`services/event_bus.py`): subscribe handlers at startup in `api/dependencies.py`; `ImportOrchestrator` only knows `IEventBus`, not concrete handlers

### Exception Hierarchy
`AppError → NotFoundError / DuplicateError / ValidationError`

### Schemas
- **`schemas/responses/`** — service-layer typed output; services annotate return types with these
- **`MoneyMixin`** — paise↔INR conversion applied in response model validators; never scattered in service code
- **`schemas/requests/`** — existing, unchanged

### Logging
`logging` module only. `WARNING` for failed fetches; `INFO` for imports/refreshes.

### Test Structure
```
tests/
├── conftest.py          # Shared: in-memory SQLite fixture (db), TestClient, DI overrides
├── factories.py         # make_asset(), make_transaction(), make_cashflow() helpers
├── fixtures/            # Static files: sample_cas.pdf, zerodha_tradebook.csv, nps_sample.csv
├── unit/
│   ├── conftest.py      # Unit-specific fixtures (no DB, no HTTP)
│   └── test_*.py        # Pure engine + strategy tests — use FakeUnitOfWork, not mocks
└── integration/
    ├── conftest.py      # Seeded DB state fixtures
    └── test_*.py        # TestClient tests against in-memory SQLite
```
- Integration test DB fixture is `db` (not `test_db`)
- Unit tests for strategies use `FakeUnitOfWork` injected directly — no `dependency_overrides`

---

## Frontend — Key Decisions

### Goals Overview Widget
- `GoalsWidget` (`components/domain/GoalsWidget.tsx`) renders compact goal progress rows on the overview page
- Uses existing `useGoals()` hook — no new API calls; placed between Net Worth Chart and allocation donuts in `app/page.tsx`
- Uses design-system tokens (bg-card, border-border, text-accent) — NOT hardcoded Tailwind colors

### P&L Display
- **Current P&L** = unrealized gains (st_unrealised + lt_unrealised) if lot-based, else current − invested
- **All-time P&L** = unrealized + realized (all 4 lot fields) if lot-based, else same as Current P&L
- ST/LT breakdown removed from HoldingsTable and AssetSummaryCards — detail only on the Tax page
- `AssetSummaryCards` always shows 5 cards: Invested | Current Value | Current P&L (with %) | All-time P&L | XIRR
- `HoldingsTable` columns: Name | Type | Invested | Current Value | Current P&L (INR + % sub) | All-time P&L | XIRR
- Deposit assets (FD/RD) show an extra row: Taxable Interest | Est. Tax (30%)

### Asset Ordering
- All asset listing pages sort by `current_value` descending (nulls last) — in `useAssetsWithReturns`

### Overview Breakdown Table
- "Summary by Asset Type" table includes Current P&L and All-time P&L columns
- All-time P&L includes inactive/closed asset net transactions (realized gains from sold positions)

### Nav Tabs
Defined in `constants/index.ts` → `NAV_TABS`:
Overview | Stocks | Mutual Funds | Deposits | PPF | EPF | NPS | US Stocks | Gold | Real Estate | Goals | Tax | Personal Info

### Frontend Architecture
```
components/ui/      → Generic, no domain knowledge (StatCard, DataTable, Skeleton, ProgressBar, Pagination)
components/charts/  → All Recharts wrappers isolated here ('use client' boundary)
components/domain/  → Domain-specific components (HoldingsTable, GoalCard, FDDetailCard, TaxLotTable)
hooks/              → All data fetching — never raw axios in components
lib/api.ts          → Fully typed API client; all calls go through here
lib/formatters.ts   → formatINR, formatPct, formatXIRR (handles null → '—'); never format inline in JSX
constants/index.ts  → Asset type labels, colors, thresholds, NAV_TABS — no magic strings in components
```
- **Server vs Client Components**: default Server; `'use client'` only for charts, forms, sliders
- **Loading states**: `<Skeleton />` per section — no full-page spinners
- **Error Boundaries**: wrap all chart sections

---

## Known Fixes Applied (docs were stale)
1. `api-routes.md` — added `RSU` to asset_type enum; added `VEST` to transaction type enum
2. Frontend directory is `frontend/app/` (no `/src/` prefix — App Router directly in `frontend/`)
3. NPS returns: MARKET_BASED (not VALUATION_BASED); NAV auto-fetched from npsnav.in
4. `requirements.md` mentions React+Vite — project uses Next.js (ignore)
5. Test conftest fixture is `db` (not `test_db`) — in-memory SQLite session used in integration tests

---

## PPF / EPF Import

### PPF CSV Parser (`backend/app/importers/ppf_csv_parser.py`)
- Parses SBI PPF account statement CSVs; account number from header; bank from IFSC first 4 chars
- Asset name: `"PPF - {bank_name}"` (e.g. "PPF - SBI")
- `txn_id`: `ppf_csv_` + SHA256(account_number|txn_type|date_iso|amount_paise)
- "INTEREST" in details → `INTEREST`; other credits → `CONTRIBUTION`; debits → `WITHDRAWAL`
- Service auto-creates one `Valuation` from closing balance

### EPF PDF Parser (`backend/app/importers/epf_pdf_parser.py`)
- Parses **page 1 only** of EPFO member passbook PDFs (page 2 = "Taxable Data" — causes duplicates)
- **"Cont. For MMYYYY" rows** → up to 3 CONTRIBUTION transactions (Employee / Employer / EPS)
- **CR rows without "Cont. For"** (transfer-ins) → CONTRIBUTION with "Transfer In - *" notes
- **"Int. Updated upto" rows** → 3 separate INTEREST transactions (Employee / Employer / EPS)
- **"Deduction of TDS" row** → INTEREST with negative amount
- **"Claim: Against PARA 57(1)" row** → 1 TRANSFER transaction
- EPF asset always `is_active=True`; invested = sum CONTRIBUTION outflows; current = invested + INTEREST inflows − TDS

### PPFEPFImportService (`backend/app/services/ppf_epf_import_service.py`)
- Direct import (no preview/commit); raises `NotFoundError` (→ 404) if asset doesn't exist
- `POST /import/ppf-csv` — returns `{inserted, skipped, valuation_created, ...}`
- `POST /import/epf-pdf` — returns `{inserted, skipped, epf_valuation_created, ...}`

### EPF Manual Contribution CLI (`add epf-contribution`)
- `--employee-share` required; `--eps-share` defaults 1250; `--employer-share` defaults `employee - eps`
- Stable txn_ids via `"epf_" + sha256("|".join(parts))` — must match PDF parser exactly
- Catch `SystemExit` and check `"409" in str(exc)` to treat duplicates as skipped

### EPS Convention
- No separate EPS asset; all contributions roll up to EPF asset with `notes="Pension Contribution (EPS)"`

---

## Fidelity RSU Import

### Fidelity RSU CSV Parser (`backend/app/importers/fidelity_rsu_csv_parser.py`)
- Filename must be `{MARKET}_{TICKER}.csv` (e.g. `NASDAQ_AMZN.csv`)
- Creates `VEST` transactions; `txn_id`: `fidelity_rsu_` + SHA-256[:16] of `ticker|date|qty_int|cost_int`
- `exchange_rates` dict maps `"YYYY-MM"` → USD/INR; missing month → error per row
- Footer detection uses month-abbreviation allowlist (not `isalpha()`)
- Call `extract_required_month_years(file_bytes)` before `parse()`

### Fidelity Sale PDF Parser (`backend/app/importers/fidelity_pdf_parser.py`)
- Uses `pdfplumber`; ticker from `"TICK: Company Name"` line
- `txn_id`: `fidelity_sale_` + SHA-256[:16] of `ticker|date_sold|date_acquired|qty_int`
- PDF gain/loss can be `+ $0.00` (space between sign and `$`) — regex uses `[+\-]?\s*\$`
- Call `extract_required_month_years(file_bytes)` before `parse()`

### forex_rate field
- `ParsedTransaction.forex_rate: Optional[float]` — USD/INR at import time; persisted to `Transaction.forex_rate`
- `currency="USD"` set automatically on `STOCK_US` assets created via Fidelity import

### API Endpoints
- `POST /import/fidelity-rsu-csv` — file + `exchange_rates` JSON form field; 422 if any month missing
- `POST /import/fidelity-sale-pdf` — same pattern; both use `_fidelity_preview()` helper in `api/imports.py`

### CLI Pattern for New Importers
- Call `_check_file(file_path)` as first line (user-friendly error on bad path)
- CLI calls `extract_required_month_years()` directly — never duplicate the regex inline

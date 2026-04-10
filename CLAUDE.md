# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Financial Portfolio Tracker — Claude Context

## Project Overview
Personal, local-first, single-user investment portfolio tracker.
- **Backend:** Python 3.11+ FastAPI + SQLAlchemy + Alembic (`backend/`)
- **Frontend:** Next.js App Router + Recharts + axios (`frontend/`)
- **DB:** SQLite locally → PostgreSQL in cloud (one `DATABASE_URL` env var switches)

---

## Commands

### Backend
```bash
cd backend

# Install dependencies (uses uv lockfile — recommended)
uv sync --all-extras

# Run dev server (on startup: seeds interest rates, auto-matures past-due FDs, backfills missing EPF monthly contributions)
uvicorn app.main:app --reload
```

### CLI (requires server running at localhost:8000)
```bash
cd backend

# First-time setup wizard (empty DB only — guides through all asset types interactively)
python cli.py quick-start

# Member management (must exist before any import)
python cli.py add-member --pan ABCDE1234F --name "Dhiraj"

# All import commands require --pan (resolved to member_id via GET /members)
python cli.py import ppf <file> --pan ABCDE1234F
python cli.py import epf <file> --pan ABCDE1234F
python cli.py import cas <file> --pan ABCDE1234F
python cli.py import nps <file> --pan ABCDE1234F
python cli.py import zerodha <file> --pan ABCDE1234F
python cli.py import fidelity-rsu <file> --pan ABCDE1234F   # RSU holding CSV
python cli.py import fidelity-sale <file> --pan ABCDE1234F  # tax-lot sale PDF
```

### Backend (tests)
```bash
cd backend

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
- **Backend** (`backend/.env`): Always check database url in .env file before querying database directly
- **Frontend** (`frontend/.env.local`): `NEXT_PUBLIC_API_URL=http://localhost:8000`

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

### CLI (`cli.py`)
- Thin HTTP client over the REST API — all logic lives in services, not the CLI
- Server must be running (`uvicorn app.main:app --reload`) before any CLI command
- Covers: imports (PPF/EPF/CAS/NPS/Zerodha/Fidelity), price refresh, snapshot, backup, goal management
- Never add business logic to `cli.py`; add an API endpoint and call it from the CLI

### Monetary Amounts
- **DB:** Signed integers in **paise** (1 INR = 100 paise)
  - Negative = outflow: `BUY`, `SIP`, `CONTRIBUTION`, `VEST`, `SWITCH_IN`, `BILLING`
  - Positive = inflow: `SELL`, `REDEMPTION`, `DIVIDEND`, `INTEREST`, `WITHDRAWAL`, `BONUS`, `SWITCH_OUT`
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

### Members
- `members` table: PAN-identified household members (`id`, `pan`, `name`, `is_default`, `created_at`)
- `member_id` FK on `assets`, `important_data`, `portfolio_snapshots` (NOT NULL)
- **API:** `GET /members`, `POST /members` (PAN validated, 409 on duplicate)
- Most list endpoints accept optional `?member_ids=1,2` (comma-separated); omit = all members
- Tax endpoints (`/tax/summary`, `/tax/unrealised`, `/tax/harvest-opportunities`) require `?member_id=<id>` (single, per-PAN)
- Snapshots are stored per-member; listing returns date-aggregated totals
- **CLI:** `add-member --pan ABCDE1234F --name "Dhiraj"`; all import commands require `--pan <PAN>`; `resolve_member_id(pan)` looks up via `GET /members` and exits with a helpful message if not found — **member must exist before first import**
- **Frontend:** Global `MemberSelector` multi-select in header (persisted to localStorage); tax page has independent single-select picker

### Asset Types
`STOCK_IN`, `STOCK_US`, `MF`, `FD`, `RD`, `PPF`, `EPF`, `NPS`, `GOLD`, `SGB`, `REAL_ESTATE`, `RSU`

### Transaction Types
`BUY`, `SELL`, `SIP`, `REDEMPTION`, `DIVIDEND`, `INTEREST`, `CONTRIBUTION`, `WITHDRAWAL`, `SWITCH_IN`, `SWITCH_OUT`, `BONUS`, `SPLIT`, `VEST`, `TRANSFER`

- `SPLIT` → excluded from XIRR calculations
- `VEST` → RSU vesting event (treated as `STOCK_US`); perquisite tax noted in `notes` field
- `TRANSFER` → EPF withdrawal/transfer out (Claim: Against PARA 57(1)); positive amount (inflow)

### RSUs
- Asset type: `STOCK_US`
- Transaction type: `VEST` (distinct from `BUY` to preserve vesting history)
- Perquisite tax at vest (income tax on FMV) tracked in `notes` field only — no separate tax module

### US Stock Lot Matching (Fidelity)
Fidelity sale PDFs carry per-row `acquisition_date`, enabling specific-lot tax accounting.

**Pipeline (runs at import commit time):**
1. `FidelityPDFImporter` emits `SELL`-only `ParsedTransaction` with `acquisition_date` set; no BUY emitted
2. `FidelityPreCommitProcessor` (`post_processors/fidelity.py`) runs inside `ImportOrchestrator.commit()` before the DB write loop:
   - Queries existing `BUY`/`VEST` txns for the asset on `acquisition_date` (FIFO among same-date lots)
   - Splits each SELL into partial-SELLs pinned to specific `lot_id`s
   - **Sell-to-cover** (acquisition_date == date_sold): synthetic `BUY + SELL` pair on same date
   - **Orphaned sale** (no matching lots and dates differ): synthetic `BUY + SELL` pair
3. `match_lots()` in `engine/lot_engine.py`: if `sell.lot_id` found → specific-lot; otherwise FIFO fallback with warning log

**Key invariant:** `FidelityPDFImporter.txn_id` = `SHA-256(ticker|date_sold|date_acquired|quantity)` — stable across re-imports.

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

**Strategy extra hooks (used by portfolio aggregations):**
- `get_portfolio_cashflows()` on `ValuationBasedStrategy`: inactive asset → `[]`; active → outflows only (avoids double-counting INTEREST embedded in terminal `current_value`)
- `get_inactive_realized_gain()` on `ValuationBasedStrategy`: `current_value − invested`; FD/RD override to use `fd_detail.maturity_amount` directly
- `FDStrategy` and `RDStrategy` override `compute()` directly — XIRR terminal cashflow is contractual maturity amount, not today's accrued value
- `EPFStrategy.build_cashflows()`: INTEREST txns excluded — they're internal accumulation; base `compute()` appends `current_value` (= invested + interest) as the terminal inflow

**Strategy hierarchy:**
```
AssetReturnsStrategy (ABC, template method)
├── MarketBasedStrategy          stcg_days: ClassVar[int]; compute_lots = FIFO lot engine
│   ├── StockINStrategy          stcg_days=365
│   ├── StockUSStrategy          stcg_days=730; override get_invested_value (USD→INR at vest)
│   ├── RSUStrategy              stcg_days=730; override build_cashflows (VEST unit calc)
│   ├── MFStrategy               stcg_days=365
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

### GoalAllocation Rules
- `allocation_pct` is set explicitly per `(asset, goal)` pair
- **Sum of `allocation_pct` across ALL goals for one asset must equal exactly 100%** (or 0 if no allocations exist)
- Must be a **whole number and a multiple of 10** (10, 20, 30 ... 100)

### Tax Module
- **Rates are config-driven:** `config/tax_rates/2024-25.yaml`, `config/tax_rates/2025-26.yaml`
- **API endpoints:** `GET /tax/summary?fy=2024-25`, `GET /tax/unrealised`, `GET /tax/harvest-opportunities`
- **Slab rate:** injected via `SLAB_RATE` env var (default 30%); read in `dependencies.py` → `TaxService`
- **Response shape:** `GET /tax/summary` returns `entries` grouped by `asset_class` (EQUITY/DEBT/GOLD/REAL_ESTATE), each with `asset_breakdown[]` per asset and `slab_rate_pct` label
- **Strategy hierarchy** (`services/tax/strategies/`): mirrors returns strategies — `TaxGainsStrategy` ABC, `FifoTaxGainsStrategy` base, leaf classes registered via `@register_tax_strategy`
  - Adding a new asset type: create a 3-line leaf in `services/tax/strategies/` with `@register_tax_strategy(("TYPE", "*"))`
  - Auto-import in `services/tax/strategies/__init__.py` populates registry on startup
  - Skipped types (no capital gains): `EPF`, `PPF`, `NPS`, `SGB`, `RSU`

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

---

## Backend Architecture

```
api/
  *.py             → HTTP only: parse request → call service → return response model
                     No db: Session. No repo imports. No business logic.
                     Routes live directly in app/api/ (e.g. assets.py, returns.py, corp_actions.py)
  dependencies.py  → ALL concrete wiring. Every service factory lives here.
                     Rule: no other file may instantiate a concrete service or repo.

services/
  returns/
    strategies/
      base.py                → AssetReturnsStrategy ABC (template method)
      market_based.py        → MarketBasedStrategy (units × price NAV, FIFO lots)
      valuation_based.py     → ValuationBasedStrategy (latest Valuation entry)
      asset_types/           → One 3-line leaf class per asset type (@register_strategy)
      registry.py            → DefaultReturnsStrategyRegistry; IReturnsStrategyRegistry protocol
    returns_service.py       → Thin wrapper: single asset via strategy registry
    portfolio_returns_service.py → Portfolio-level aggregations (breakdown, allocation, gainers, overview, lots)
  imports/
    orchestrator.py    → ImportOrchestrator: unified preview/commit flow (handles PPF/EPF valuations)
                         Calls importer.validate() for post-parse validation
                         Runs post-processors; fires ImportCompletedEvent
    deduplicator.py    → InMemoryDeduplicator / DBDeduplicator (pure, injectable)
    preview_store.py   → TTL store for pending previews
    post_processors/
      base.py          → IPostProcessor protocol
      stock.py         → marks asset inactive when net_units ≤ 0
      mf.py            → persists CAS snapshots
      ppf.py           → creates valuation from PPF CSV import
      epf.py           → ensures EPF asset always is_active=True
      fidelity.py      → FidelityPreCommitProcessor: resolves SELL lot_ids from acquisition_date before DB write
  tax/
    strategies/
      base.py         → AssetTaxGainsResult dataclass, TaxGainsStrategy ABC, TaxStrategyRegistry
      fifo_base.py    → FifoTaxGainsStrategy (FIFO lot matching, ST/LT classification, tax computation)
      __init__.py     → auto-imports all strategy modules to trigger @register_tax_strategy
      indian_equity.py, foreign_equity.py, gold.py, debt_mf.py, accrued_interest.py, real_estate.py
  event_bus.py              → SyncEventBus + IEventBus protocol + ImportCompletedEvent
  price_feed.py             → BasePriceFetcher ABC + @register_fetcher; staleness on class
  tax_service.py            → uses IUnitOfWorkFactory + TaxStrategyRegistry; dispatches by (asset_type, asset_class)
  corp_actions_service.py   → fetches NSE corp actions (bonus, split, dividend) and applies transactions
  important_data_service.py → key-value store for bank accounts, MF folios, identity docs, insurance
  epf_auto_contrib_service.py → backfills missing EPF monthly CONTRIBUTION rows on startup
  snapshot_service.py
  deposits_service.py

repositories/
  interfaces.py       → Protocol definitions (duck-typed; existing repos satisfy without changes)
  unit_of_work.py     → UnitOfWork context manager; exposes all repos as attributes
                        On success: commits. On exception: rolls back. Repos have NO db.commit().
  *.py                → All DB queries here. No db.commit() calls — UoW commits.

importers/
  base.py             → BaseImporter ABC + ValidationResult dataclass
                        source / format / asset_type ClassVars
                        parse() → ImportResult
                        validate() → ValidationResult (post-parse validation hook)
  registry.py         → @register_importer decorator + ImporterRegistry
  pipeline.py         → ImportPipeline: parse → validate → deduplicate
  helpers/
    exchange_rate_validation_helper.py → Fidelity exchange_rates JSON validation
  *_importer.py       → Concrete importers; each decorated with @register_importer
                        Fidelity importers override validate() for exchange_rates checking

engine/
  lot_engine.py       → stcg_days accepted as parameter (not hardcoded per asset type)
  lot_helper.py       → LotHelper class + _Lot/_Sell dataclasses + LOT_TYPES/SELL_TYPES constants
                        Import _Lot/_Sell/LOT_TYPES/SELL_TYPES from here (NOT from market_based.py) — circular import otherwise
  tax_engine.py       → TaxRatePolicy + TaxRate dataclass; reads config/tax_rates/{FY}.yaml
  mf_classifier.py    → ISchemeClassifier protocol + DefaultSchemeClassifier
  mf_scheme_lookup.py → lazy-loaded ISIN → (scheme_code, category) lookup from config/mf_scheme_codes/mf_schemes.csv
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
- **All wiring in `app/api/dependencies.py`** — the only file where concrete service/repo types appear
- Services declare abstract dependencies (`IUnitOfWorkFactory`, `IReturnsStrategyRegistry`, etc.) in `__init__` — never instantiate anything internally
- **Rule:** No service file may contain the word `Session` or import a concrete repo class

### UnitOfWork Pattern
- Services use `with self._uow_factory() as uow:` for all DB access
- All writes in the block commit atomically on exit; any exception triggers full rollback
- Repositories have **no `db.commit()` calls** — commit is solely the UoW's responsibility

### API Layer — No Direct DB Access
- API routes (`api/*.py`) call services only — never import repos, `UnitOfWork`, or `Session`
- Business logic belongs in services; API layer is HTTP parsing + response serialization only
- Violations break DI contract and make routes untestable in isolation

---

## Frontend — Key Decisions

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
---


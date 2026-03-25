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

# Install dependencies (uses uv lockfile)
pip install -e ".[dev]"

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
python cli.py list assets
python cli.py refresh-prices
python cli.py snapshot
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
| Groww CSV | Native `order_id` from file |
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
```
MARKET_BASED  = STOCK_IN, STOCK_US, MF, RSU, GOLD, SGB, NPS
                → current_value = total_units × price_cache NAV
FD_BASED      = FD, RD
                → current_value = formula (compound interest)
EPF_BASED     = EPF
                → total_invested = sum of all CONTRIBUTION outflows (employee + employer + EPS + transfer-ins)
                → current_value  = total_invested + sum of all INTEREST inflows (employee + employer + EPS − TDS)
                → EPF asset is always is_active=True (never auto-set inactive)
VALUATION_BASED = PPF, REAL_ESTATE
                → current_value = latest Valuation entry (manual passbook)
```
- NPS moved to MARKET_BASED (from VALUATION_BASED) — units tracked via CONTRIBUTION transactions, NAV auto-fetched
- Valuation entries for NPS are no longer required or used
- For VALUATION_BASED assets with no Valuation entry: `total_invested` still shows from transactions; `current_value`/XIRR/P&L are null

### NPS Price Feed (npsnav.in)
- **Source:** `https://npsnav.in/api`
- **Bulk scheme resolution (once per `refresh_all`):**
  1. `GET /api/schemes` → all 150+ scheme codes + names (one call for all NPS funds)
  2. Fuzzy-match each NPS asset name via `SequenceMatcher` (threshold 0.6)
  3. Persist resolved SM code to `asset.identifier`; always uses latest fetched code (overwrites stored if different)
- **Per-asset NAV:** `GET /api/{scheme_code}` → plain-text float
- **Standalone `refresh_asset`:** falls back to a single `/api/schemes` call
- **Staleness:** 1 day (same as MF)
- If `asset.identifier` already starts with `SM`, used directly without scheme lookup

### GoalAllocation Rules
- `allocation_pct` is set explicitly per `(asset, goal)` pair
- **Sum of `allocation_pct` across ALL goals for one asset must equal exactly 100%** (or 0 if no allocations exist)
- Must be a **whole number and a multiple of 10** (10, 20, 30 ... 100)
- Violation → API returns 422
- `current_value_toward_goal = asset_current_value × allocation_pct / 100`

### Tax Module (Phase 5 — complete)
- **FY2024-25 rates only** (no historical rate table needed):
  - `STOCK_IN` / equity `MF`: STCG 20% (<1yr), LTCG 12.5% (≥1yr), ₹1.25L exemption
  - `STOCK_US` / `RSU`: STCG at slab (<2yr), LTCG 12.5% (≥2yr)
  - Debt `MF` (post Apr 2023): slab rate regardless of holding period
  - `GOLD` / `SGB`: STCG slab (<3yr), LTCG 12.5% (≥3yr); SGB held to maturity = tax-free
  - `REAL_ESTATE`: STCG slab (<2yr), LTCG 12.5% (≥2yr)
  - `FD` / `RD` / `EPF` (above threshold): slab rate; `PPF`: EEE (fully exempt)
- **API endpoints:** `GET /tax/summary?fy=2024-25`, `GET /tax/unrealised`, `GET /tax/harvest-opportunities`
- **Frontend tax page:** FY selector, 4 stat cards, realized/unrealized gains rolled up to 4 broad categories (Equity / Debt / Gold / Real Estate), harvest table per asset with pagination

### Price Feeds
| Asset | Source | Identifier field | Stale after |
|---|---|---|---|
| MF NAV | mfapi.in | `mfapi_scheme_code` (auto-discovered by name search) | 1 day |
| NPS NAV | npsnav.in (bulk scheme lookup) | `identifier` = SM code (auto-discovered) | 1 day |
| NSE/BSE stocks | yfinance `.NS` | `name` = NSE ticker | 6 hours |
| US stocks + forex | yfinance + `USDINR=X` | `identifier` = ticker | 6 hours |
| Gold | yfinance `GC=F` → INR/gram | — | 6 hours |
| FD/RD | Formula-computed | — | Never |
| PPF / EPF / Real Estate | Latest `Valuation` entry | — | Never |

### Startup Behaviour
- FastAPI lifespan event on startup:
  1. Seeds interest rates (idempotent)
  2. Runs `DepositsService.mark_matured_fds()` — marks FDs/RDs past their maturity date as `is_matured=True` / `is_active=False`, and back-fills `maturity_amount` if missing
- Price refresh is **on-demand only** via `python cli.py refresh-prices`; it is no longer triggered automatically on startup

### DepositsService (`backend/app/services/deposits_service.py`)
- `mark_matured_fds()` — queries active FD/RD assets whose `maturity_date < today` and `is_matured=False`; for each, computes `maturity_amount` from `fd_engine` formulas if not already stored, sets `is_matured=True`, sets `asset.is_active=False`, commits once at the end
- Called automatically on startup; safe to call repeatedly (idempotent)

### FD vs RD in FDDetail
- `fd_type = FD` → `principal_amount` = lump-sum deposit (paise)
- `fd_type = RD` → `principal_amount` = **monthly installment** (paise); total principal computed from `CONTRIBUTION` transactions

### PPF/EPF XIRR
- Requires at least one `Valuation` entry (manual passbook update)
- Returns `null` XIRR with explanatory message if no Valuation exists

---

## Frontend — Key Decisions

### P&L Display (no ST/LT detail on listing pages)
- **Current P&L** = unrealized gains (st_unrealised + lt_unrealised) if lot-based, else current − invested
- **All-time P&L** = unrealized + realized (all 4 lot fields) if lot-based, else same as Current P&L
- ST/LT breakdown removed from HoldingsTable and AssetSummaryCards — detail only on the Tax page
- `AssetSummaryCards` always shows 5 cards: Invested | Current Value | Current P&L (with %) | All-time P&L | XIRR
- `HoldingsTable` columns: Name | Type | Invested | Current Value | Current P&L (INR + % sub) | All-time P&L | XIRR
- Deposit assets (FD/RD) show an extra row below the 5 cards: Taxable Interest | Est. Tax (30%)

### Asset Ordering
- All asset listing pages sort by `current_value` descending (nulls last) — implemented in `useAssetsWithReturns`

### Overview Breakdown Table
- "Summary by Asset Type" table includes Current P&L and All-time P&L columns
- All-time P&L includes inactive/closed asset net transactions (realized gains from sold positions)

### Nav Tabs
Defined in `constants/index.ts` → `NAV_TABS`:
Overview | Stocks | Mutual Funds | Deposits | PPF | EPF | NPS | US Stocks | Gold | Real Estate | Goals | Tax | Personal Info

---

## Coding Standards

### TDD Workflow (mandatory)
```
1. Write failing test  →  2. pytest (RED)  →  3. Write minimum code  →  4. pytest (GREEN)  →  5. Refactor
```
- **No code without a failing test first.**
- Coverage targets: `pytest --cov=app --cov-fail-under=80`; engine functions ≥ 90%; importers ≥ 85%
- Test deps: `pytest`, `pytest-cov`, `pytest-mock`, `httpx`, `factory-boy`

### Dependency Injection
- **DB session**: always via `Depends(get_db)` — never create `Session()` manually in routes
- **Services are injectable classes** — enables DI override in tests without mocking
- **Test override**: `app.dependency_overrides[get_db] = lambda: test_db_session`

### Backend Architecture (strictly enforced)
```
api/          → HTTP only: parse request, call service, return response. NO business logic.
services/     → Injectable classes. Orchestration: calls repositories + engines.
engine/       → Pure functions only: (data_in) → result. NO db param, NO side effects.
repositories/ → All DB queries live here. Never inline in routes or services.
importers/    → One class per source, all implement BaseImporter protocol.
```

- **Exception hierarchy**: `AppError → NotFoundError / DuplicateError / ValidationError`
- **Pydantic `MoneyMixin`**: centralize paise↔INR conversion; Response schemas always return INR decimal
- **Strategy pattern** for importers and price fetchers
- **Logging**: `logging` module only. `WARNING` for failed fetches; `INFO` for imports/refreshes

### Test Structure
```
tests/
├── conftest.py          # Shared: in-memory SQLite fixture, TestClient, DI overrides
├── factories.py         # make_asset(), make_transaction(), make_cashflow() helpers
├── fixtures/            # Static files: sample_cas.pdf, zerodha_tradebook.csv, nps_sample.csv
├── unit/
│   ├── conftest.py      # Unit-specific fixtures (no DB, no HTTP)
│   └── test_*.py        # Pure engine function tests — zero mocking needed
└── integration/
    ├── conftest.py      # Seeded DB state fixtures
    └── test_*.py        # TestClient tests against in-memory SQLite
```

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
3. NPS returns: moved from VALUATION_BASED to MARKET_BASED; NAV auto-fetched from npsnav.in
4. `requirements.md` mentions React+Vite — project uses Next.js (ignore)

---

## PPF / EPF Import (Phase 2 extension)

### PPF CSV Parser (`backend/app/importers/ppf_csv_parser.py`)
- Parses SBI PPF account statement CSVs (bank-exported format)
- Account number extracted from CSV header; bank name derived from IFSC code (first 4 chars)
- Asset name format: `"PPF - {bank_name}"` (e.g. "PPF - SBI")
- `txn_id`: `ppf_csv_` + SHA256(account_number|txn_type|date_iso|amount_paise)
- Credit rows with "INTEREST" in details → `INTEREST` (positive inflow); other credits → `CONTRIBUTION` (negative outflow); debits → `WITHDRAWAL`
- Returns `PPFCSVImportResult` with: `account_number`, `bank_name`, `asset_name`, `closing_balance_inr`, `closing_balance_date`
- Service auto-creates one `Valuation` entry from the closing balance

### EPF PDF Parser (`backend/app/importers/epf_pdf_parser.py`)
- Parses **page 1 only** of EPFO member passbook PDFs — page 2 is "Taxable Data" with different interest splits that would create duplicates
- Extracts member_id, establishment_name, print_date (from Hindi `eqfnzr/Printed On DD-MM-YYYY` line)
- **"Cont. For MMYYYY" rows** → up to 3 CONTRIBUTION transactions (skip if amount=0):
  - notes="Employee Share" (employee EPF)
  - notes="Employer Share" (employer EPF)
  - notes="Pension Contribution (EPS)" (pension/EPS)
- **CR rows without "Cont. For"** (transfer-ins from old employer) → CONTRIBUTION transactions:
  - notes="Transfer In - Employee Share" / "Transfer In - Employer Share" / "Transfer In - Pension (EPS)"
- **"Int. Updated upto DD/MM/YYYY" rows** → 3 separate INTEREST transactions:
  - notes="Employee Interest", notes="Employer Interest", notes="EPS Interest"
  - EPS interest recorded even when 0 (for data completeness)
  - If row absent (shows "Interest details N/A") → no interest txns created for that year
- **"Deduction of TDS" row** → INTEREST transaction(s) with negative amount (notes="TDS Deduction")
- **"Claim: Against PARA 57(1)" row** → 1 TRANSFER transaction using print_date
- Returns `EPFImportResult` with: `member_id`, `establishment_name`, `print_date`, `net_balance_inr`, grand totals
- **Invested value** = sum of all CONTRIBUTION outflows (employee + employer + EPS + transfer-ins)
- **Current value** = invested + sum of all INTEREST inflows (employee + employer + EPS − TDS deductions)

### TRANSFER Transaction Type
- Added `TRANSFER = "TRANSFER"` to `TransactionType` enum in `backend/app/models/transaction.py`
- Alembic migration: `a1b2c3d4e5f6_add_transfer_transaction_type.py` (no-op for SQLite, ALTER TYPE for PostgreSQL)
- Frontend `TransactionType` union in `frontend/types/index.ts` updated to include `'TRANSFER'`

### EPS Convention (no separate asset)
- Pension/EPS contributions are imported as CONTRIBUTION transactions on the EPF asset with `notes="Pension Contribution (EPS)"`
- No separate EPS asset is created; employee + employer + EPS all roll up into the single EPF asset

### PPFEPFImportService (`backend/app/services/ppf_epf_import_service.py`)
- Direct import pattern (no preview/commit step)
- `import_ppf_csv(file_bytes)`: matches PPF asset by identifier (account number), deduplicates by txn_id, creates Valuation
- `import_epf(file_bytes)`: matches EPF asset by member_id, imports all transactions under it, creates EPF Valuation; EPF asset is never set inactive
- Both methods raise `NotFoundError` (→ HTTP 404) if the asset does not exist

### API Endpoints
- `POST /import/ppf-csv` — returns `{inserted, skipped, valuation_created, valuation_value, valuation_date, account_number, errors}`
- `POST /import/epf-pdf` — returns `{inserted, skipped, epf_valuation_created, epf_valuation_value, errors}`

### EPF Manual Contribution CLI (`add epf-contribution`)
- Use after initial PDF import for ongoing monthly contributions
- `--employee-share` is the only required arg; `--eps-share` defaults to 1250; `--employer-share` defaults to `employee-share − eps-share`
- Generates stable txn_ids via `_epf_txn_id(*parts)` = `"epf_" + sha256("|".join(parts))` — must match the PDF parser's scheme exactly to prevent cross-source duplicates
- Interest args (`--employee-interest`, `--employer-interest`, `--eps-interest`) are optional; each creates a separate INTEREST transaction (positive inflow)
- CLI `_api()` calls `sys.exit` on any non-2xx; catch `SystemExit` and check `"409" in str(exc)` to treat duplicates as skipped (see `cmd_add_epf_contribution`)

### EPF Page (frontend)
- `frontend/app/epf/page.tsx` shows all EPF assets in a single HoldingsTable with `showNotes` enabled
- Notes column shows the asset's notes field (no separate EPS sub-section)

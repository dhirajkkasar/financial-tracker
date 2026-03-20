# Financial Portfolio Tracker — Claude Context

## Project Overview
Personal, local-first, single-user investment portfolio tracker.
- **Backend:** Python 3.11+ FastAPI + SQLAlchemy + Alembic (`backend/`)
- **Frontend:** Next.js App Router + Recharts + axios (`frontend/` — existing `/src/app/` structure)
- **DB:** SQLite locally → PostgreSQL in cloud (one `DATABASE_URL` env var switches)
- **Plan:** `/Users/dhirajkasar/.claude/plans/abstract-baking-sparkle.md` (7 phases, ~85 tasks)

## Running Locally
```bash
# Backend
cd backend
pip install -e .
alembic upgrade head
python scripts/seed_interest_rates.py   # idempotent, also runs on startup
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Authoritative Docs (in repo root)
| File | Authority |
|---|---|
| `requirements.md` (v0.3) | Schema, asset types, tax rules, UI tab structure |
| `api-routes.md` | API contract — backend + frontend must match exactly |
| `data_model.md` | Idempotency strategy, data shapes |
| `tech_decisions.md` | Monorepo layout, design principles |
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
`BUY`, `SELL`, `SIP`, `REDEMPTION`, `DIVIDEND`, `INTEREST`, `CONTRIBUTION`, `WITHDRAWAL`, `SWITCH_IN`, `SWITCH_OUT`, `BONUS`, `SPLIT`, `VEST`

- `SWITCH_IN` / `SWITCH_OUT` / `SPLIT` → excluded from XIRR calculations
- `VEST` → RSU vesting event (treated as `STOCK_US`); perquisite tax noted in `notes` field

### RSUs
- Asset type: `STOCK_US`
- Transaction type: `VEST` (distinct from `BUY` to preserve vesting history)
- Perquisite tax at vest (income tax on FMV) tracked in `notes` field only — no separate tax module

### GoalAllocation Rules
- `allocation_pct` is set explicitly per `(asset, goal)` pair
- **Sum of `allocation_pct` across ALL goals for one asset must equal exactly 100%** (or 0 if no allocations exist)
- Must be a **whole number and a multiple of 10** (10, 20, 30 ... 100)
- Violation → API returns 422
- `current_value_toward_goal = asset_current_value × allocation_pct / 100`

### Tax Rates
- **FY2024-25 rates only** (no historical rate table needed):
  - `STOCK_IN` / equity `MF`: STCG 20% (<1yr), LTCG 12.5% (≥1yr), ₹1.25L exemption
  - `STOCK_US` / `RSU`: STCG at slab (<2yr), LTCG 12.5% (≥2yr)
  - Debt `MF` (post Apr 2023): slab rate regardless of holding period
  - `GOLD` / `SGB`: STCG slab (<3yr), LTCG 12.5% (≥3yr); SGB held to maturity = tax-free
  - `REAL_ESTATE`: STCG slab (<2yr), LTCG 12.5% (≥2yr)
  - `FD` / `RD` / `EPF` (above threshold): slab rate; `PPF`: EEE (fully exempt)

### Price Staleness
| Asset | Source | Stale after |
|---|---|---|
| MF NAV | mfapi.in | 1 day post 9PM IST |
| NSE/BSE stocks | yfinance (`ticker.NS` / `.BO`) | 6 hours |
| US stocks + forex | yfinance + `USDINR=X` | 6 hours |
| Gold | yfinance `GC=F` → INR/gram (÷31.1035 × USD/INR) | 6 hours |
| NPS NAV | Manual entry | Never via price feed |
| FD/RD | Formula-computed | Never (no feed) |
| PPF / EPF / Real Estate | Latest `Valuation` entry | Never via price feed |

### FD vs RD in FDDetail
- `fd_type = FD` → `principal_amount` = lump-sum deposit (paise)
- `fd_type = RD` → `principal_amount` = **monthly installment** (paise); total principal computed from `CONTRIBUTION` transactions

### PPF/EPF XIRR
- Requires at least one `Valuation` entry (manual passbook update)
- Return `null` XIRR with explanatory message if no Valuation exists

---

## Coding Standards

### TDD Workflow (mandatory)
```
1. Write failing test  →  2. pytest (RED)  →  3. Write minimum code  →  4. pytest (GREEN)  →  5. Refactor
```
- **No code without a failing test first.** If a test passes before writing any implementation, the test is wrong.
- Coverage targets: `pytest --cov=app --cov-fail-under=80`; engine functions ≥ 90%; importers ≥ 85%
- Test deps: `pytest`, `pytest-cov`, `pytest-mock`, `httpx`, `factory-boy`

### Dependency Injection
- **DB session**: always via `Depends(get_db)` — never create `Session()` manually in routes
- **Services are injectable classes** (not plain functions) — enables DI override in tests without mocking:
  ```python
  class PriceService:
      def __init__(self, db: Session): self.db = db
  def get_price_service(db: Session = Depends(get_db)) -> PriceService:
      return PriceService(db)
  # In routes:
  def refresh(svc: PriceService = Depends(get_price_service)): ...
  ```
- **Auth** applied at router level: `app.include_router(router, dependencies=[Depends(verify_token)])`
- **Test override** (no mocking needed):
  ```python
  app.dependency_overrides[get_db] = lambda: test_db_session
  # PriceService, ImportService etc automatically receive test DB
  ```

### Backend Architecture (strictly enforced)
```
api/          → HTTP only: parse request, call service, return response. NO business logic.
services/     → Injectable classes. Orchestration: calls repositories + engines.
engine/       → Pure functions only: (data_in) → result. NO db param, NO side effects.
repositories/ → All DB queries live here. Never inline in routes or services.
importers/    → One class per source, all implement BaseImporter protocol.
```

- **Exception hierarchy**: `AppError → NotFoundError / DuplicateError / ValidationError`; single `@app.exception_handler` → never `raise HTTPException` in business logic
- **Pydantic `MoneyMixin`**: centralize paise↔INR conversion; Response schemas always return INR decimal
- **Strategy pattern** for importers and price fetchers — `IMPORTERS = {"zerodha": ZerodhaImporter, ...}`
- **Logging**: `logging` module only. `WARNING` for failed fetches/convergence; `INFO` for imports/refreshes

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
components/ui/      → Generic, no domain knowledge (StatCard, DataTable, Skeleton, ProgressBar)
components/charts/  → All Recharts wrappers isolated here ('use client' boundary)
components/domain/  → Domain-specific components (HoldingsTable, GoalCard, FDDetailCard)
hooks/              → All data fetching (useAssets, useOverview, useGoals) — never raw axios in components
lib/api.ts          → Fully typed API client; all calls go through here
lib/formatters.ts   → formatINR, formatPct, formatXIRR (handles null → '—'); never format inline in JSX
constants/index.ts  → Asset type labels, colors, thresholds — no magic strings in components
```

- **Server vs Client Components**: default Server; `'use client'` only for charts, forms, sliders, localStorage
- **No prop drilling**: pages fetch + pass one level down; use React Context if sharing across distant components
- **Error Boundaries**: wrap all chart sections (Recharts throws on bad data)
- **Loading states**: `<Skeleton />` per section — no full-page spinners

---

## Known Issues in Existing Docs (Fix During Implementation)
1. `api-routes.md` — missing `RSU` from asset_type enum; missing `VEST` from transaction type enum
2. `api-routes.md` POST `/fd-detail` — `principal_amount` field means monthly installment for RD
3. `data_model.md` — `txn_id` hash formula uses `instrument_id` (internal DB ID) → use source-system natural keys instead
4. `ui.md` — tab structure is outdated; use `requirements.md` v0.3 tab layout
5. `requirements.md` — mentions React+Vite; project uses Next.js (ignore Vite reference)

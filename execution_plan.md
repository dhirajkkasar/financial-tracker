# Financial Portfolio Tracker — Execution Plan

## Context

Building a personal, local-first investment portfolio tracker for a single user. Tracks Indian and US equities, mutual funds, FD/RD, PPF, EPF, NPS, gold/SGBs, real estate, and RSUs. Core value: accurate XIRR/CAGR, FIFO tax lot tracking, goal funding, and idempotent imports from CAS PDFs and broker CSVs.

---

## Key Decisions (Resolved)

| Decision | Resolution |
|---|---|
| Frontend | **Next.js** App Router (`frontend/app/` — no `/src/`) |
| DB amounts | **Signed integers (paise)** in DB: negative = outflow (BUY/SIP/CONTRIBUTION/VEST), positive = inflow (SELL/DIVIDEND/INTEREST/WITHDRAWAL) |
| API amounts | Decimal INR (convert to/from paise in schema layer) |
| RSUs | **STOCK_US** asset type + **VEST** transaction type. Perquisite tax tracked in notes field only. |
| Tax rate scope | **FY2024-25 rates only**: LTCG 12.5%/₹1.25L, STCG 20% for equity. |
| GoalAllocation | `allocation_pct` per (asset, goal): sum across all goals for one asset = exactly 100%, whole numbers, multiples of 10. Violation = 422. |
| `txn_id` hash | Source-system natural keys (not internal DB IDs) |
| NPS NAV | Auto-fetched from **npsnav.in/api** — bulk scheme lookup once per refresh, then per-asset NAV call |
| PPF/EPF XIRR | Requires at least one `Valuation` entry; null XIRR with message if none exists |
| NPS returns | Market-based (units × NAV from price cache), same as MF/stocks |
| Startup | Background `refresh_all` on server start via FastAPI lifespan |

---

## Architecture

### Backend (`backend/`)

```
app/
├── api/          → HTTP only: parse request, call service, return response
├── services/     → Injectable classes: orchestrates repos + engines
│   ├── price_feed.py      → MFAPIFetcher, YFinanceFetcher, GoldFetcher, NPSNavFetcher
│   ├── price_service.py   → PriceService (get/refresh/refresh_all)
│   ├── returns_service.py → ReturnsService (asset/overview/breakdown/lots/gainers)
│   ├── import_service.py  → ImportService (preview/commit, idempotent)
│   └── tax_service.py     → TaxService (summary/unrealised/harvest)
├── engine/       → Pure functions only — no DB, no side effects
│   ├── returns.py         → compute_xirr, compute_cagr, compute_absolute_return
│   ├── lot_engine.py      → match_lots_fifo, compute_lot_unrealised, compute_gains_summary
│   ├── fd_engine.py       → compute_fd_maturity, compute_fd_current_value, compute_rd_maturity
│   ├── ppf_epf_engine.py  → get_latest_valuation, get_applicable_rate
│   ├── tax_engine.py      → parse_fy, classify_holding, compute_fy_realised_gains, estimate_tax, find_harvest_opportunities
│   └── allocation.py      → compute_allocation, find_top_gainers
├── repositories/ → All DB queries here (never inline in routes/services)
├── importers/    → One class per source format (BaseImporter protocol)
│   ├── cas_parser.py
│   ├── nps_csv_parser.py
│   └── broker_csv_parser.py
├── models/       → SQLAlchemy ORM (one file per model)
├── schemas/      → Pydantic request/response schemas
└── middleware/   → Error handler (AppError hierarchy → consistent JSON)
```

**Asset type routing in returns:**
- `MARKET_BASED` = STOCK_IN, STOCK_US, MF, RSU, GOLD, SGB, **NPS** → units × price_cache NAV
- `FD_BASED` = FD, RD → formula-computed
- `VALUATION_BASED` = PPF, EPF, REAL_ESTATE → latest Valuation entry

### Frontend (`frontend/`)

```
app/                → Next.js App Router pages (Server Components by default)
components/
├── ui/             → Generic (StatCard, DataTable, Skeleton, ProgressBar, Pagination)
├── charts/         → Recharts wrappers ('use client' boundary)
└── domain/         → Domain-specific (HoldingsTable, GoalCard, FDDetailCard)
hooks/              → All data fetching (useAssetsWithReturns, useOverview, useGoals)
lib/
├── api.ts          → Fully typed axios client
└── formatters.ts   → formatINR, formatPct, formatXIRR (null → '—')
constants/index.ts  → Asset type labels, colors, XIRR thresholds, NAV_TABS
types/index.ts      → TypeScript types matching backend schemas
```

### Price Feeds

| Asset | Fetcher | Identifier field | Stale after |
|---|---|---|---|
| MF | MFAPIFetcher (mfapi.in) | `mfapi_scheme_code` (auto-discovered) | 1 day |
| NPS | NPSNavFetcher (npsnav.in) | `identifier` = SM code (auto-discovered via bulk scheme lookup) | 1 day |
| STOCK_IN | YFinanceFetcher `.NS` | `name` = NSE ticker | 6 hours |
| STOCK_US / RSU | YFinanceFetcher (USD→INR) | `identifier` = ticker | 6 hours |
| GOLD | GoldFetcher (GC=F + USDINR=X) | — | 6 hours |

**NPSNavFetcher bulk flow (refresh_all):**
1. Single call to `https://npsnav.in/api/schemes` → all scheme codes + names
2. Fuzzy-match each NPS asset name (SequenceMatcher, threshold 0.6) → scheme code
3. Persist resolved code to `asset.identifier`; use latest fetched code if different from stored
4. Per-asset: `GET https://npsnav.in/api/{code}` → plain-text NAV

---

## Tax Rules (FY2024-25)

| Asset Type | ST threshold | ST rate | LT rate | Exemption |
|---|---|---|---|---|
| STOCK_IN, equity MF | < 1 year | 20% | 12.5% | ₹1.25L LTCG |
| STOCK_US, RSU | < 2 years | Slab | 12.5% | — |
| GOLD, SGB | < 3 years | Slab | 12.5% | — |
| REAL_ESTATE | < 2 years | Slab | 12.5% | — |
| FD, RD, EPF | Always | Slab | Slab | — |
| PPF | Always | Exempt | Exempt | EEE |
| SGB (held to maturity) | — | Exempt | Exempt | — |

---

## Phase Status

### ✅ Phase 1 — Core Engine
- SQLAlchemy models, Alembic migrations, all CRUD endpoints
- Returns engine: XIRR (scipy brentq + Newton fallback), CAGR, absolute return
- FD/RD formula engine, PPF/EPF valuation-based engine
- FastAPI error middleware (AppError hierarchy)
- Interest rate seed script (idempotent, runs on startup)
- Test infrastructure: in-memory SQLite, TestClient, factories

### ✅ Phase 2 — Imports + Price Feeds
- MFAPIFetcher, YFinanceFetcher, GoldFetcher, NPSNavFetcher
- PriceService: get/refresh_asset/refresh_all (NPS bulk scheme resolution in one API call)
- CASImporter, NPSImporter, ZerodhaImporter, GrowwImporter
- ImportService: preview/commit with idempotent txn_id deduplication
- Startup lifespan: background price refresh on server start

### ✅ Phase 3 — Returns, Allocation, Asset Detail
- FIFO lot engine: match_lots_fifo, compute_lot_unrealised, compute_gains_summary
- ReturnsService: per-asset, overview, breakdown (current P&L + all-time P&L), lots, gainers
- Overview breakdown table: Current P&L + All-time P&L columns
- AssetSummaryCards: 5 cards (Invested | Current Value | Current P&L | All-time P&L | XIRR)
- HoldingsTable: Current P&L (INR + %) + All-time P&L columns (ST/LT detail removed)
- All asset listing pages sorted by current value descending

### ✅ Phase 4 — Goals Engine
- compute_goal_value, compute_sip_needed (numpy_financial.pmt)
- Goals CRUD with allocation_pct validation (sum=100%, multiple of 10)
- Goals page: progress cards, SIP calculator with rate slider
- Goal detail: linked assets table with value toward goal

### ✅ Phase 5 — Tax Module
- tax_engine.py: parse_fy, classify_holding, get_tax_rate, compute_fy_realised_gains,
  apply_ltcg_exemption, estimate_tax, find_harvest_opportunities
- TaxService: get_tax_summary, get_unrealised_summary, get_harvest_opportunities
- API: GET /tax/summary?fy=, GET /tax/unrealised, GET /tax/harvest-opportunities
- Tax page: FY selector, 4 stat cards, realized/unrealized rolled up to 4 broad categories
  (Equity / Debt / Gold / Real Estate), harvest table per asset with pagination
- 55 unit tests + 14 integration tests for tax module

### 🔲 Phase 6 — Cloud Deployment
- [ ] T6.1.1 backend/Dockerfile (Python 3.11 slim, uvicorn)
- [ ] T6.1.2 frontend/Dockerfile (Node 20 alpine)
- [ ] T6.1.3 docker-compose.yml (backend + frontend + postgres)
- [ ] T6.1.4 PostgreSQL compatibility audit
- [ ] T6.1.5 DATABASE_URL env-var switching (WAL pragma only for SQLite)
- [ ] T6.2.1 Bearer token auth middleware (API_TOKEN env var)
- [ ] T6.2.2 Next.js login page + axios interceptor + 401 redirect
- [ ] T6.3.1 GET /backup/sqlite — stream portfolio.db
- [ ] T6.3.2 GET /backup/export — structured JSON export
- [ ] T6.3.3 POST /backup/import — idempotent JSON import
- [ ] T6.4.1 Docker build + health check verification
- [ ] T6.4.2 Full test suite against PostgreSQL

### 🔲 Phase 7 — Polish
- [ ] T7.1.1 Important Data rich field templates per category
- [ ] T7.2.1 PortfolioSnapshot model + daily cron
- [ ] T7.2.3 NetWorthChart (Recharts LineChart)
- [ ] T7.3.1 HoldingsTable: client-side column sorting
- [ ] T7.3.2 HoldingsTable: "Show Inactive" toggle
- [ ] T7.3.3 Transaction list: date range filter
- [ ] T7.4.2 Async price refresh (asyncio.gather + httpx.AsyncClient)
- [ ] T7.4.3 60-second in-memory cache on GET /overview

---

## Running Locally

```bash
# Backend
cd backend
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
# Prices auto-refresh on startup via lifespan event

# Frontend
cd frontend
npm install
npm run dev
```

## Test Coverage Targets

- Engine functions (`engine/`): ≥ 90%
- API routes (`api/`): ≥ 80%
- Importers: ≥ 85%
- Overall: ≥ 80%

Run: `cd backend && pytest --cov=app --cov-fail-under=80`

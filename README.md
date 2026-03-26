# Financial Portfolio Tracker

A personal, local-first investment portfolio tracker for Indian investors. Tracks equities, mutual funds, fixed deposits, PPF/EPF/NPS, US stocks, gold, real estate, and RSUs — with accurate XIRR/CAGR, FIFO tax lot tracking, goal funding, and automated price feeds.

## Features

- **Portfolio overview** — invested, current value, current P&L, all-time P&L, XIRR across all asset types
- **Asset types** — Indian stocks, US stocks, mutual funds, FD/RD, PPF, EPF, NPS, gold, SGBs, real estate, RSUs
- **Auto price feeds** — MF NAV (mfapi.in), NPS NAV (npsnav.in), stocks/gold (yfinance), triggered on startup
- **FIFO lot engine** — per-lot unrealized/realized gains, short-term vs long-term classification
- **Tax module** — FY2024-25 realized/unrealized gains by asset class, LTCG exemption, harvest opportunities
- **Goals** — allocate assets to financial goals, SIP calculator, progress tracking
- **Imports** — idempotent CSV/PDF imports: Zerodha tradebook, Groww, NPS CSV, CAS PDF (CAMS/KFintech)
- **Personal info** — store bank accounts, MF folios, identity docs, insurance details

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic |
| Database | SQLite (local) → PostgreSQL (cloud, same `DATABASE_URL` switch) |
| Returns engine | scipy (XIRR), numpy-financial (SIP/PMT), custom FIFO lot engine |
| Price feeds | httpx + mfapi.in, npsnav.in, yfinance |
| Frontend | Next.js 15 App Router, TypeScript, Tailwind CSS, Recharts |
| Testing | pytest, pytest-cov (248 tests, 84% coverage) |

## Project Structure

```
financial-tracker/
├── backend/
│   ├── app/
│   │   ├── api/           # Route handlers (HTTP only)
│   │   ├── engine/        # Pure computation (XIRR, FIFO lots, FD/tax formulas)
│   │   ├── services/      # Orchestration (price feeds, returns, imports, tax)
│   │   ├── repositories/  # All DB queries
│   │   ├── importers/     # CAS PDF, NPS CSV, Zerodha/Groww CSV parsers
│   │   ├── models/        # SQLAlchemy ORM models
│   │   └── schemas/       # Pydantic request/response schemas
│   ├── scripts/           # Seed scripts
│   ├── tests/             # 248 tests (unit + integration)
│   └── pyproject.toml
├── frontend/
│   ├── app/               # Next.js App Router pages
│   ├── components/        # ui/, charts/, domain/
│   ├── hooks/             # Data fetching hooks
│   ├── lib/               # api.ts, formatters.ts
│   ├── types/             # TypeScript types
│   └── constants/         # Asset labels, colors, nav tabs
├── execution_plan.md      # Phase status and architecture decisions
├── CLAUDE.md              # AI assistant context and coding standards
└── api-routes.md          # API contract reference
```

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Git

### Backend

```bash
cd backend

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Set up database
alembic upgrade head

# Start server (interest rates seeded + prices refreshed automatically on startup)
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure API URL (optional — defaults to localhost:8000)
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Start dev server
npm run dev
```

The frontend runs at `http://localhost:3000`.

### Environment Variables

**Backend** (`backend/.env`):
```
DATABASE_URL=sqlite:///./portfolio.db   # SQLite (default)
# DATABASE_URL=postgresql://user:pass@host/db   # PostgreSQL (cloud)
```

**Frontend** (`frontend/.env.local`):
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Running Tests

```bash
cd backend
source .venv/bin/activate
pytest --cov=app --cov-report=term-missing
```

Coverage targets: overall ≥ 80%, engine functions ≥ 90%, importers ≥ 85%.

## Importing Data

### Mutual Funds (CAS PDF)
`POST /import/cas-pdf` — upload a CAMS or KFintech CAS PDF. Preview first, then commit.

### NPS
`POST /import/nps-csv` — upload NSDL NPS transaction statement CSV.

### Stocks
`POST /import/broker-csv?broker=zerodha` — Zerodha tradebook CSV  
`POST /import/broker-csv?broker=groww` — Groww CSV

All imports are **idempotent** — re-importing the same file creates 0 new records.

## Price Feeds

Prices refresh automatically when the backend starts. Manual refresh:

```bash
# Refresh all assets
curl -X POST http://localhost:8000/prices/refresh-all

# Refresh a single asset
curl -X POST http://localhost:8000/assets/{id}/price/refresh
```

NPS NAV is fetched from [npsnav.in](https://npsnav.in/nps-api) — scheme codes are auto-discovered by matching asset names.

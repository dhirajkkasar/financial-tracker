# Financial Portfolio Tracker

A personal, local-first investment portfolio tracker for Indian investors. Tracks equities, mutual funds, fixed deposits, PPF/EPF/NPS, US stocks, gold, real estate, and RSUs — with accurate XIRR/CAGR, FIFO tax lot tracking, goal funding, and automated price feeds.

## Features

- **Portfolio overview** — invested, current value, current P&L, all-time P&L, XIRR across all asset types
- **Asset types** — Indian stocks, US stocks, mutual funds, FD/RD, PPF, EPF, NPS, gold, SGBs, real estate, RSUs
- **Price feeds** — MF NAV (mfapi.in), NPS NAV (npsnav.in), stocks/gold (yfinance), refreshed on-demand via CLI
- **FIFO lot engine** — per-lot unrealized/realized gains, short-term vs long-term classification
- **Tax module** — FY2024-25 realized/unrealized gains by asset class, LTCG exemption, harvest opportunities
- **Goals** — allocate assets to financial goals, SIP calculator, progress tracking
- **Imports** — idempotent CSV/PDF imports: Zerodha tradebook, PPF, EPF, NPS CSV, CAS PDF (CAMS/KFintech), Fidelity RSU & sale
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

### Backend Setup

1. **Clone and navigate to backend:**
   ```bash
   cd backend
   ```

2. **Create and activate virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   # Using uv (recommended)
   uv sync --all-extras
   
   # Or using pip
   pip install -e .[dev]
   ```

4. **Set up environment variables:**
   Create a `.env` file in the `backend/` directory:
   ```bash
   cp .env.example .env  # If example exists, otherwise create manually
   ```
   
   Required variables:
   ```env
   DATABASE_URL=sqlite:///./financial_tracker.db
   API_TOKEN=your_secure_token_here
   GOOGLE_CLIENT_ID=your_google_client_id
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   GOOGLE_DRIVE_BACKUP_FOLDER=financial-tracker-backup
   ```

5. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Seed the database with demo data:**
   ```bash
   python scripts/seed_all.py
   ```
   
   This runs 14 seeding scripts in order:
   - Interest rates
   - Demo assets (deposits, PPF, EPF, NPS, gold)
   - Historical SIPs & stock BUY lots
   - Closed positions (inactive stocks, MFs, matured FDs)
   - Market assets (MF and Indian stock assets)
   - Personal info data
   - NPS schemes
   - Rich EPF data
   - Comprehensive FD/RD assets
   - US stocks RSU data
   - CAS snapshots for MF assets
   - Portfolio snapshots
   - Price cache for market assets
   - Manual valuations

7. **Start the backend server:**
   ```bash
   uvicorn app.main:app --reload
   ```
   
   The API runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend Setup

1. **Navigate to frontend:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure API URL (optional):**
   ```bash
   echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
   ```

4. **Start the development server:**
   ```bash
   npm run dev
   ```
   
   The frontend runs at `http://localhost:3000`.

## CLI Commands

The backend includes a comprehensive CLI tool for data management. All commands require the server to be running.

### Import Commands
```bash
# Import various data sources
python cli.py import ppf <ppf_csv_file>           # SBI PPF account statement CSV
python cli.py import epf <epf_pdf_file>           # EPFO member passbook PDF
python cli.py import cas <cas_pdf_file>           # CAMS/KFintech CAS PDF
python cli.py import nps <nps_csv_file>           # NPS transaction CSV
python cli.py import zerodha <tradebook_csv>     # Zerodha tradebook CSV
python cli.py import fidelity-rsu <rsu_csv>      # Fidelity RSU holding CSV
python cli.py import fidelity-sale <sale_pdf>    # Fidelity tax-cover sale PDF
```

### Add Assets Manually
```bash
# Add various asset types
python cli.py add fd --name "HDFC FD" --bank HDFC --principal 500000 --rate 7.1 --start 2024-01-15 --maturity 2025-01-15 --compounding QUARTERLY
python cli.py add rd --name "SBI RD" --bank SBI --installment 10000 --rate 6.5 --start 2024-01-01 --maturity 2026-01-01 --compounding QUARTERLY
python cli.py add real-estate --name "Venezia Flat" --purchase-amount 7500000 --purchase-date 2020-11-09 --current-value 12000000 --value-date 2024-01-01
python cli.py add gold --name "Digital Gold" --date 2023-06-01 --units 10 --price 5800
python cli.py add sgb --name "SGB 2023-24 S3" --date 2023-12-01 --units 50 --price 6200
python cli.py add rsu --name "AMZN RSU" --date 2024-03-01 --units 10 --price 180.50 --forex 83.5 --notes "Perquisite tax: ..."
python cli.py add us-stock --name "Apple" --identifier AAPL --date 2023-01-15 --units 5 --price 142.50 --forex 82.0
```

### Add Transactions and Valuations
```bash
# Add manual transactions
python cli.py add txn --asset "AMZN RSU" --type VEST --date 2024-09-01 --amount -90000 --units 5 --price 215 --forex 84

# Add EPF monthly contributions (after initial PDF import)
python cli.py add epf-contribution --asset "My EPF" --month-year 03/2026 --employee-share 5000
python cli.py add epf-contribution --asset "My EPF" --month-year 03/2026 --employee-share 5000 --eps-share 1250 --employer-share 3750 --employee-interest 500 --employer-interest 400 --eps-interest 50

# Add manual valuations for PPF/Real Estate
python cli.py add valuation --asset "Venezia Flat" --value 13000000 --date 2025-01-01
```

### Goal Management
```bash
# Create and manage financial goals
python cli.py add goal --name "Retirement" --target 10000000 --date 2040-01-01 --asset "HDFC MF:50" --asset "PPF SBI:50" --assumed-return 12.0
python cli.py add goal --name "Emergency Fund" --target 500000 --date 2026-12-31

# Update goal allocations
python cli.py update goal-allocation --goal "Retirement" --asset "HDFC MF" --pct 30
python cli.py remove goal-allocation --goal "Retirement" --asset "HDFC MF"
python cli.py delete goal --name "Retirement"
```

### Data Management
```bash
# List all assets
python cli.py list assets

# Refresh prices for all market assets
python cli.py refresh-prices

# Create portfolio snapshot
python cli.py snapshot

# Backup database to Google Drive
python cli.py backup
python cli.py backup --folder my-custom-folder
```

### Environment Override
Set the `PORTFOLIO_API` environment variable to override the default API URL:
```bash
export PORTFOLIO_API=http://localhost:8000
```

## Using the App

### Getting Started
1. **Start both servers** (backend and frontend) as described in Setup
2. **Open the frontend** at `http://localhost:3000`
3. **Navigate through the tabs** to view your portfolio:
   - **Overview**: Net worth, asset allocation, recent performance
   - **Stocks**: Indian and US stock holdings
   - **Mutual Funds**: MF portfolio with SIP tracking
   - **Deposits**: FDs, RDs with maturity calculations
   - **PPF/EPF/NPS**: Retirement accounts
   - **US Stocks**: US market investments and RSUs
   - **Gold**: Physical and digital gold holdings
   - **Real Estate**: Property valuations
   - **Goals**: Financial goal tracking and progress
   - **Tax**: Tax calculations and harvest opportunities
   - **Personal Info**: Bank accounts, insurance, documents

### Adding Your Data
1. **Import existing data** using CLI commands (see CLI Commands section below)
2. **Refresh prices** as needed using CLI: `python cli.py refresh-prices`
3. **Create financial goals** and allocate assets to them
4. **Track valuations** for PPF, EPF, and real estate manually

### Key Features
- **Real-time P&L**: Current and all-time returns with XIRR calculations
- **FIFO Tax Lots**: Accurate short-term vs long-term capital gains
- **Goal Funding**: Allocate assets to specific financial goals
- **Tax Planning**: View realized/unrealized gains and harvest opportunities
- **Portfolio Snapshots**: Track performance over time
- **Automated Backups**: Database backups to Google Drive

### Maintenance Tasks
- **Refresh prices regularly**: `python cli.py refresh-prices`
- **Create snapshots**: `python cli.py snapshot` for historical tracking
- **Backup data**: `python cli.py backup` to Google Drive
- **Update valuations**: For PPF/EPF/real estate as needed

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
uv run pytest --cov=app --cov-report=term-missing
```

Coverage targets: overall ≥ 80%, engine functions ≥ 90%, importers ≥ 85%.

To run specific tests:
```bash
# Run a specific test file
uv run pytest tests/unit/test_fd_engine.py -v

# Run a single test by name
uv run pytest tests/unit/test_fd_engine.py::test_function_name -v

# Run only unit or integration tests
uv run pytest tests/unit/
uv run pytest tests/integration/
```

## Unified Import Pipeline

All file imports use a consistent **Preview → Commit** workflow:

1. **Preview** — Parse file, deduplicate, show preview
2. **Commit** — Persist transactions, trigger post-processors, create valuations

### Supported Import Formats

| Source | Format | Asset Type(s) | Method |
|---|---|---|---|
| Zerodha | Tradebook CSV | STOCK_IN | `POST /import/preview-file` |
| CAMS/KFintech | CAS PDF | MF | `POST /import/preview-file` |
| NSDL | NPS CSV | NPS | `POST /import/preview-file` |
| SBI/Banks | PPF CSV | PPF | `POST /import/preview-file` |
| EPFO | EPF PDF | EPF | `POST /import/preview-file` |
| Fidelity | RSU CSV | STOCK_US | `POST /import/preview-file` + exchange_rates |
| Fidelity | Sale PDF | STOCK_US | `POST /import/preview-file` + exchange_rates |
| Groww | CSV | MF | `POST /import/preview-file` |

### Fidelity Imports (Exchange Rates)

Fidelity importers require USD/INR exchange rates for the transaction months:

```bash
# CLI
python cli.py import fidelity-rsu NASDAQ_AMZN.csv --exchange-rates '{"2025-03": 86.5, "2025-04": 85.2}'

# API
POST /import/preview-file
  source=fidelity_rsu
  format=csv
  file=<file>
  user_inputs={"2025-03": 86.5, "2025-04": 85.2}
```

All imports are **idempotent** — re-importing the same file creates 0 new records.

### PPF/EPF Imports

PPF and EPF now use the same orchestrator pipeline as other assets:
- **PPF CSV** — auto-creates closing valuation from CSV balance
- **EPF PDF** — parses monthly contributions, interests, and transfers
- Asset auto-created if not found; EPF asset always marked `is_active=True`

## Price Feeds

Manual price refresh via CLI:

```bash
# Refresh all assets
python cli.py refresh-prices
```

On startup, the backend:
1. Seeds interest rates (idempotent)
2. Auto-matures past-due FDs/RDs
3. Attempts background price refresh (non-blocking)

**Supported price sources:**
- MF NAV: [mfapi.in](https://mfapi.in) — 1 day staleness
- NPS NAV: [npsnav.in](https://npsnav.in/api) — 1 day staleness, auto-discovered by name matching
- Stocks/Gold: [yfinance](https://finance.yahoo.com/) — 6 hours staleness
- US stocks + forex: yfinance — 6 hours staleness

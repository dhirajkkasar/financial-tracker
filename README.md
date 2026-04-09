# Financial Portfolio Tracker

A personal, local-first investment portfolio tracker for Indian investors. Tracks equities, mutual funds, fixed deposits, PPF/EPF/NPS, US stocks, gold, real estate, and RSUs — with accurate XIRR/CAGR, FIFO tax lot tracking, goal funding, and automated price feeds.

## Features

- **Portfolio overview** — invested, current value, current P&L, all-time P&L, XIRR across all asset types
- **Asset types** — Indian stocks, US stocks, mutual funds, FD/RD, PPF, EPF, NPS, gold, SGBs, real estate, RSUs
- **Live price feeds** — MF NAV (mfapi.in), NPS NAV (npsnav.in), stocks/gold (yfinance), refreshed on-demand
- **FIFO lot engine** — per-lot unrealized/realized gains, short-term vs long-term classification
- **Tax module** — FY-aware realized/unrealized gains by asset class, LTCG exemption, harvest opportunities
- **Goals** — allocate assets to financial goals, SIP calculator, progress tracking
- **Idempotent imports** — CSV/PDF imports: Zerodha, PPF, EPF, NPS, CAS (CAMS/KFintech), Fidelity RSU & sale
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

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) — `pip install uv`
- Node.js 20+

### 1. Backend

```bash
cd backend

# Install dependencies
uv sync --all-extras

# Configure environment
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL (SQLite default works out of the box)

# Run database migrations
uv run alembic upgrade head

# (Optional) Seed with demo data
uv run python scripts/seed_all.py

# Start the API server
uvicorn app.main:app --reload
# API at http://localhost:8000 — interactive docs at http://localhost:8000/docs
```

### 2. Frontend

```bash
cd frontend

npm install

# Set API URL (defaults to localhost:8000 if omitted)
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm run dev
# UI at http://localhost:3000
```

### Environment Variables

**Backend** (`backend/.env`):
```env
DATABASE_URL=sqlite:///./portfolio.db          # SQLite (default)
# DATABASE_URL=postgresql://user:pass@host/db  # PostgreSQL (cloud)
API_TOKEN=changeme                             # Simple token auth
GOOGLE_CLIENT_ID=...                           # For Google Drive backup (optional)
GOOGLE_CLIENT_SECRET=...
GOOGLE_DRIVE_BACKUP_FOLDER=financial-tracker-backup
```

**Frontend** (`frontend/.env.local`):
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Downloading Statements

### Mutual Funds (CAS PDF)
1. Go to [CAMS Consolidated Account Statement](https://www.camsonline.com/Investors/Statements/Consolidated-Account-Statement)
2. Select statement type: **Detailed**
3. Set folio listing to: **With zero balance folios**
4. Download the PDF — **remove the password from the PDF** before importing (the importer does not support password-protected files)

### Indian Stocks (Zerodha)
1. Log in to Zerodha and download the **year-wise tradebook** CSV for each financial year
2. Import files **sequentially from oldest to newest year** — order matters for correct FIFO lot computation

### NPS
1. Log in to [Protean CRA](https://cra.nps-proteantech.in/CRA/)
2. Download **transaction statements** for both Tier 1 and Tier 2 accounts, for each year
3. Import files **sequentially from oldest to newest year**

### EPF
1. Log in to [EPFO Member Passbook](https://passbook.epfindia.gov.in/MemberPassBook/login)
2. Download **year-wise PDF statements**

### PPF
1. Download the account statement in **CSV format** (currently supports SBI PPF statements)

### US Stocks / RSUs (Fidelity)
1. Download your **holding statement in CSV format**
2. Rename the file to `<MARKET>_<TICKER>.csv` — e.g. `NASDAQ_AMZN.csv`
3. Ensure the currency column in the CSV is **USD**

### Fixed Deposits (Manual via CLI)
FDs are added manually using the CLI — no statement download required:

```bash
python cli.py add fd \
  --name "HDFC FD" \
  --bank HDFC \
  --principal 500000 \
  --rate 7.1 \
  --start 2024-01-15 \
  --maturity 2025-01-15 \
  --compounding QUARTERLY
```

---

## CLI Commands

All commands require the backend server to be running. Set `PORTFOLIO_API` to override the default URL.

```bash
export PORTFOLIO_API=http://localhost:8000  # optional override
```

### Member Management

Each household member is identified by PAN. A member must exist before any data can be imported for them.

```bash
# Add a member (required once per PAN before importing)
python cli.py add-member --pan ABCDE1234F --name "Dhiraj"
python cli.py add-member --pan XYZAB5678G --name "Spouse"
```

### Import Data

All import commands require `--pan` to identify which household member the data belongs to.

```bash
python cli.py import ppf <ppf_csv_file> --pan ABCDE1234F        # SBI PPF account statement CSV
python cli.py import epf <epf_pdf_file> --pan ABCDE1234F        # EPFO member passbook PDF
python cli.py import cas <cas_pdf_file> --pan ABCDE1234F        # CAMS/KFintech CAS PDF (mutual funds)
python cli.py import nps <nps_csv_file> --pan ABCDE1234F        # NPS transaction CSV
python cli.py import zerodha <tradebook_csv> --pan ABCDE1234F   # Zerodha tradebook CSV
python cli.py import fidelity-rsu <rsu_csv> --pan ABCDE1234F    # Fidelity RSU holding CSV (prompts for USD/INR rates)
python cli.py import fidelity-sale <sale_pdf> --pan ABCDE1234F  # Fidelity tax-cover sale PDF (prompts for USD/INR rates)
```

All imports are idempotent — re-importing the same file creates 0 new records.

### Add Assets Manually

```bash
python cli.py add fd        --name "HDFC FD" --bank HDFC --principal 500000 --rate 7.1 --start 2024-01-15 --maturity 2025-01-15 --compounding QUARTERLY
python cli.py add rd        --name "SBI RD" --bank SBI --installment 10000 --rate 6.5 --start 2024-01-01 --maturity 2026-01-01 --compounding QUARTERLY
python cli.py add real-estate --name "Venezia Flat" --purchase-amount 7500000 --purchase-date 2020-11-09 --current-value 12000000 --value-date 2024-01-01
python cli.py add gold      --name "Digital Gold" --date 2023-06-01 --units 10 --price 5800
python cli.py add sgb       --name "SGB 2023-24 S3" --date 2023-12-01 --units 50 --price 6200
python cli.py add rsu       --name "AMZN RSU" --date 2024-03-01 --units 10 --price 180.50 --forex 83.5 --notes "Perquisite tax: ..."
python cli.py add us-stock  --name "Apple" --identifier AAPL --date 2023-01-15 --units 5 --price 142.50 --forex 82.0
```

### Add Transactions and Valuations

```bash
# Manual transaction
python cli.py add txn --asset "AMZN RSU" --type VEST --date 2024-09-01 --amount -90000 --units 5 --price 215 --forex 84

# EPF monthly contributions (after initial PDF import)
python cli.py add epf-contribution --asset "My EPF" --month-year 03/2026 --employee-share 5000
python cli.py add epf-contribution --asset "My EPF" --month-year 03/2026 --employee-share 5000 --eps-share 1250 --employer-share 3750 --employee-interest 500 --employer-interest 400 --eps-interest 50

# Manual valuations for PPF / Real Estate
python cli.py add valuation --asset "Venezia Flat" --value 13000000 --date 2025-01-01
```

### Goal Management

```bash
python cli.py add goal --name "Retirement" --target 10000000 --date 2040-01-01 --asset "HDFC MF:50" --asset "PPF SBI:50"
python cli.py add goal --name "Emergency Fund" --target 500000 --date 2026-12-31

python cli.py update goal-allocation --goal "Retirement" --asset "HDFC MF" --pct 30
python cli.py remove goal-allocation --goal "Retirement" --asset "HDFC MF"
python cli.py delete goal --name "Retirement"
```

### Data Management

```bash
python cli.py list assets      # List all assets
python cli.py refresh-prices   # Refresh prices for all market assets
python cli.py snapshot         # Create a portfolio snapshot
python cli.py backup           # Backup database to Google Drive
python cli.py backup --folder my-custom-folder
```

---

## Price Feeds

Prices are fetched on-demand via `python cli.py refresh-prices` and also attempted in the background on server startup.

| Asset class | Source | Staleness threshold |
|---|---|---|
| Mutual funds (NAV) | [mfapi.in](https://mfapi.in) | 1 day |
| NPS (NAV) | [npsnav.in](https://npsnav.in/api) — scheme auto-discovered by name | 1 day |
| Indian stocks | [yfinance](https://finance.yahoo.com/) (NSE/BSE) | 6 hours |
| US stocks + forex | yfinance | 6 hours |
| Gold | yfinance | 6 hours |

Each fetcher self-registers via `@register_fetcher`. Adding a new price source requires only a new class — no changes to existing files.

---

## Using the App

Open `http://localhost:3000` after starting both servers. Navigate the tabs:

| Tab | What it shows |
|---|---|
| Overview | Net worth, asset allocation, recent performance |
| Stocks | Indian stock holdings and lots |
| Mutual Funds | MF portfolio with SIP tracking |
| Deposits | FDs and RDs with maturity calculations |
| PPF / EPF / NPS | Retirement accounts |
| US Stocks | US market investments and RSUs |
| Gold | Physical and digital gold |
| Real Estate | Property valuations |
| Goals | Financial goal tracking and progress |
| Tax | Realized/unrealized gains, harvest opportunities |
| Personal Info | Bank accounts, insurance, identity docs |

---

## Testing

```bash
cd backend

# Run all tests
uv run pytest

# With coverage report
uv run pytest --cov=app --cov-report=term-missing

# Run a specific file or test
uv run pytest tests/unit/test_fd_engine.py -v
uv run pytest tests/unit/test_fd_engine.py::test_function_name -v

# Unit or integration only
uv run pytest tests/unit/
uv run pytest tests/integration/
```

Coverage targets: overall ≥ 80%, engine functions ≥ 90%, importers ≥ 85%.

---

## Contributing

This is a personal project but contributions are welcome.

- **Architecture:** See `CLAUDE.md` for architecture decisions, coding standards, and DI patterns.
- **TDD:** All new code requires a failing test first. Red → Green → Refactor.
- **No business logic in API routes** — routes parse requests and return responses; all logic lives in services.
- **No `db.commit()` in repositories** — the UnitOfWork context manager owns all commits.
- **New asset type:** Add a 3-line leaf class in `backend/app/services/returns/strategies/asset_types/` with `@register_strategy`.
- **New price source:** Add a `@register_fetcher` class in `backend/app/services/price_feed.py` — no other file changes needed.

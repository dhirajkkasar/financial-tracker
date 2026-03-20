# Investment Tracker — Requirements Document

**Version:** 0.3  
**Last updated:** March 2026  
**Owner:** Single user, personal use

---

## 1. Project overview

A personal investment portfolio tracker that runs locally (no Docker initially). Tracks all asset types, computes returns (XIRR/CAGR) at individual asset and portfolio level, handles tax harvesting continuity correctly, tracks goals with linked investments, and stores important personal/financial reference data.

**Local run:**
```
cd backend && uvicorn main:app --reload
cd frontend && npm run dev
```

Data stored in `portfolio.db` (SQLite, auto-created on first run, lives in project root).

---

## 2. Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+ + FastAPI |
| ORM | SQLAlchemy + Alembic (migrations) |
| Database | SQLite (local) → PostgreSQL (cloud, future) |
| Return engine | numpy-financial (XIRR), pandas |
| PDF parsing | pdfplumber (CAMS CAS) |
| CSV parsing | pandas |
| Frontend | React + Vite |
| HTTP client | axios |
| Charts | Recharts |
| Price feeds | mfapi.in (MF NAV), yfinance (stocks, US stocks, gold) |

---

## 3. Data model

### 3.1 Asset

```
Asset
  id                    integer PK
  name                  e.g. "Axis Bluechip Fund — Direct Growth"
  identifier            ticker / ISIN / folio / account number
  asset_type            enum (see section 4)
  asset_class           enum: EQUITY | DEBT | GOLD | REAL_ESTATE | MIXED
  currency              INR | USD
  is_active             bool (false = exited / matured)
  notes                 text
```

### 3.2 Transaction

```
Transaction
  id                    integer PK
  asset_id              FK → Asset
  type                  enum: BUY | SELL | DIVIDEND | INTEREST | SIP |
                              REDEMPTION | BONUS | SPLIT | CONTRIBUTION |
                              WITHDRAWAL | SWITCH_IN | SWITCH_OUT
  date                  date
  units                 decimal (nullable for FD/PPF/EPF)
  price_per_unit        decimal (nullable for FD/PPF/EPF)
  forex_rate            decimal (only for US stocks — USD/INR at transaction date)
  amount                decimal (INR — always)
  charges               decimal (brokerage, STT, stamp duty)
  lot_id                UUID (auto-generated on BUY/SIP/CONTRIBUTION — for FIFO)
  notes                 text
```

### 3.3 Valuation

Manual price snapshots for illiquid / non-market-priced assets.

```
Valuation
  id                    integer PK
  asset_id              FK → Asset
  date                  date
  value_inr             decimal
  notes                 text
```

Used for: Real estate, Gold (if manual), PPF balance snapshots, EPF passbook balance.

### 3.4 PriceCache

```
PriceCache
  asset_id              FK → Asset
  fetched_at            datetime
  price_inr             decimal
  source                "mfapi.in" | "yfinance" | "manual"
```

### 3.5 InterestRateHistory

Built-in historical rate table for PPF and EPF. Pre-seeded at app startup.

```
InterestRateHistory
  id                    integer PK
  instrument            enum: PPF | EPF
  effective_from        date
  effective_to          date (null = current)
  rate_pct              decimal (e.g. 7.1)
  source                text (e.g. "Ministry of Finance notification")
```

Pre-seeded data covers PPF and EPF rates from 2000 onwards. App looks up the applicable rate for any given financial year automatically.

### 3.6 FDDetail

Stores the terms of each FD/RD — used to compute maturity value and XIRR without needing daily price feeds.

```
FDDetail
  id                    integer PK
  asset_id              FK → Asset (one-to-one)
  bank                  text
  fd_type               enum: FD | RD
  principal_amount      decimal
  interest_rate_pct     decimal (annual)
  compounding           enum: MONTHLY | QUARTERLY | HALF_YEARLY | YEARLY | SIMPLE
  start_date            date
  maturity_date         date
  maturity_amount       decimal (actual if matured, computed if active)
  is_matured            bool
  premature_withdrawal  bool (if broken before maturity)
  tds_applicable        bool
  notes                 text (bank branch, FD number etc.)
```

For **old/matured FDs**: `is_matured = true`, `maturity_amount` = actual amount received. XIRR computed from: `-principal on start_date` → `+maturity_amount on maturity_date`. Interest credited annually also optionally recorded as INTEREST transactions for accuracy.

For **active FDs**: `maturity_amount` computed from formula. Used as the "current value" for return calculations.

**RD:** Monthly contribution recorded as recurring CONTRIBUTION transactions. Maturity amount computed from RD formula.

### 3.7 Goal

```
Goal
  id                    integer PK
  name                  e.g. "Retirement", "House down payment"
  target_amount_inr     decimal
  target_date           date
  assumed_return_pct    decimal (default 12.0 — used for SIP calculator)
  notes                 text
```

### 3.8 GoalAllocation

```
GoalAllocation
  id                    integer PK
  goal_id               FK → Goal
  asset_id              FK → Asset
  allocation_pct        decimal 0–100
```

One asset can link to multiple goals. Allocation % across goals can sum to more than 100 (goals overlap intentionally).

### 3.9 ImportantData

```
ImportantData
  id                    integer PK
  category              enum: BANK | MF_FOLIO | IDENTITY | INSURANCE |
                              ACCOUNT | OTHER
  label                 text (e.g. "HDFC Savings", "Zerodha login")
  fields                JSON (flexible key-value per category)
  notes                 text
```

---

## 4. Asset types and return calculation

### 4.1 Stocks — NSE/BSE (STOCK_IN)

- **Price:** Auto-fetch via yfinance (`NSE:INFY`, `BSE:500209`)
- **Return:** XIRR across all BUY/SELL/DIVIDEND transactions + current market value
- **Tax:** FIFO lot matching, STCG < 1 year at 20%, LTCG ≥ 1 year at 12.5% (₹1.25L exemption)
- **Special:** Pre-Jan 2018 grandfathering — store `jan31_2018_price` per lot, tax cost basis = max(actual, jan31 price)

### 4.2 Mutual Funds (MF)

- **Price:** Auto-fetch NAV via mfapi.in (ISIN or scheme code)
- **Return:** XIRR across all SIP/BUY/REDEMPTION/DIVIDEND transactions + current NAV × units
- **Tax:** Equity MF same as stocks. Debt MF (post Apr 2023) taxed at slab rate regardless of holding period
- **Import:** CAMS / KFintech CAS PDF

### 4.3 FD / RD (FD)

- **Price:** No feed — maturity amount computed from FDDetail formula
- **Return:** XIRR: `-principal` on start date → `+maturity_amount` on maturity date
  - For active FDs: current value = accrued amount as of today (simple daily accrual approximation)
  - For matured FDs: actual maturity amount used — gives true historical XIRR
- **Tax:** Interest taxed at slab rate. TDS deducted at 10% if interest > ₹40,000/year
- **Entry:** Manual via FD entry form

**FD XIRR example:**
```
-₹1,00,000   01 Apr 2021   (principal, outflow)
+₹1,28,647   01 Apr 2024   (maturity at 8.75% p.a. quarterly compounding, inflow)
XIRR → 8.6% (slightly under stated rate due to TDS if applicable)
```

### 4.4 PPF (PPF)

- **Price:** No feed — balance from manual Valuation entries (annual passbook update)
- **Return:** XIRR across all annual/irregular CONTRIBUTION transactions + current balance from latest Valuation
- **Interest rate:** Looked up automatically from InterestRateHistory table by financial year
- **Lock-in:** 15-year lock-in flagged in UI. Partial withdrawal rules shown as info (not enforced)
- **Tax:** EEE — contributions, interest, and maturity all tax-free. Shown separately in tax view
- **Entry:** Manual contributions (irregular amounts, any date within FY)

**PPF interest calculation:**
Interest for each FY = min balance between 5th and last day of each month × applicable rate.
Approximation used: annual balance × rate (sufficiently accurate for return tracking purposes).

### 4.5 EPF (EPF)

- **Price:** No feed — balance from manual Valuation entries (annual passbook snapshot)
- **Return:** XIRR across all monthly CONTRIBUTION transactions + current balance
- **Interest rate:** Looked up from InterestRateHistory table by FY (e.g. 8.25% for FY2023-24)
- **Entry:** Monthly contributions — employee amount + employer amount entered separately as two CONTRIBUTION transactions per month (or combined, user's choice)
- **Tax:** Employee contributions up to ₹1.5L/year under 80C. Interest tax-free up to ₹2.5L/year contribution threshold (above that, interest taxable)

### 4.6 NPS (NPS)

- **Price:** NAV per scheme — manual update or future scrape from NPS Trust
- **Return:** XIRR across all CONTRIBUTION transactions + current NAV × units
- **Import:** NSDL CRA CSV (`enps.nsdl.com` → Transaction Statement download)
- **CSV parser handles:**
  - Multiple scheme rows per contribution (E/C/G/A fund split)
  - Tier I and Tier II as separate Asset entries
  - SWITCH_IN / SWITCH_OUT transactions (unit movement between schemes — not a cash flow, excluded from XIRR)
  - Columns: Transaction Date, Transaction Type, Amount, Units Allotted, NAV, Closing Units, Scheme Name
- **Tax:** Contributions up to ₹1.5L under 80C + additional ₹50K under 80CCD(1B). 60% maturity tax-free, 40% mandatorily annuitised

### 4.7 US Stocks (STOCK_US)

- **Price:** Auto-fetch via yfinance (e.g. `AAPL`) × live USD/INR rate
- **Return:** XIRR in INR only. All amounts stored in INR using forex rate at transaction date
- **forex_rate field** on Transaction stores USD/INR at the time of each transaction
- **Tax:** < 2 years = slab rate, ≥ 2 years = 12.5% LTCG (no exemption)

### 4.8 Gold / SGBs (GOLD / SGB)

- **Price:** yfinance (`GC=F` for gold spot) or manual Valuation entry
- **SGBs:** Store as separate Asset. Price = RBI issue price + accrued interest (2.5% p.a. paid semi-annually)
- **Return:** XIRR across BUY transactions + current value
- **Tax:** Gold < 3 years = slab rate, ≥ 3 years = 12.5%. SGBs held to maturity = tax-free on capital gains

### 4.9 Real Estate (REAL_ESTATE)

- **Price:** Manual Valuation entries (user updates periodically with estimated market value)
- **Return:** XIRR: `-purchase_cost` on purchase date → current valuation. Rental income recorded as INTEREST transactions
- **Tax:** < 2 years = slab rate, ≥ 2 years = 12.5% (Section 54/54F exemption flagged in UI)
- **Entry:** Manual — property name, purchase date, cost (including registration, stamp duty), current valuation

---

## 5. Return calculation engine

### 5.1 XIRR (primary)

`numpy-financial.xirr()` applied to list of (date, amount) cash flows.

Sign convention:
- Outflows (BUY, SIP, CONTRIBUTION) → negative
- Inflows (SELL, REDEMPTION, DIVIDEND, INTEREST, WITHDRAWAL) → positive
- Current value of open holding → positive (as of today)
- SWITCH_IN / SWITCH_OUT → excluded (not cash flows)

**Tax harvesting continuity:** Asset-level XIRR aggregates all transactions. Harvest sell + buyback appears as near-cancelling cash flows. True economic return from original buy date is preserved automatically — no special data structure needed.

### 5.2 Per-lot tax view

Each BUY lot (identified by `lot_id`) evaluated independently via FIFO matching against sells. Buyback after harvest creates a new lot with its own cost basis and holding start date. Both views shown side-by-side on asset detail screen.

### 5.3 CAGR (secondary)

For lumpsum single-buy assets (FD, PPF lumpsum, one-time stock buy):
```
CAGR = (current_value / invested_amount) ^ (1 / years) - 1
```

### 5.4 Absolute return
```
Absolute % = (current_value - total_invested) / total_invested × 100
```

### 5.5 Pre-Jan 2018 grandfathering
```
Tax cost basis = max(actual_purchase_price, price_on_31_jan_2018)
```
`jan31_2018_price` stored as a field on the lot (entered manually or looked up). Tax gain uses grandfathered basis; economic XIRR uses actual cost.

---

## 6. Tax calculation module

### 6.1 Rates (FY2024-25 onwards)

| Asset | STCG threshold | STCG rate | LTCG rate | LTCG exemption |
|---|---|---|---|---|
| Listed equity / equity MF | < 1 year | 20% | 12.5% | ₹1.25L/year |
| Debt MF (post Apr 2023) | All | Slab | Slab | None |
| FD / RD / EPF (above threshold) | — | Slab | — | — |
| PPF | — | Tax-free (EEE) | — | — |
| NPS (60% lumpsum) | — | Tax-free | — | — |
| US stocks | < 2 years | Slab | 12.5% | None |
| Gold | < 3 years | Slab | 12.5% | — |
| SGBs (maturity) | — | Tax-free | — | — |
| Real estate | < 2 years | Slab | 12.5% | 54/54F flag |

Historical rates stored for earlier FYs (pre-Budget 2024: LTCG 10%, exemption ₹1L).

### 6.2 Lot matching

Default: FIFO. Option to view LIFO or specific-lot for planning.

### 6.3 Tax P&L report (per FY Apr–Mar)

- Realised STCG / LTCG by asset class
- Estimated tax liability
- Unrealised gains (mark-to-market)
- Harvesting opportunity scanner — flags lots with unrealised losses that can offset gains

---

## 7. Import mechanisms

### 7.1 CAMS / KFintech CAS PDF

- Upload PDF → pdfplumber extracts transactions
- Fields: folio, scheme, ISIN, date, type, units, NAV, amount
- Deduplication by (date + folio + amount)
- Preview before committing

### 7.2 NSDL NPS CSV

- Upload CSV from enps.nsdl.com Transaction Statement
- Parser handles: multiple schemes per contribution, Tier I/II split, SWITCH transactions
- SWITCH_IN/OUT recorded but excluded from XIRR
- Each scheme mapped to a separate Asset entry (e.g. "NPS — SBI Equity Tier I")

### 7.3 Broker CSV

- Zerodha tradebook CSV
- Groww stock + MF CSV
- Generic fallback with manual column mapping

### 7.4 Manual entry forms

- FD/RD: bank, type, principal, rate, compounding, dates
- PPF: contribution date + amount (irregular)
- EPF: month, employee contribution, employer contribution
- Real estate: property details + purchase cost
- Gold/SGBs: purchase date, units, price
- US stocks: ticker, date, units, price in USD, forex rate (auto-filled from feed)

---

## 8. Live price feeds

| Asset | Source | Refresh |
|---|---|---|
| MF NAV | mfapi.in | Daily post 9 PM |
| NSE/BSE stocks | yfinance | On-demand |
| US stocks | yfinance + USD/INR | On-demand |
| Gold | yfinance (GC=F) | On-demand |
| NPS NAV | Manual (future: NPS Trust scrape) | On update |
| FD / RD | Formula-computed — no feed | — |
| PPF / EPF | Manual Valuation entry | On update |
| Real estate | Manual Valuation entry | On update |

Stale prices shown with staleness indicator. Last cached price used on fetch failure.

---

## 9. Navigation and UI

```
[ Overview ]  [ Goals ]  [ Stocks ]  [ Mutual Funds ]  [ FD / RD ]
[ PPF / EPF / NPS ]  [ US Stocks ]  [ Gold / SGBs ]  [ Real Estate ]  [ Important Data ]
```

### 9.1 Overview tab

- Total portfolio value (INR)
- Overall XIRR + absolute return
- Equity / Debt / Gold / Real Estate allocation donut chart
- Goal progress cards
- Top gainers / losers
- Unrealised LTCG estimate (current FY)

### 9.2 Goals tab

- Card per goal: name, target, current value, progress %, time remaining, SIP needed
- Goal detail: linked investments + SIP calculator (assumed return rate slider)

### 9.3 Stocks / MFs / FD-RD / PPF-EPF-NPS / US Stocks / Gold-SGBs / Real Estate tabs

- Holdings table: Name | Invested | Current value | Gain/Loss | XIRR | Holding period
- Click holding → Asset detail:
  - Transaction timeline
  - Continuous XIRR (all transactions)
  - Per-lot tax view (FIFO)
  - Price/value history chart
  - Goals this asset contributes to

**FD/RD detail additionally shows:**
- Stated interest rate vs actual XIRR (difference shows TDS impact)
- Maturity date countdown for active FDs
- Matured FDs shown in a separate "Closed" section with historical XIRR

**PPF/EPF detail additionally shows:**
- Year-wise contribution + interest credited (from rate history table)
- Cumulative balance chart

**NPS detail additionally shows:**
- Scheme-wise breakdown (E/C/G/A allocation)
- Tier I and Tier II separately

### 9.4 Important Data tab

- Grouped by: Banks, MF Folios, Identity, Insurance, Accounts, Other
- Add / edit / delete entries
- Card layout with key-value fields

---

## 10. Non-functional requirements

| | |
|---|---|
| Local-first | SQLite, no Docker initially. `uvicorn` + `npm run dev` |
| Cloud-portable | SQLAlchemy ORM — one env var switches SQLite → PostgreSQL |
| Single user | No auth needed locally |
| Performance | Dashboard < 2s. Price refresh async |
| Backup | Copy `portfolio.db`. Full JSON/CSV export |

---

## 11. Out of scope (v1)

- Docker / cloud deployment (Phase 6, later)
- Multi-user / family portfolios
- Real-time intraday prices
- Automated tax filing integration
- Mobile app

---

## 12. Phased build plan

### Phase 1 — Core engine
- DB schema + Alembic migrations (all tables including FDDetail, InterestRateHistory)
- Pre-seed InterestRateHistory (PPF + EPF rates from 2000)
- FastAPI CRUD endpoints
- XIRR / CAGR / absolute return engine
- Manual entry forms (all asset types)
- React shell + tab navigation

### Phase 2 — Imports + price feeds
- CAMS / KFintech CAS PDF parser
- NSDL NPS CSV parser
- Zerodha / Groww CSV importer
- mfapi.in + yfinance price feed integration
- PriceCache with staleness handling

### Phase 3 — Returns and allocation
- Asset detail: continuous XIRR + per-lot tax view
- FD detail: stated rate vs actual XIRR
- PPF/EPF: year-wise breakdown with rate history
- Allocation view (equity/debt/gold/RE)
- Pre-2018 grandfathering

### Phase 4 — Goals
- Goal CRUD + GoalAllocation
- Goal progress on Overview
- SIP calculator with adjustable return rate

### Phase 5 — Tax module
- STCG / LTCG with FIFO lot matching
- FY-wise tax P&L report
- Harvesting opportunity scanner

### Phase 6 — Cloud deployment
- Dockerfile + docker-compose
- PostgreSQL migration
- Bearer token auth
- Backup / export tooling

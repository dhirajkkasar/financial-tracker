# Personal Finance Tracker – Data Model

## 1. Design Principles

* Event-driven model based on **cashflows (transactions)**
* **Idempotent ingestion** using deterministic transaction IDs
* Separation of:

  * static data (transactions, instruments)
  * computed data (holdings, XIRR, valuation)
* Schema designed to be **SQLite-compatible** and portable to PostgreSQL

---

## 2. Core Entities Overview

### Hierarchy

```text
Asset Class → Investment → Transactions → Holdings (derived)
```

---

## 3. Tables

---

## 3.1 asset_classes

Defines high-level allocation categories.

```sql
CREATE TABLE asset_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
```

### Examples:

* Equity
* Debt
* Gold
* Real Estate
* Retirement

---

## 3.2 instruments

Represents a financial instrument (MF scheme, stock, FD, etc.)

```sql
CREATE TABLE instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,              -- MF, STOCK, FD, NPS, etc.
    isin TEXT,
    symbol TEXT,
    asset_class_id INTEGER,
    UNIQUE(isin),
    FOREIGN KEY (asset_class_id) REFERENCES asset_classes(id)
);
```

---

## 3.3 investments

Represents a holding/account for an instrument.

```sql
CREATE TABLE investments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    instrument_id INTEGER NOT NULL,
    platform TEXT,                  -- Zerodha, Groww, Bank, etc.
    notes TEXT,
    FOREIGN KEY (instrument_id) REFERENCES instruments(id)
);
```

### Example:

* “Axis Bluechip Fund (Groww)”
* “Infosys (Zerodha)”
* “SBI FD 2023”

---

## 3.4 transactions (🔥 most important)

Stores all cashflows.

```sql
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_id TEXT NOT NULL UNIQUE,    -- idempotency key

    investment_id INTEGER NOT NULL,
    date TEXT NOT NULL,             -- ISO format YYYY-MM-DD

    amount INTEGER NOT NULL,        -- in paise (negative = निवेश, positive = withdrawal)
    units REAL,                     -- optional (for MF, stocks)

    type TEXT NOT NULL,             -- BUY, SELL, DIVIDEND, INTEREST, etc.

    source TEXT,                    -- CAS, CSV, MANUAL
    source_ref TEXT,                -- file reference / hash

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (investment_id) REFERENCES investments(id)
);
```

---

## 3.5 holdings (optional but recommended)

Stores aggregated units per investment.

```sql
CREATE TABLE holdings (
    investment_id INTEGER PRIMARY KEY,
    total_units REAL NOT NULL,
    last_updated TEXT,
    FOREIGN KEY (investment_id) REFERENCES investments(id)
);
```

👉 Can also be computed dynamically, but storing improves performance.

---

## 3.6 prices_cache

Caches latest market prices.

```sql
CREATE TABLE prices_cache (
    instrument_id INTEGER PRIMARY KEY,
    price REAL NOT NULL,
    last_updated TEXT NOT NULL,
    source TEXT,
    FOREIGN KEY (instrument_id) REFERENCES instruments(id)
);
```

---

## 3.7 metadata_vault

Stores important personal information.

```sql
CREATE TABLE metadata_vault (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,         -- BANK, INSURANCE, LOGIN, etc.
    name TEXT,
    value TEXT,
    notes TEXT
);
```

⚠️ Sensitive data should be encrypted if needed.

---

## 4. Idempotency Strategy

Each transaction must have a **deterministic txn_id**.

### Suggested format:

```text
hash(instrument_id + date + amount + units + type)
```

---

## 5. Derived Data (Not Stored Permanently)

These are computed at runtime:

* Current value = units × latest price
* Portfolio value
* XIRR (all levels)
* Asset allocation
* Gains/losses

---

## 6. Indexing Strategy

```sql
CREATE INDEX idx_transactions_investment ON transactions(investment_id);
CREATE INDEX idx_transactions_date ON transactions(date);
CREATE INDEX idx_instruments_asset_class ON instruments(asset_class_id);
```

---

## 7. Data Flow

### Ingestion

```text
CAS / CSV / CLI
    ↓
Normalize data
    ↓
Generate txn_id
    ↓
INSERT ... ON CONFLICT(txn_id) DO UPDATE
```

---

### Dashboard

```text
Fetch investments
    ↓
Aggregate holdings
    ↓
Fetch latest prices
    ↓
Compute valuation + XIRR
```

---

## 8. Notes on Special Asset Types

### Fixed Deposits

* Single investment
* Transactions:

  * initial deposit (negative)
  * maturity (optional or computed)

---

### EPF / PPF

* Yearly contributions as transactions
* Interest handled in valuation logic

---

### NPS

* Units-based like mutual funds

---

### Gold / Real Estate

* Units optional
* Value updated manually or via price service

---

### RSUs

* Vesting treated as:

  * zero-cost or discounted BUY transaction

---

## 9. Future Extensions

* portfolio_snapshots (for historical tracking)
* tax_events table
* multi-currency support
* goal tracking

---

## 10. Key Guarantees

* No duplicate transactions (via txn_id)
* All returns derived from cashflows
* Real-time valuation using latest prices
* DB remains source of truth for all raw data
# Addendum: Goal Data Model

---

## 1. goals

```sql
CREATE TABLE goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target_amount INTEGER NOT NULL,   -- in paise
    target_date TEXT NOT NULL,        -- YYYY-MM-DD
    notes TEXT
);
```

---

## 2. investment_goals (mapping table)

Many-to-many relationship with allocation.

```sql
CREATE TABLE investment_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investment_id INTEGER NOT NULL,
    goal_id INTEGER NOT NULL,
    allocation_percent REAL NOT NULL,  -- e.g., 40.0 = 40%

    UNIQUE(investment_id, goal_id),

    FOREIGN KEY (investment_id) REFERENCES investments(id),
    FOREIGN KEY (goal_id) REFERENCES goals(id)
);
```

---

## 3. Derived Goal Computations (Not Stored)

For each goal:

### Current Value

```text
Σ (investment_value × allocation_percent)
```

---

### Invested Amount

```text
Σ (investment_invested × allocation_percent)
```

---

### Goal Completion %

```text
(current_value / target_amount) × 100
```

---

### Remaining Amount

```text
target_amount - current_value
```

---

### Required Monthly Investment (SIP)

Derived using future value formula:

```text
PMT = required monthly investment
```

Inputs:

* remaining amount
* months left
* expected return rate

---

## 4. Notes

* Allocation percent per investment can sum to:

  * ≤ 100% (recommended)
* Remaining % can be treated as “unassigned”
* No duplication of transactions needed—allocation is virtual


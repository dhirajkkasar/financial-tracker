# Personal Finance Tracker – Technical Decisions

## 1. System Architecture

* Architecture style: **Single backend monolith**
* Backend exposes **REST APIs**
* System is **CLI-first for data ingestion** with a **read-only web dashboard**
* Single-user, local-first application

---

## 2. Backend

* Language: **Python**
* Framework: **FastAPI**
* Responsibilities:

  * Data ingestion (CAS, CSV, CLI)
  * Portfolio data normalization
  * XIRR calculations
  * Real-time valuation engine
  * REST API for UI

---

## 3. Frontend

* Framework: **Next.js**
* Role: **Read-only dashboard**
* Responsibilities:

  * Portfolio summary visualization
  * Asset allocation charts
  * Investment drilldowns
  * Display XIRR and portfolio metrics

Frontend communicates with backend using **REST APIs**.

---

## 4. Database

* Primary database: **SQLite**
* Usage context:

  * Local-only deployment
  * Single-user system
* Design considerations:

  * Enable WAL mode for better concurrency
  * Store monetary values as **integer (paise)** to avoid precision issues
  * Store dates in **ISO format (YYYY-MM-DD)**

Future migration path:

* Schema and ORM designed to allow **SQLite → PostgreSQL migration**.

---

## 5. ORM Layer

* ORM: **SQLAlchemy (v2 style)**
* Purpose:

  * Database abstraction
  * Easier migration between databases
  * Schema definition and query building
* Migrations: **Alembic**

---

## 6. Data Ingestion

Data can be loaded via:

### Supported Methods

* CAS PDF import (Mutual Funds)
* CSV import (Stocks, NPS)
* CLI commands
* REST API endpoints (optional)

### Idempotency Requirement

All ingestion operations must be **idempotent**:

* Each transaction will have a **deterministic transaction ID**
* Database enforces **unique constraint**
* Duplicate imports update or replace existing records instead of creating duplicates.

---

## 7. Data Model Approach

System follows an **event-driven model** based on financial cashflows.

Core entities:

* Assets
* Investments
* Transactions (cashflows)
* Holdings (derived from transactions)
* Metadata (account information)

Transactions represent all inflows/outflows used to compute portfolio metrics.

---

## 8. Portfolio Analytics

The backend computes:

* XIRR per investment
* XIRR per asset class
* Overall portfolio XIRR
* Total invested amount
* Current portfolio value
* Asset allocation (equity vs debt etc.)

All calculations are performed **in the backend**.

---

## 9. Real-Time Valuation

Market prices are fetched dynamically when the dashboard loads.

Sources include:

* Mutual Fund NAV
* Stock market prices
* NPS NAV

Design principles:

* Latest prices fetched via external APIs
* Values cached for short durations to avoid excessive API calls
* Portfolio valuation and XIRR are recalculated using latest prices.

---

## 10. Non-Market Asset Valuation

Assets without market pricing are computed internally.

Examples:

* Fixed Deposits → accrued interest and maturity tracking
* EPF / PPF → contributions + interest calculation
* Gold / Real Estate → manually updated valuations

---

## 11. Dashboard Behavior

Dashboard is **read-only** and does not support editing.

Displayed information:

* Portfolio summary
* Current portfolio value
* Portfolio XIRR
* Asset allocation
* Investment-level performance
* Days remaining for maturity (FDs)

---

## 12. Deployment Model

Initial deployment model:

* Backend: FastAPI running locally
* Frontend: Next.js web UI
* Database: SQLite file

All components run locally on the user's machine.

---

## 13. Key Design Principles

* **Idempotent data ingestion**
* **Event-sourced financial model**
* **Real-time valuation**
* **CLI-first workflows**
* **Local-first architecture**
* **Database portability**

## Structure of app
Follows mono-repo setup

finance-tracker/
│
├── backend/
│   ├── app/
│   ├── models/
│   ├── api/
│   └── main.py
│
├── frontend/
│   ├── app/ (Next.js)
│   └── components/
│
├── scripts/
│   └── ingestion/   (CLI tools)
│
├── docs/
│   ├── requirements.md
│   ├── data_model.md
│   ├── api_spec.md
│   └── build_plan.md
│
└── README.md

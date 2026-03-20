Great idea—this is exactly the right moment to **formalize requirements before jumping into tech decisions**. I’ll convert everything we discussed into a clean **Product Requirements Document (PRD-style)** split into **Functional** and **Non-Functional**.

---

# 📘 Personal Finance Tracker – Requirements

---

# ✅ 1. Functional Requirements

## 🧾 1.1 Investment Coverage

The system must support tracking of the following asset classes:

* Mutual Funds (via CAS import)
* Stocks (via CSV import)
* NPS (via CSV/manual import)
* Fixed Deposits (manual entry)
* EPF (manual entry)
* PPF (manual entry)
* Gold (manual entry)
* Real Estate (manual entry)
* RSUs (manual entry)

---

## 📥 1.2 Data Ingestion

### 1.2.1 CAS Upload (Mutual Funds)

* Parse CAS PDF files
* Extract:

  * folios
  * schemes
  * transactions (buy/sell/dividend)
* Convert into normalized cashflows

---

### 1.2.2 CSV Upload

* Support CSV import for:

  * stocks (e.g., broker exports)
  * NPS
* Allow multiple source formats via adapters

---

### 1.2.3 CLI-Based Data Entry

* All data additions must be supported via CLI or API
* Examples:

  * add cashflow
  * update valuation
  * import files

---

### 1.2.4 Idempotent Data Loading

* Re-running the same import must:

  * NOT create duplicate entries
  * overwrite/update existing records if needed
* Each transaction must have a deterministic unique identity

---

## 🧱 1.3 Data Model

The system must maintain:

* Assets (e.g., equity, debt, gold)
* Investments (e.g., specific MF, stock, FD)
* Cashflows (all inflows/outflows)
* Units/holdings (derived or stored)
* Metadata (account details, folios, etc.)

---

## 📊 1.4 Portfolio Analytics

### 1.4.1 XIRR Calculations

System must compute XIRR at:

* Investment level
* Asset class level (equity, debt, etc.)
* Overall portfolio level

---

### 1.4.2 Portfolio Metrics

* Total invested amount
* Current portfolio value
* Gains/losses
* Asset allocation (equity vs debt vs others)

---

## ⚡ 1.5 Real-Time Valuation

* System must fetch latest market data dynamically:

  * MF NAV
  * stock prices
  * NPS NAV

* Portfolio value and XIRR must:

  * update automatically on dashboard load
  * NOT require manual refresh/upload

---

## 🏦 1.6 Non-Market Assets Computation

### Fixed Deposits

* Calculate:

  * accrued interest
  * maturity value
  * days remaining

---

### EPF / PPF

* Track contributions
* Apply interest rates to compute current value

---

### Gold / Real Estate

* Allow manual valuation updates

---

## 📂 1.7 Important Data Vault

* Store structured information:

  * insurance policies
  * bank accounts
  * folio numbers
  * usernames / notes

---

## 🖥️ 1.8 Read-Only Dashboard

* UI must be read-only (no editing required)
* Display:

  * portfolio summary
  * XIRR metrics
  * asset allocation
  * investment drilldowns

---

## 🔄 1.9 Historical Tracking (Optional but expected)

* Ability to:

  * track portfolio over time
  * visualize net worth trends

---

# ⚙️ 2. Non-Functional Requirements

---

## 🔁 2.1 Idempotency & Data Integrity

* All ingestion operations must be idempotent
* Duplicate imports must not corrupt data
* System must ensure strong consistency of financial records

---

## ⚡ 2.2 Performance

* Dashboard load should be fast (<1–2 seconds ideally)
* Real-time price fetching must use caching to avoid latency

---

## 🧠 2.3 Accuracy

* Financial calculations (XIRR, valuations) must be precise
* Date handling must be consistent and timezone-safe

---

## 🔌 2.4 Extensibility

* Easy to add:

  * new asset classes
  * new import formats
  * new data sources/APIs

---

## 🔐 2.5 Security

* Sensitive data must:

  * not be stored in plain text (for critical fields)
* System can remain simple (single-user), but must avoid obvious risks

---

## 🧩 2.6 Modularity

System should have clear separation of:

* ingestion layer
* core financial engine
* pricing service
* analytics layer
* UI layer

---

## 🧪 2.7 Reliability

* System must tolerate:

  * repeated imports
  * partial failures in parsing
* Should allow reprocessing of data safely

---

## 🌐 2.8 Availability

* System should work:

  * without constant internet (except for live prices)
* Graceful fallback if price APIs fail

---

## 📦 2.9 Maintainability

* Codebase should be:

  * cleanly structured
  * easy to debug
  * testable (especially XIRR + parsing logic)

---

## 🧑‍💻 2.10 Developer Experience

* CLI-first workflow must be:

  * simple
  * scriptable
  * reproducible

---

# 🎯 Summary (What You’re Building)

You are building:

> **A CLI-driven, idempotent, event-sourced personal finance engine with real-time valuation and a read-only analytics dashboard**

---

# 🚀 Next Step

Now that requirements are clear, next we should decide:

1. **Data model (exact schema)**
2. **API design (what Python exposes)**
3. **Price fetching strategy (India-specific)**
4. **Folder/project structure**

# Addendum: Goal Tracking Requirements

## 1. Functional Requirements – Goals

### 1.1 Goal Management

System must allow defining financial goals with:

* name (e.g., “Retirement”, “House”, “Child Education”)
* target amount
* target date
* optional notes

---

### 1.2 Investment–Goal Mapping

* A goal can have **multiple investments**
* An investment can belong to **multiple goals**
* Mapping must include:

  * allocation percentage (e.g., 40% of MF A → Retirement, 60% → Child Education)

---

### 1.3 Goal Valuation

System must compute for each goal:

* current value (based on allocated portions of investments)
* total invested amount
* XIRR (optional but preferred)
* percentage completion

---

### 1.4 Goal Progress Tracking (Frontend)

Dashboard must show:

* goal target amount
* current value
* % achieved
* remaining amount

---

### 1.5 Future Planning / Required Investment

System must estimate:

* required monthly investment (SIP) to reach goal
* based on:

  * current value
  * target value
  * time remaining
  * assumed rate of return (configurable)

---

### 1.6 Goal Allocation Impact

* Portfolio allocation must be viewable:

  * by asset class
  * by goal

---

## 2. Non-Functional Additions

* Goal calculations must be computed dynamically using real-time valuation
* Allocation logic must remain consistent even with partial investment overlaps
* System must handle fractional allocation accurately


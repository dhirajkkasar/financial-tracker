# Personal Finance Tracker – System Components & Build Plan

## 🧩 Main Components

### 1. Ingestion Layer

* CLI / API for CAS, CSV, manual entries
* Idempotent transaction handling

---

### 2. Data Layer

* SQLite database
* ORM models (investments, transactions, goals)

---

### 3. Core Engine

* Holdings calculation (units, invested amount)
* XIRR computation
* Goal allocation logic

---

### 4. Pricing Service

* Fetch NAV / stock prices
* Caching mechanism

---

### 5. Valuation Engine

* Compute current values
* Portfolio, asset-level, and goal-level metrics

---

### 6. API Layer (FastAPI)

* Read APIs (portfolio, investments, goals)
* Write APIs (transactions, imports)

---

### 7. Frontend (Next.js)

* Overview dashboard
* Asset-class tabs
* Goal tracking
* Important data section

---

# 🚀 Phased Build Plan

## 🟢 Phase 1: Core Backbone (MVP)

* Database schema + ORM setup
* `/transactions` API (idempotent)
* Basic holdings calculation
* Portfolio summary API (no real-time pricing yet)

**Goal:** Validate data model and ingestion flow

---

## 🟡 Phase 2: XIRR + Basic UI

* XIRR engine (investment + portfolio level)
* Simple Next.js dashboard
* Display:

  * total invested
  * current value (static/manual)
  * XIRR

**Goal:** Validate correctness of returns

---

## 🔵 Phase 3: Real-Time Valuation

* Pricing service (NAV, stocks)
* Cache layer
* Live portfolio valuation

**Goal:** Ensure dashboard reflects current market values

---

## 🟣 Phase 4: Asset Views

* Asset class aggregation (equity, debt, etc.)
* Asset-level XIRR
* Investment list UI (active/inactive)

**Goal:** Validate portfolio breakdown usability

---

## 🟠 Phase 5: Goals Engine

* Goals + allocation tables
* Goal valuation logic
* Required SIP calculation
* Goals section in UI

**Goal:** Validate planning and tracking features

---

## 🔴 Phase 6: Imports & Automation

* CAS parser integration
* CSV adapters
* CLI workflows

**Goal:** Enable real-world data ingestion

---

## ⚫ Phase 7: Polish & Enhancements

* Important data vault
* Historical snapshots
* Filters and sorting
* Performance tuning

---

# 🎯 Build Strategy

* Each phase delivers **independent value**
* Each phase is **testable in isolation**
* System evolves incrementally without rework
* Focus on **correctness first, automation later**


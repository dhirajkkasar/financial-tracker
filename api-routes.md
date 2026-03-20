# Financial Tracker — API Routes

**Version:** 0.1  
**Base URL (local):** `http://localhost:8000`  
**Framework:** FastAPI (Python)

---

## Conventions

- All responses are JSON
- Dates use ISO 8601 format: `YYYY-MM-DD`
- Amounts are always in INR (decimal)
- `{id}` parameters are integers
- Financial year format: `"2023-24"` (string)

---

## Assets

| Method | Path | Description |
|---|---|---|
| GET | `/assets` | List all assets. Filter via `?type=MF&class=EQUITY&active=true` |
| POST | `/assets` | Create a new asset |
| GET | `/assets/{id}` | Single asset with summary (current value, total invested) |
| PUT | `/assets/{id}` | Update asset metadata |
| DELETE | `/assets/{id}` | Soft delete (sets `is_active = false`) |

---

## Transactions

| Method | Path | Description |
|---|---|---|
| GET | `/assets/{id}/transactions` | All transactions for an asset, ordered by date |
| POST | `/assets/{id}/transactions` | Add a transaction to an asset |
| PUT | `/transactions/{id}` | Edit a transaction |
| DELETE | `/transactions/{id}` | Delete a transaction |

**POST `/assets/{id}/transactions` body:**
```json
{
  "type": "BUY",
  "date": "2024-01-15",
  "units": 10.5,
  "price_per_unit": 450.00,
  "forex_rate": null,
  "amount": 4725.00,
  "charges": 25.00,
  "notes": "SIP instalment"
}
```

---

## FD Details

| Method | Path | Description |
|---|---|---|
| GET | `/assets/{id}/fd-detail` | Get FD terms + computed maturity amount |
| POST | `/assets/{id}/fd-detail` | Create FD terms (one per asset) |
| PUT | `/assets/{id}/fd-detail` | Update FD terms |

**POST body:**
```json
{
  "bank": "HDFC Bank",
  "fd_type": "FD",
  "principal_amount": 100000,
  "interest_rate_pct": 7.25,
  "compounding": "QUARTERLY",
  "start_date": "2023-04-01",
  "maturity_date": "2026-04-01",
  "maturity_amount": null,
  "is_matured": false,
  "tds_applicable": true
}
```

---

## Valuations

Manual price snapshots for illiquid assets (real estate, PPF, EPF, gold).

| Method | Path | Description |
|---|---|---|
| GET | `/assets/{id}/valuations` | Full valuation history |
| POST | `/assets/{id}/valuations` | Add a valuation snapshot |
| DELETE | `/valuations/{id}` | Remove a valuation entry |

---

## Returns

All return endpoints compute on-the-fly (no caching). Typically < 50ms for personal portfolio sizes.

| Method | Path | Description |
|---|---|---|
| GET | `/assets/{id}/returns` | XIRR + CAGR + absolute return for one asset |
| GET | `/assets/{id}/returns/lots` | Per-lot FIFO breakdown (for tax view) |
| GET | `/returns/overview` | Portfolio-wide XIRR, absolute return, total invested vs current |

**GET `/assets/{id}/returns` response:**
```json
{
  "asset_id": 12,
  "asset_name": "Axis Bluechip Fund",
  "total_invested": 120000,
  "current_value": 158400,
  "absolute_return_pct": 32.0,
  "xirr_pct": 14.2,
  "cagr_pct": null,
  "holding_days": 912
}
```

**GET `/assets/{id}/returns/lots` response:**
```json
{
  "lots": [
    {
      "lot_id": "uuid-xxx",
      "buy_date": "2021-03-01",
      "buy_amount": 50000,
      "units": 110.5,
      "current_value": 82000,
      "holding_days": 1200,
      "is_short_term": false,
      "unrealised_gain": 32000,
      "xirr_pct": 16.1
    }
  ]
}
```

---

## Prices

| Method | Path | Description |
|---|---|---|
| GET | `/assets/{id}/price` | Latest cached price + staleness info |
| POST | `/assets/{id}/price/refresh` | Force fetch latest price from feed |
| POST | `/prices/refresh-all` | Refresh all assets with stale prices |

**GET `/assets/{id}/price` response:**
```json
{
  "asset_id": 12,
  "price_inr": 48.72,
  "fetched_at": "2026-03-17T09:15:00",
  "source": "mfapi.in",
  "is_stale": false
}
```

---

## Overview (Dashboard)

| Method | Path | Description |
|---|---|---|
| GET | `/overview` | Total value, overall XIRR, absolute return, invested amount |
| GET | `/overview/allocation` | Equity / Debt / Gold / Real Estate split (value + %) |
| GET | `/overview/gainers` | Top 5 gainers and losers by absolute return % |

**GET `/overview` response:**
```json
{
  "total_invested": 2500000,
  "current_value": 3180000,
  "absolute_return_pct": 27.2,
  "xirr_pct": 13.8,
  "as_of": "2026-03-17"
}
```

---

## Goals

| Method | Path | Description |
|---|---|---|
| GET | `/goals` | All goals with current progress |
| POST | `/goals` | Create a goal |
| GET | `/goals/{id}` | Goal detail with linked assets |
| PUT | `/goals/{id}` | Update goal |
| DELETE | `/goals/{id}` | Delete goal |
| POST | `/goals/{id}/allocations` | Link an asset to this goal with allocation % |
| PUT | `/goals/{id}/allocations/{asset_id}` | Update allocation % |
| DELETE | `/goals/{id}/allocations/{asset_id}` | Unlink asset from goal |
| GET | `/goals/{id}/sip-calculator` | Monthly SIP needed. Pass `?rate=12` for assumed return |

**POST `/goals` body:**
```json
{
  "name": "Retirement",
  "target_amount_inr": 30000000,
  "target_date": "2045-01-01",
  "assumed_return_pct": 12.0,
  "notes": "25x annual expenses"
}
```

**GET `/goals/{id}/sip-calculator` response:**
```json
{
  "goal_id": 1,
  "target_amount": 30000000,
  "current_value_toward_goal": 4200000,
  "gap": 25800000,
  "months_remaining": 226,
  "assumed_return_pct": 12.0,
  "monthly_sip_needed": 42350
}
```

---

## Tax

| Method | Path | Description |
|---|---|---|
| GET | `/tax/summary` | STCG + LTCG for current FY (Apr–Mar) |
| GET | `/tax/summary?fy=2023-24` | Summary for a specific financial year |
| GET | `/tax/unrealised` | Unrealised gains mark-to-market |
| GET | `/tax/harvest-opportunities` | Lots with unrealised losses that can offset gains |

**GET `/tax/summary` response:**
```json
{
  "fy": "2025-26",
  "equity": {
    "stcg_gain": 15000,
    "stcg_tax": 3000,
    "ltcg_gain": 180000,
    "ltcg_exemption_used": 125000,
    "ltcg_taxable": 55000,
    "ltcg_tax": 6875
  },
  "debt": {
    "gain": 8000,
    "tax_at_slab": true
  },
  "total_estimated_tax": 9875
}
```

---

## Import

Two-step flow: preview first (parse only, no DB write), then commit.

| Method | Path | Description |
|---|---|---|
| POST | `/import/cas-pdf` | Upload CAMS / KFintech CAS PDF |
| POST | `/import/nps-csv` | Upload NSDL NPS transaction CSV |
| POST | `/import/broker-csv` | Upload Zerodha / Groww CSV. Pass `?broker=zerodha` |
| POST | `/import/commit` | Commit a previously previewed import |

All import endpoints accept `multipart/form-data` with a `file` field.

**Preview response (all import types):**
```json
{
  "preview_id": "abc123",
  "parsed": 148,
  "new": 32,
  "duplicates": 116,
  "conflicts": 0,
  "transactions": [
    {
      "date": "2024-01-05",
      "asset_name": "Axis Bluechip Fund",
      "type": "SIP",
      "amount": 5000,
      "units": 102.3,
      "status": "new"
    }
  ]
}
```

**POST `/import/commit` body:**
```json
{ "preview_id": "abc123" }
```

---

## Reference Data

| Method | Path | Description |
|---|---|---|
| GET | `/interest-rates` | All PPF + EPF historical rates |
| GET | `/interest-rates?instrument=PPF&date=2020-04-01` | Rate applicable on a specific date |

**GET `/interest-rates?instrument=PPF&date=2020-04-01` response:**
```json
{
  "instrument": "PPF",
  "rate_pct": 7.1,
  "effective_from": "2020-04-01",
  "effective_to": null,
  "source": "Ministry of Finance"
}
```

---

## Important Data

| Method | Path | Description |
|---|---|---|
| GET | `/important-data` | All entries, grouped by category |
| POST | `/important-data` | Add an entry |
| PUT | `/important-data/{id}` | Update an entry |
| DELETE | `/important-data/{id}` | Delete an entry |

**POST body:**
```json
{
  "category": "BANK",
  "label": "HDFC Savings Account",
  "fields": {
    "account_number": "XXXX1234",
    "ifsc": "HDFC0001234",
    "branch": "Pune Main"
  },
  "notes": "Primary salary account"
}
```

---

## Enum Reference

**asset_type:** `STOCK_IN` `STOCK_US` `MF` `FD` `RD` `PPF` `EPF` `NPS` `GOLD` `SGB` `REAL_ESTATE`

**asset_class:** `EQUITY` `DEBT` `GOLD` `REAL_ESTATE` `MIXED`

**transaction type:** `BUY` `SELL` `DIVIDEND` `INTEREST` `SIP` `REDEMPTION` `BONUS` `SPLIT` `CONTRIBUTION` `WITHDRAWAL` `SWITCH_IN` `SWITCH_OUT`

**compounding:** `MONTHLY` `QUARTERLY` `HALF_YEARLY` `YEARLY` `SIMPLE`

**import broker:** `zerodha` `groww` `generic`

**important_data category:** `BANK` `MF_FOLIO` `IDENTITY` `INSURANCE` `ACCOUNT` `OTHER`

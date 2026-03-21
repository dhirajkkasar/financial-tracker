# Stock P&L and Inactive-Asset Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three bugs in stock tracking: (1) auto-mark fully-exited stocks as inactive on import, (2) fix `total_invested` to show open-lot cost basis instead of all-time buy total, (3) retroactive fix for existing data via a CLI command.

**Architecture:** All changes are backend-only. The frontend (`HoldingsTable.tsx`) already handles inactive stocks (hides current P&L, shows only all-time realized gains, applies "Closed" badge, dim colors). The stocks page already defaults to `activeOnly=true`. No frontend changes needed.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, existing `returns_service.py` + `import_service.py` + `lot_engine.py` (pure functions, no changes needed to lot engine itself).

---

## Background: What Already Works

- `lot_engine.py` already computes open lots with `buy_amount_inr = buy_price × remaining_units`
- `compute_gains_summary()` already returns 0 for exited positions (empty open_lots)
- `HoldingsTable.tsx` `computeRow()` already uses `st_unrealised + lt_unrealised` for current P&L — correct for exited positions (both = 0)
- Stocks page: `activeOnly = true` default, "Show Inactive" toggle exists
- XIRR for exited stocks: already correct — the `if current_value > 0` guard prevents adding a terminal `(today, 0)` cashflow, so XIRR uses only the actual buy/sell cashflows

## Root Causes of Bugs

1. **`is_active` never flipped for stocks** — only MF (CAS) and EPF (zero balance) auto-mark inactive; broker CSV import never does this
2. **`total_invested` = all-time buys** — line 337 in `returns_service.py` accumulates `total_invested += abs(amount_inr)` for every BUY regardless of whether those shares were later sold; should be open-lot cost basis only

---

## Files Modified

| File | Change |
|---|---|
| `backend/app/services/import_service.py` | After broker CSV commit: compute net_units per touched STOCK_IN/STOCK_US asset, mark inactive if ≤ 0 |
| `backend/app/services/returns_service.py` | Fix `total_invested` = open lots cost basis in `_compute_market_based_returns` |
| `backend/app/api/assets.py` | Add `POST /assets/fix-inactive-stocks` endpoint for retroactive fix |
| `backend/cli.py` | Add `fix-inactive` subcommand |
| `backend/tests/integration/test_import_flow.py` | Test auto-inactive on broker CSV commit |
| `backend/tests/unit/test_mf_returns.py` | Test `total_invested` = open lots cost basis |

---

## Task 1: Fix `total_invested` in `_compute_market_based_returns`

**Files:**
- Modify: `backend/app/services/returns_service.py:317-421`
- Test: `backend/tests/unit/test_mf_returns.py`

Currently `total_invested` accumulates ALL buy amounts (line 337). Fix: move the lot computation before `total_invested` assignment, derive it from `open_lots`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/test_mf_returns.py`:

```python
from unittest.mock import MagicMock, patch
from datetime import date
from app.services.returns_service import ReturnsService


def test_total_invested_uses_open_lots_cost_basis():
    """
    total_invested should = cost basis of currently HELD shares only.
    Buy 100 @ 1500 = ₹1,50,000. Sell 40 → 60 remain.
    Open lot cost basis = 60 × 1500 = ₹90,000 (not ₹1,50,000).
    """
    db = MagicMock()

    # Stub: asset
    asset = MagicMock()
    asset.id = 1
    asset.asset_type.value = "STOCK_IN"

    # Transactions: BUY 100 @ 1500, SELL 40 @ 1800
    buy_txn = MagicMock()
    buy_txn.type.value = "BUY"
    buy_txn.date = date(2023, 1, 1)
    buy_txn.units = 100.0
    buy_txn.price_per_unit = 1500.0
    buy_txn.amount_inr = -15_000_000   # -₹1,50,000 in paise
    buy_txn.lot_id = "lot-1"
    buy_txn.id = 1

    sell_txn = MagicMock()
    sell_txn.type.value = "SELL"
    sell_txn.date = date(2024, 1, 1)
    sell_txn.units = 40.0
    sell_txn.price_per_unit = 1800.0
    sell_txn.amount_inr = 7_200_000    # +₹72,000 in paise
    sell_txn.lot_id = None
    sell_txn.id = 2

    svc = ReturnsService.__new__(ReturnsService)
    svc.db = db
    svc.txn_repo = MagicMock()
    svc.txn_repo.list_by_asset.return_value = [buy_txn, sell_txn]
    svc.price_repo = MagicMock()
    svc.price_repo.get_by_asset_id.return_value = MagicMock(
        price_inr=200_000,   # ₹2000 per share in paise
        fetched_at=__import__('datetime').datetime.utcnow(),
    )

    result = svc._compute_market_based_returns(asset)

    # 60 remaining shares × ₹1500 = ₹90,000 cost basis
    assert abs(result["total_invested"] - 90_000.0) < 1.0, (
        f"Expected ₹90,000, got {result['total_invested']}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_mf_returns.py::test_total_invested_uses_open_lots_cost_basis -v
```

Expected: FAIL — `total_invested` is ~150,000 (all buys), not 90,000

- [ ] **Step 3: Implement the fix in `returns_service.py`**

In `_compute_market_based_returns` (currently lines ~317–421), restructure so lot computation happens before `total_invested` is assigned:

```python
def _compute_market_based_returns(self, asset) -> dict:
    asset_id = asset.id
    asset_type = asset.asset_type.value
    transactions = self.txn_repo.list_by_asset(asset_id)

    # Filter excluded types
    filtered_txns = [t for t in transactions if t.type.value not in EXCLUDED_TYPES]

    # Build XIRR cashflows (paise → INR) — no longer accumulates total_invested here
    cashflows = []
    for txn in filtered_txns:
        amount_inr = txn.amount_inr / 100.0
        txn_type = txn.type.value
        if txn_type in OUTFLOW_TYPES:
            cashflows.append((txn.date, amount_inr))
        elif txn_type in INFLOW_TYPES:
            cashflows.append((txn.date, amount_inr))

    # Get current price from cache; compute current_value and total_units
    price_cache = self.price_repo.get_by_asset_id(asset_id)
    current_value = None
    if price_cache:
        total_units = sum(
            t.units or 0 for t in filtered_txns if t.type.value in OUTFLOW_TYPES
        ) - sum(
            t.units or 0 for t in filtered_txns if t.type.value in INFLOW_TYPES
        )
        current_price_inr = price_cache.price_inr / 100.0
        current_value = total_units * current_price_inr
        if current_value > 0:
            cashflows.append((date.today(), current_value))

    xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None

    total_inflows = sum(
        txn.amount_inr / 100.0
        for txn in filtered_txns
        if txn.type.value in INFLOW_TYPES
    )
    effective_current = current_value if current_value is not None else (
        total_inflows if total_inflows > 0 else None
    )

    # --- Lot computation (moved up so open_lots drives total_invested) ---
    gains_summary = {
        "st_unrealised_gain": None, "lt_unrealised_gain": None,
        "st_realised_gain": None, "lt_realised_gain": None,
    }
    open_lots: list[dict] = []
    if asset_type != "SGB":
        try:
            open_lots, matched_sells = self._build_lots_and_sells(
                asset_id, asset_type, transactions
            )
            gains_summary = compute_gains_summary(open_lots, matched_sells, asset_type)
        except Exception as e:
            logger.warning("Error computing gain summary for asset %d: %s", asset_id, str(e))

    # total_invested = cost basis of CURRENTLY HELD shares (open lots only).
    # For fully exited positions this is 0; for active positions it's sum of remaining lot costs.
    # SGB exception: lot computation is skipped for SGB (tax-exempt on maturity), so fall back
    # to the all-buy total to avoid showing ₹0 Invested for held SGB positions.
    if asset_type == "SGB":
        total_invested = sum(
            abs(txn.amount_inr / 100.0)
            for txn in filtered_txns
            if txn.type.value in OUTFLOW_TYPES
        )
    else:
        total_invested = sum(lot["buy_amount_inr"] for lot in open_lots)

    # CAGR / abs_return on current position
    cagr = None
    abs_return = None
    if total_invested > 0 and effective_current is not None:
        abs_return = compute_absolute_return(total_invested, effective_current)
        if filtered_txns:
            oldest = min(filtered_txns, key=lambda t: t.date)
            years = (date.today() - oldest.date).days / 365.0
            cagr = compute_cagr(total_invested, effective_current, years)

    # Price staleness metadata
    price_is_stale = None
    price_fetched_at = None
    if price_cache:
        from datetime import datetime, timedelta
        threshold = STALE_MINUTES.get(asset.asset_type)
        if threshold is not None:
            price_is_stale = datetime.utcnow() - price_cache.fetched_at > timedelta(minutes=threshold)
        price_fetched_at = price_cache.fetched_at.isoformat()

    result = {
        "asset_id": asset.id,
        "asset_type": asset_type,
        "xirr": xirr,
        "cagr": cagr,
        "absolute_return": abs_return,
        "total_invested": total_invested,
        "current_value": effective_current,
        "message": None,
        "price_is_stale": price_is_stale,
        "price_fetched_at": price_fetched_at,
    }
    result.update(gains_summary)
    return result
```

**Key change:** removed `total_invested = 0.0` and `total_invested += abs(amount_inr)` from the cashflow loop; added `total_invested = sum(lot["buy_amount_inr"] for lot in open_lots)` after lot computation.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/unit/test_mf_returns.py::test_total_invested_uses_open_lots_cost_basis -v
```

Expected: PASS

- [ ] **Step 5: Run full unit test suite to catch regressions**

```bash
cd backend && uv run pytest tests/unit/ -v
```

Expected: all existing tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/returns_service.py backend/tests/unit/test_mf_returns.py
git commit -m "fix: total_invested uses open-lot cost basis for stock assets"
```

---

## Task 2: Auto-mark stocks inactive after broker CSV import

**Files:**
- Modify: `backend/app/services/import_service.py:83-155`
- Test: `backend/tests/integration/test_import_flow.py`

After committing broker CSV transactions, compute net_units per touched STOCK_IN/STOCK_US asset and mark inactive if ≤ 0.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/integration/test_import_flow.py`:

```python
class TestBrokerCSVAutoInactive:
    def test_fully_sold_stock_marked_inactive_after_import(self, client):
        """
        Import a CSV with BUY 10 + SELL 10 for the same stock.
        After commit, that asset should have is_active=False.
        """
        import io, csv
        from datetime import date

        def make_row(trade_type, qty, price, trade_id):
            return {
                "symbol": "TESTCO",
                "isin": "INE999X01234",
                "trade_date": "2024-01-15",
                "exchange": "NSE",
                "segment": "EQ",
                "series": "EQ",
                "trade_type": trade_type,
                "auction": "false",
                "quantity": str(qty),
                "price": str(price),
                "trade_id": trade_id,
                "order_id": f"ORD{trade_id}",
                "order_execution_time": "2024-01-15T10:00:00",
            }

        rows = [make_row("buy", 10, 100.0, "T001"), make_row("sell", 10, 120.0, "T002")]
        fieldnames = rows[0].keys()
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        csv_bytes = buf.getvalue().encode()

        # Preview
        resp = client.post(
            "/import/broker-csv?broker=zerodha",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        preview_id = resp.json()["preview_id"]

        # Commit
        resp = client.post("/import/commit", json={"preview_id": preview_id})
        assert resp.status_code == 200

        # Asset should be inactive
        assets = client.get("/assets?type=STOCK_IN").json()
        testco = next((a for a in assets if a["identifier"] == "INE999X01234"), None)
        assert testco is not None
        assert testco["is_active"] is False, "Fully-sold stock should be inactive"

    def test_partially_sold_stock_stays_active(self, client):
        """
        Import BUY 10 + SELL 5. Asset should remain is_active=True.
        """
        import io, csv

        def make_row(trade_type, qty, price, trade_id):
            return {
                "symbol": "PARTIAL",
                "isin": "INE888X01234",
                "trade_date": "2024-02-01",
                "exchange": "NSE",
                "segment": "EQ",
                "series": "EQ",
                "trade_type": trade_type,
                "auction": "false",
                "quantity": str(qty),
                "price": str(price),
                "trade_id": trade_id,
                "order_id": f"ORD{trade_id}",
                "order_execution_time": "2024-02-01T10:00:00",
            }

        rows = [make_row("buy", 10, 200.0, "T101"), make_row("sell", 5, 250.0, "T102")]
        fieldnames = rows[0].keys()
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        csv_bytes = buf.getvalue().encode()

        resp = client.post(
            "/import/broker-csv?broker=zerodha",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        preview_id = resp.json()["preview_id"]

        resp = client.post("/import/commit", json={"preview_id": preview_id})
        assert resp.status_code == 200

        assets = client.get("/assets?type=STOCK_IN").json()
        partial = next((a for a in assets if a["identifier"] == "INE888X01234"), None)
        assert partial is not None
        assert partial["is_active"] is True, "Partially-sold stock should stay active"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/integration/test_import_flow.py::TestBrokerCSVAutoInactive -v
```

Expected: FAIL — `is_active` stays True for fully-sold stock

- [ ] **Step 3: Implement in `import_service.py`**

In the `commit()` method, after the transaction creation loop and the CAS snapshot section, add auto-inactive logic before `self.db.commit()`:

```python
# Track which STOCK_IN/STOCK_US assets were touched in this import
touched_stock_asset_ids: set[int] = set()
```

Add to the transaction loop (inside `for txn in parsed_txns:`, after `asset = self._find_or_create_asset(...)`):

```python
if txn.asset_type in {"STOCK_IN", "STOCK_US"}:
    touched_stock_asset_ids.add(asset.id)
```

Then after the CAS snapshot section, before `self.db.commit()`:

```python
# Auto-mark fully-exited STOCK_IN/STOCK_US assets as inactive
_STOCK_OUTFLOWS = {"BUY", "SIP", "VEST"}
_STOCK_INFLOWS = {"SELL", "REDEMPTION"}
for asset_id in touched_stock_asset_ids:
    stock_asset = asset_repo.get_by_id(asset_id)
    if stock_asset is None:
        continue
    all_txns = txn_repo.list_by_asset(asset_id)
    net_units = sum(
        (t.units or 0.0) if t.type.value in _STOCK_OUTFLOWS
        else -(t.units or 0.0) if t.type.value in _STOCK_INFLOWS
        else 0.0
        for t in all_txns
    )
    if net_units <= 1e-6 and stock_asset.is_active:
        stock_asset.is_active = False
        logger.info(
            "Auto-marked asset %d '%s' inactive (net_units=%.4f)",
            asset_id, stock_asset.name, net_units,
        )
```

Also initialise `touched_stock_asset_ids: set[int] = set()` before the `for txn in parsed_txns:` loop.

The complete `commit()` method signature doesn't change; only the internals.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/integration/test_import_flow.py::TestBrokerCSVAutoInactive -v
```

Expected: PASS

- [ ] **Step 5: Run full integration suite**

```bash
cd backend && uv run pytest tests/integration/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/import_service.py backend/tests/integration/test_import_flow.py
git commit -m "feat: auto-mark fully-exited stocks inactive on broker CSV import"
```

---

## Task 3: `POST /assets/fix-inactive-stocks` + CLI `fix-inactive`

**Files:**
- Modify: `backend/app/api/assets.py`
- Modify: `backend/cli.py`

Retroactively scan all STOCK_IN/STOCK_US assets, mark those with net_units ≤ 0 as inactive.

- [ ] **Step 1: Write the failing integration test**

Add to `backend/tests/integration/test_assets_api.py`:

```python
class TestFixInactiveStocks:
    def test_fix_inactive_stocks_marks_exited_assets(self, client, db):
        """POST /assets/fix-inactive-stocks marks assets with net_units=0 as inactive."""
        from datetime import date
        from app.models.asset import Asset, AssetType, AssetClass
        from app.models.transaction import Transaction, TransactionType
        import uuid

        # Create a stock with BUY 10 + SELL 10 (fully exited) — still is_active=True
        asset = Asset(
            name="Exited Stock",
            identifier="INE000EX9999",
            asset_type=AssetType.STOCK_IN,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            is_active=True,
        )
        db.add(asset)
        db.flush()

        buy = Transaction(
            txn_id=f"test_{uuid.uuid4().hex}",
            asset_id=asset.id,
            type=TransactionType.BUY,
            date=date(2023, 1, 1),
            units=10.0,
            price_per_unit=100.0,
            amount_inr=-100_000,
            charges_inr=0,
            lot_id=str(uuid.uuid4()),
        )
        sell = Transaction(
            txn_id=f"test_{uuid.uuid4().hex}",
            asset_id=asset.id,
            type=TransactionType.SELL,
            date=date(2023, 6, 1),
            units=10.0,
            price_per_unit=120.0,
            amount_inr=120_000,
            charges_inr=0,
        )
        db.add_all([buy, sell])
        db.commit()

        resp = client.post("/assets/fix-inactive-stocks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fixed"] >= 1

        # Reload and verify
        db.refresh(asset)
        assert asset.is_active is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/integration/test_assets_api.py::TestFixInactiveStocks -v
```

Expected: FAIL — 404 (endpoint doesn't exist yet)

- [ ] **Step 3: Add endpoint to `assets.py`**

Add at the end of `backend/app/api/assets.py`:

```python
@router.post("/fix-inactive-stocks")
def fix_inactive_stocks(db: Session = Depends(get_db)):
    """
    Retroactively scan all STOCK_IN/STOCK_US assets.
    Mark as inactive any asset whose net_units (total bought - total sold) <= 0.
    Safe to run multiple times (idempotent).
    """
    from app.models.transaction import Transaction
    from app.repositories.transaction_repo import TransactionRepository

    _OUTFLOWS = {"BUY", "SIP", "VEST"}
    _INFLOWS = {"SELL", "REDEMPTION"}
    stock_types = [AssetType.STOCK_IN, AssetType.STOCK_US]

    assets = db.query(Asset).filter(Asset.asset_type.in_(stock_types)).all()
    txn_repo = TransactionRepository(db)
    fixed = 0

    for asset in assets:
        txns = txn_repo.list_by_asset(asset.id)
        net_units = sum(
            (t.units or 0.0) if t.type.value in _OUTFLOWS
            else -(t.units or 0.0) if t.type.value in _INFLOWS
            else 0.0
            for t in txns
        )
        if net_units <= 1e-6 and asset.is_active:
            asset.is_active = False
            fixed += 1

    db.commit()
    return {"fixed": fixed, "total_checked": len(assets)}
```

Make sure `AssetType` and `Asset` are already imported at the top of `assets.py` (they should be).

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/integration/test_assets_api.py::TestFixInactiveStocks -v
```

Expected: PASS

- [ ] **Step 5: Add CLI `fix-inactive` command to `cli.py`**

In `build_parser()`, add after `sub.add_parser("snapshot", ...)`:

```python
sub.add_parser("fix-inactive", help="Scan all stocks and mark fully-exited ones as inactive")
```

In `main()`, add in the `elif` chain:

```python
elif args.command == "fix-inactive":
    result = _api("post", "/assets/fix-inactive-stocks")
    print(f"✓ fix-inactive: {result['fixed']} marked inactive out of {result['total_checked']} checked")
```

- [ ] **Step 6: Run fix-inactive against the real DB**

```bash
cd backend && uv run python cli.py fix-inactive
```

Expected: prints something like `✓ fix-inactive: 12 marked inactive out of 35 checked`

- [ ] **Step 7: Run full test suite**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/assets.py backend/cli.py backend/tests/integration/test_assets_api.py
git commit -m "feat: add fix-inactive-stocks endpoint and CLI command for retroactive inactive marking"
```

---

## Verification Checklist

After all tasks complete:

- [ ] `uv run python cli.py fix-inactive` — shows N stocks marked inactive
- [ ] Open dashboard → Stocks tab → only active stocks visible by default
- [ ] Click "Show Inactive" — closed positions appear with "Closed" badge, dimmed colors
- [ ] For an active stock with partial sells: "Invested" column shows cost of remaining shares (not total ever invested)
- [ ] For an exited stock: Current P&L = `—`, All-time P&L = realized gains, XIRR shown
- [ ] `uv run pytest tests/ --tb=short` — full suite green

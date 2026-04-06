# US Stock Specific Lot Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace FIFO-only lot matching for STOCK_US with specific-lot matching driven by `date_acquired` data from Fidelity PDFs, so realized STCG/LTCG gains reflect the actual lots sold.

**Architecture:** The Fidelity PDF importer is refactored to emit SELL-only transactions with acquisition metadata. A new `FidelityPreCommitProcessor` runs before DB writes in `commit()`, queries existing BUY/VEST lots by `date_acquired`, and splits each SELL into partial-SELL transactions pinned to specific `lot_id`s. The lot engine gets a `match_lots` function that uses `lot_id` on SELL rows for specific matching and falls back to FIFO when absent.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, SQLite, pytest, uv

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/importers/base.py` | Modify | Add 3 acquisition fields to `ParsedTransaction` |
| `app/engine/lot_helper.py` | Modify | Add `lot_id` to `_Sell`; populate from transaction |
| `app/engine/lot_engine.py` | Modify | Add `match_lots` function with specific-lot + FIFO fallback |
| `app/services/returns/strategies/market_based.py` | Modify | Call `match_lots` instead of `match_lots_fifo` |
| `app/services/import_service.py` | Modify | Respect pre-assigned `lot_id` on `ParsedTransaction` |
| `app/services/imports/post_processors/base.py` | Modify | Add `IPreCommitProcessor` protocol |
| `app/services/imports/post_processors/fidelity.py` | Create | `FidelityPreCommitProcessor` — lot resolution logic |
| `app/services/imports/orchestrator.py` | Modify | Add `pre_commit_processors` registry; call before txn loop |
| `app/api/dependencies.py` | Modify | Inject `FidelityPreCommitProcessor` |
| `app/importers/fidelity_pdf_importer.py` | Modify | Emit SELL-only with acquisition fields |
| `tests/unit/test_lot_engine.py` | Modify | Add `match_lots` tests |
| `tests/unit/test_fidelity_pdf_importer.py` | Modify | Update for SELL-only output |
| `tests/unit/test_fidelity_pre_commit_processor.py` | Create | All lot-resolution logic tests |
| `tests/integration/test_fidelity_imports.py` | Modify | End-to-end lot matching scenarios |

---

## Task 1: Add acquisition fields to ParsedTransaction

**Files:**
- Modify: `app/importers/base.py:23-45`

No test needed — this is a pure dataclass field addition. All callers use keyword args so adding optional fields is non-breaking.

- [ ] **Step 1: Add three optional fields to `ParsedTransaction`**

In `app/importers/base.py`, after the `forex_rate` field (line 44), add:

```python
    forex_rate: Optional[float] = None    # USD/INR rate used for conversion
    # Fidelity PDF acquisition metadata — used by FidelityPreCommitProcessor
    acquisition_date: Optional[date] = None        # date_acquired from Fidelity PDF sale row
    acquisition_cost: Optional[float] = None       # cost basis in INR (cost_usd * acquisition_forex_rate)
    acquisition_forex_rate: Optional[float] = None # USD/INR rate at acquisition date
```

- [ ] **Step 2: Verify no import errors**

```bash
cd backend && uv run python -c "from app.importers.base import ParsedTransaction; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/importers/base.py
git commit -m "feat: add acquisition_date/cost/forex_rate fields to ParsedTransaction"
```

---

## Task 2: Add `lot_id` to `_Sell` and populate it in `LotHelper`

**Files:**
- Modify: `app/engine/lot_helper.py:18-25` (`_Sell` dataclass)
- Modify: `app/engine/lot_helper.py:51-71` (`build_lots_sells`)
- Test: `tests/unit/test_lot_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_lot_engine.py`, after the existing imports:

```python
from app.engine.lot_helper import LotHelper, _Sell

class TestLotHelperSellLotId:
    """_Sell.lot_id is populated from transaction.lot_id."""

    def _make_txn(self, ttype, units, amount_paise, lot_id=None):
        from dataclasses import make_dataclass
        from datetime import date
        from enum import Enum

        class TType(Enum):
            BUY = "BUY"
            SELL = "SELL"

        T = make_dataclass("T", [
            "type", "date", "units", "amount_inr", "lot_id",
            ("id", int, 1),
        ])
        return T(
            type=TType(ttype),
            date=date(2024, 1, 1),
            units=units,
            amount_inr=amount_paise,
            lot_id=lot_id,
        )

    def test_sell_lot_id_populated_from_transaction(self):
        txns = [
            self._make_txn("BUY", 10, -100000, lot_id="lot-buy-1"),
            self._make_txn("SELL", 5, 60000, lot_id="lot-buy-1"),
        ]
        helper = LotHelper(stcg_days=730)
        lots, sells = helper.build_lots_sells(txns)
        assert len(sells) == 1
        assert sells[0].lot_id == "lot-buy-1"

    def test_sell_without_lot_id_is_none(self):
        txns = [
            self._make_txn("BUY", 10, -100000, lot_id="lot-buy-1"),
            self._make_txn("SELL", 5, 60000, lot_id=None),
        ]
        helper = LotHelper(stcg_days=730)
        _, sells = helper.build_lots_sells(txns)
        assert sells[0].lot_id is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_lot_engine.py::TestLotHelperSellLotId -v
```

Expected: FAIL — `_Sell` has no `lot_id` field.

- [ ] **Step 3: Add `lot_id` to `_Sell` dataclass**

In `app/engine/lot_helper.py`, replace the `_Sell` dataclass:

```python
@dataclass
class _Sell:
    date: date
    units: float
    amount_inr: float
    lot_id: Optional[str] = None  # set for specific-lot sells (Fidelity PDF path)
```

- [ ] **Step 4: Populate `lot_id` in `build_lots_sells`**

In `LotHelper.build_lots_sells`, find the `elif ttype in SELL_TYPES` branch (around line 69) and update:

```python
            elif ttype in SELL_TYPES and t.units:
                sells.append(_Sell(
                    date=t.date,
                    units=t.units,
                    amount_inr=abs(t.amount_inr / 100.0),
                    lot_id=t.lot_id,  # None for non-Fidelity SELLs; specific lot_id for Fidelity path
                ))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/unit/test_lot_engine.py::TestLotHelperSellLotId -v
```

Expected: PASS

- [ ] **Step 6: Run full test suite to check no regressions**

```bash
cd backend && uv run pytest tests/unit/test_lot_engine.py -v
```

Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add app/engine/lot_helper.py tests/unit/test_lot_engine.py
git commit -m "feat: add lot_id to _Sell and populate from transaction in LotHelper"
```

---

## Task 3: Add `match_lots` to lot engine

**Files:**
- Modify: `app/engine/lot_engine.py`
- Test: `tests/unit/test_lot_engine.py`

`match_lots` behaves like `match_lots_fifo` but when a sell has `lot_id` set, it consumes from that exact lot instead of FIFO order. `match_lots_fifo` stays unchanged — it's still used by all non-US-stock asset types.

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_lot_engine.py`:

```python
from app.engine.lot_engine import match_lots_fifo  # already imported

# Add to imports at top of file:
# from app.engine.lot_engine import match_lots

class TestMatchLots:
    """match_lots: specific-lot when sell.lot_id set; FIFO fallback when None."""

    def _lot(self, lot_id, buy_date, units, price):
        return FakeLot(
            lot_id=lot_id, asset_id=1,
            buy_date=buy_date, units=units,
            buy_price_per_unit=price,
            buy_amount_inr=units * price,
        )

    def _sell(self, sell_date, units, amount, lot_id=None):
        # FakeSell extended with lot_id
        from dataclasses import dataclass as dc
        @dc
        class FakeSellWithLot:
            date: object
            units: float
            amount_inr: float
            lot_id: object = None
        return FakeSellWithLot(date=sell_date, units=units, amount_inr=amount, lot_id=lot_id)

    def test_specific_lot_match_skips_fifo_order(self):
        """Sell pinned to lot B should consume B even though A is older."""
        lots = [
            self._lot("A", date(2022, 1, 1), 10, 100.0),
            self._lot("B", date(2023, 1, 1), 10, 200.0),
        ]
        sell = self._sell(date(2024, 6, 1), units=5, amount=1200.0, lot_id="B")
        from app.engine.lot_engine import match_lots
        matched = match_lots(lots, [sell], stcg_days=730)
        assert len(matched) == 1
        assert matched[0]["lot_id"] == "B"
        assert matched[0]["units_sold"] == 5.0

    def test_no_lot_id_falls_back_to_fifo(self):
        """Sell with lot_id=None uses FIFO — consumes from A (oldest) first."""
        lots = [
            self._lot("A", date(2022, 1, 1), 10, 100.0),
            self._lot("B", date(2023, 1, 1), 10, 200.0),
        ]
        sell = self._sell(date(2024, 6, 1), units=5, amount=600.0, lot_id=None)
        from app.engine.lot_engine import match_lots
        matched = match_lots(lots, [sell], stcg_days=730)
        assert matched[0]["lot_id"] == "A"

    def test_unknown_lot_id_falls_back_to_fifo(self):
        """Sell with unrecognised lot_id falls back to FIFO, not silent failure."""
        lots = [self._lot("A", date(2022, 1, 1), 10, 100.0)]
        sell = self._sell(date(2024, 6, 1), units=5, amount=600.0, lot_id="NONEXISTENT")
        from app.engine.lot_engine import match_lots
        matched = match_lots(lots, [sell], stcg_days=730)
        assert matched[0]["lot_id"] == "A"

    def test_specific_lot_realised_gain_computed_correctly(self):
        lots = [
            self._lot("A", date(2022, 1, 1), 10, 100.0),  # cost 1000
            self._lot("B", date(2023, 1, 1), 10, 200.0),  # cost 2000
        ]
        sell = self._sell(date(2024, 6, 1), units=10, amount=3000.0, lot_id="B")
        from app.engine.lot_engine import match_lots
        matched = match_lots(lots, [sell], stcg_days=730)
        # proceeds 3000, cost 2000 → gain 1000
        assert matched[0]["realised_gain_inr"] == pytest.approx(1000.0)

    def test_specific_lot_is_short_term_flag(self):
        """Lot bought 6 months ago, stcg_days=730 → is_short_term=True."""
        lots = [self._lot("A", date(2023, 12, 1), 10, 100.0)]
        sell = self._sell(date(2024, 6, 1), units=5, amount=600.0, lot_id="A")
        from app.engine.lot_engine import match_lots
        matched = match_lots(lots, [sell], stcg_days=730)
        assert matched[0]["is_short_term"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/unit/test_lot_engine.py::TestMatchLots -v
```

Expected: FAIL — `match_lots` not defined.

- [ ] **Step 3: Implement `match_lots` in `lot_engine.py`**

Add after `match_lots_fifo` (after line 112):

```python
def match_lots(lots: list, sells: list, stcg_days: int = 365) -> list[dict]:
    """
    Match sell events against buy lots.

    - If sell.lot_id is set and found in lots: specific-lot match (consume from that lot only).
    - If sell.lot_id is None or not found: FIFO fallback (earliest lot first).

    Args:
        lots:      List of lot-like objects (must have .lot_id, .buy_date, .units, etc.)
        sells:     List of sell-like objects (must have .date, .units, .amount_inr, .lot_id).
        stcg_days: Short-term holding threshold in days.

    Returns:
        Same structure as match_lots_fifo.
    """
    import logging
    _log = logging.getLogger(__name__)

    remaining = {lot.lot_id: lot.units for lot in lots}
    lot_index = {lot.lot_id: lot for lot in lots}
    ordered_ids = [lot.lot_id for lot in sorted(lots, key=lambda l: l.buy_date)]

    matches: list[dict] = []

    for sell in sells:
        sell_lot_id = getattr(sell, "lot_id", None)
        units_to_sell = sell.units
        sell_price = sell.amount_inr / sell.units if sell.units > 0 else 0.0

        if sell_lot_id and sell_lot_id in lot_index:
            # Specific-lot path: consume from exactly this lot
            consume_ids = [sell_lot_id]
        else:
            if sell_lot_id and sell_lot_id not in lot_index:
                _log.warning(
                    "match_lots: lot_id %r not found in lots — falling back to FIFO", sell_lot_id
                )
            # FIFO fallback
            consume_ids = ordered_ids

        for lot_id in consume_ids:
            if units_to_sell <= 0:
                break
            avail = remaining.get(lot_id, 0.0)
            if avail <= 0:
                continue

            lot = lot_index[lot_id]
            consumed = min(avail, units_to_sell)
            remaining[lot_id] = avail - consumed
            units_to_sell -= consumed

            cost_basis = lot.buy_price_per_unit * consumed
            proceeds = sell_price * consumed
            realised_gain = proceeds - cost_basis
            holding_days = (sell.date - lot.buy_date).days

            matches.append({
                "lot_id": lot_id,
                "sell_date": sell.date,
                "buy_date": lot.buy_date,
                "units_sold": consumed,
                "units_remaining": remaining[lot_id],
                "buy_price_per_unit": lot.buy_price_per_unit,
                "sell_price_per_unit": sell_price,
                "realised_gain_inr": realised_gain,
                "is_short_term": holding_days < stcg_days,
            })

    return matches
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/unit/test_lot_engine.py::TestMatchLots -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Run full lot engine tests**

```bash
cd backend && uv run pytest tests/unit/test_lot_engine.py -v
```

Expected: All tests pass (existing + new).

- [ ] **Step 6: Commit**

```bash
git add app/engine/lot_engine.py tests/unit/test_lot_engine.py
git commit -m "feat: add match_lots with specific-lot matching and FIFO fallback"
```

---

## Task 4: Wire `match_lots` into `MarketBasedStrategy`

**Files:**
- Modify: `app/services/returns/strategies/market_based.py:12-17` (imports)
- Modify: `app/services/returns/strategies/market_based.py:98` (`_match_and_get_open_lots`)

- [ ] **Step 1: Update import in `market_based.py`**

In `app/services/returns/strategies/market_based.py`, change:

```python
from app.engine.lot_engine import (
    match_lots_fifo,
    compute_gains_summary,
    compute_lot_unrealised,
    GRANDFATHERING_CUTOFF,
)
```

to:

```python
from app.engine.lot_engine import (
    match_lots,
    compute_gains_summary,
    compute_lot_unrealised,
    GRANDFATHERING_CUTOFF,
)
```

- [ ] **Step 2: Replace `match_lots_fifo` call with `match_lots`**

In `_match_and_get_open_lots` (around line 98), change:

```python
        matched = match_lots_fifo(lots, sells, stcg_days=self.stcg_days)
```

to:

```python
        matched = match_lots(lots, sells, stcg_days=self.stcg_days)
```

- [ ] **Step 3: Run existing strategy tests to confirm no regression**

```bash
cd backend && uv run pytest tests/unit/ -v -k "not fidelity"
```

Expected: All existing unit tests pass. (`match_lots` falls back to FIFO when `sell.lot_id is None`, so non-STOCK_US behaviour is unchanged.)

- [ ] **Step 4: Commit**

```bash
git add app/services/returns/strategies/market_based.py
git commit -m "feat: use match_lots in MarketBasedStrategy for specific-lot matching"
```

---

## Task 5: Respect pre-assigned `lot_id` in `import_service.py`

**Files:**
- Modify: `app/services/import_service.py:122`

This lets the post-processor pass BUY and SELL rows with `lot_id` already set without `import_service` overwriting them.

- [ ] **Step 1: Change `lot_id` assignment logic**

In `app/services/import_service.py`, line 122, change:

```python
            lot_id = str(uuid.uuid4()) if txn.txn_type in LOT_TYPES else None
```

to:

```python
            lot_id = txn.lot_id or (str(uuid.uuid4()) if txn.txn_type in LOT_TYPES else None)
```

- [ ] **Step 2: Run tests**

```bash
cd backend && uv run pytest tests/unit/ tests/integration/ -v -k "import"
```

Expected: All import-related tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/services/import_service.py
git commit -m "feat: respect pre-assigned lot_id on ParsedTransaction in import_service"
```

---

## Task 6: Add `IPreCommitProcessor` protocol and wire into orchestrator

**Files:**
- Modify: `app/services/imports/post_processors/base.py`
- Modify: `app/services/imports/orchestrator.py:47-61` (`__init__`)
- Modify: `app/services/imports/orchestrator.py:105-165` (`commit`)

- [ ] **Step 1: Add `IPreCommitProcessor` to `base.py`**

In `app/services/imports/post_processors/base.py`, add after the existing `IPostProcessor` class:

```python
class IPreCommitProcessor(Protocol):
    """
    Runs inside commit() BEFORE the transaction loop.
    Receives the in-memory ImportResult, may add/replace ParsedTransactions.
    Keyed by result.source (not asset_type).
    """
    source: ClassVar[str]

    def process(self, result: "ImportResult", uow: "UnitOfWork") -> "ImportResult":
        """Return modified ImportResult. May expand, replace, or annotate transactions."""
        ...
```

Also add the necessary imports at the top of the file:

```python
from typing import ClassVar, Protocol, TYPE_CHECKING
if TYPE_CHECKING:
    from app.importers.base import ImportResult
    from app.repositories.unit_of_work import UnitOfWork
```

- [ ] **Step 2: Add `pre_commit_processors` to `ImportOrchestrator.__init__`**

In `app/services/imports/orchestrator.py`, update `__init__` to accept and store the new registry:

```python
    def __init__(
        self,
        uow_factory,
        pipeline: ImportPipeline,
        preview_store: PreviewStore,
        post_processors: list,
        event_bus: IEventBus,
        pre_commit_processors: list | None = None,  # NEW — optional for backwards compat
    ):
        self._uow_factory = uow_factory
        self._pipeline = pipeline
        self._store = preview_store
        self._processors: dict[str, IPostProcessor] = {
            at: p for p in post_processors for at in p.asset_types
        }
        self._pre_commit_processors: dict[str, object] = {
            p.source: p for p in (pre_commit_processors or [])
        }
        self._bus = event_bus
```

- [ ] **Step 3: Call pre-commit processor at start of `commit()`**

In `app/services/imports/orchestrator.py`, in `commit()`, after loading `result` from the store (after line 110) and before the transaction loop (line 116), add:

```python
        # Run pre-commit processor (e.g. Fidelity lot resolution) before any DB writes
        pre_processor = self._pre_commit_processors.get(result.source)
        if pre_processor:
            result = pre_processor.process(result, uow)
```

Note: this call must be *inside* the `with self._uow_factory() as uow:` block so the processor has a live session.

- [ ] **Step 4: Run existing orchestrator/import tests**

```bash
cd backend && uv run pytest tests/integration/ -v
```

Expected: All integration tests pass (`pre_commit_processors` defaults to `[]`, no change to existing behaviour).

- [ ] **Step 5: Commit**

```bash
git add app/services/imports/post_processors/base.py app/services/imports/orchestrator.py
git commit -m "feat: add IPreCommitProcessor protocol and pre-commit hook in ImportOrchestrator"
```

---

## Task 7: Refactor `FidelityPDFImporter` to emit SELL-only

**Files:**
- Modify: `app/importers/fidelity_pdf_importer.py`
- Test: `tests/unit/test_fidelity_pdf_importer.py`

- [ ] **Step 1: Write failing tests for new SELL-only behaviour**

Replace the contents of `tests/unit/test_fidelity_pdf_importer.py` with:

```python
import pytest
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_sample_pdf_bytes() -> bytes:
    path = FIXTURES / "fidelity_sale_sample.pdf"
    if path.exists():
        return path.read_bytes()
    pytest.skip("fidelity_sale_sample.pdf fixture not available")


class TestFidelityPDFImporter:
    RATES = {"2025-03": 86.0, "2025-09": 84.5}

    def _parse(self):
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = _make_sample_pdf_bytes()
        return FidelityPDFImporter(exchange_rates=self.RATES).parse(data)

    # --- Structural ---

    def test_parse_returns_one_transaction_per_sale_row(self):
        """Each PDF sale row now produces exactly 1 SELL (no synthetic BUY)."""
        result = self._parse()
        # fixture has 2 sale rows → 2 transactions
        assert len(result.transactions) == 2
        assert result.errors == []

    def test_all_transactions_are_sells(self):
        result = self._parse()
        for t in result.transactions:
            assert t.txn_type == "SELL"

    def test_no_buy_transactions_emitted(self):
        result = self._parse()
        assert all(t.txn_type != "BUY" for t in result.transactions)

    # --- Sell transaction fields ---

    def test_sell_asset_type_and_name(self):
        t = self._parse().transactions[0]
        assert t.asset_type == "STOCK_US"
        assert t.asset_name == "AMZN"
        assert t.asset_identifier == "AMZN"

    def test_sell_date(self):
        t = self._parse().transactions[0]
        assert t.date == date(2025, 3, 17)

    def test_sell_units(self):
        t = self._parse().transactions[0]
        assert t.units == pytest.approx(36.0)

    def test_sell_amount_inr_positive_inflow(self):
        # proceeds = $7,070.24, rate = 86.0
        t = self._parse().transactions[0]
        assert t.amount_inr == pytest.approx(7070.24 * 86.0, rel=1e-4)
        assert t.amount_inr > 0

    def test_sell_forex_rate(self):
        t = self._parse().transactions[0]
        assert t.forex_rate == pytest.approx(86.0)

    def test_sell_lot_id_is_none(self):
        """lot_id is None — FidelityPreCommitProcessor will assign it."""
        t = self._parse().transactions[0]
        assert t.lot_id is None

    # --- Acquisition metadata fields (NEW) ---

    def test_sell_acquisition_date_populated(self):
        t = self._parse().transactions[0]
        assert t.acquisition_date == date(2025, 3, 17)  # same date = sell-to-cover fixture

    def test_sell_acquisition_cost_inr_populated(self):
        # cost = $7,070.44, rate = 86.0 → 607,857.84 INR
        t = self._parse().transactions[0]
        assert t.acquisition_cost == pytest.approx(7070.44 * 86.0, rel=1e-4)
        assert t.acquisition_cost > 0

    def test_sell_acquisition_forex_rate_populated(self):
        t = self._parse().transactions[0]
        assert t.acquisition_forex_rate == pytest.approx(86.0)

    # --- txn_id stability ---

    def test_sell_txn_id_is_stable(self):
        """txn_id scheme unchanged: hash(ticker|date_sold|date_acquired|qty)."""
        r1 = self._parse()
        r2 = self._parse()
        assert r1.transactions[0].txn_id == r2.transactions[0].txn_id

    def test_sell_txn_id_not_empty(self):
        t = self._parse().transactions[0]
        assert t.txn_id and len(t.txn_id) > 10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/unit/test_fidelity_pdf_importer.py -v
```

Expected: Multiple failures — `test_parse_returns_one_transaction_per_sale_row` fails (currently returns 4 for 2 sale rows), acquisition field tests fail (fields don't exist yet on emitted transactions).

- [ ] **Step 3: Refactor `_parse_match` to return a single SELL**

Replace `_parse_match` in `app/importers/fidelity_pdf_importer.py`:

```python
    def _parse_match(self, m: re.Match, ticker: str) -> ParsedTransaction:
        date_sold_str, date_acq_str = m.group(1), m.group(2)
        quantity_str, cost_str, proceeds_str = m.group(3), m.group(4), m.group(5)

        date_sold = datetime.strptime(date_sold_str, "%b-%d-%Y").date()
        date_acquired = datetime.strptime(date_acq_str, "%b-%d-%Y").date()
        quantity = float(quantity_str.replace(",", ""))
        proceeds_usd = float(proceeds_str.replace(",", ""))
        cost_usd = float(cost_str.replace(",", "")) if cost_str else 0.0

        date_sold_month_year = date_sold.strftime("%Y-%m")
        date_acquired_month_year = date_acquired.strftime("%Y-%m")
        date_sold_forex_rate = self.exchange_rates.get(date_sold_month_year)
        date_acquired_forex_rate = self.exchange_rates.get(date_acquired_month_year)

        if date_sold_forex_rate is None and self.exchange_rates:
            raise ValueError(f"No exchange rate provided for {date_sold_month_year}")
        if date_acquired_forex_rate is None and self.exchange_rates:
            raise ValueError(f"No exchange rate provided for {date_acquired_month_year}")

        sale_amount_inr = proceeds_usd * date_sold_forex_rate if date_sold_forex_rate else 0.0
        acquire_amount_inr = cost_usd * date_acquired_forex_rate if date_acquired_forex_rate else 0.0

        sale_price_per_unit_usd = round(proceeds_usd / quantity, 4) if quantity else 0.0
        sell_txn_id = self._make_txn_id(ticker, date_sold.isoformat(), date_acquired.isoformat(), quantity, False)

        return ParsedTransaction(
            source="fidelity_sale",
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type="SELL",
            date=date_sold,
            units=quantity,
            price_per_unit=sale_price_per_unit_usd,
            forex_rate=date_sold_forex_rate,
            amount_inr=sale_amount_inr,
            txn_id=sell_txn_id,
            lot_id=None,                                   # FidelityPreCommitProcessor assigns this
            acquisition_date=date_acquired,
            acquisition_cost=acquire_amount_inr,
            acquisition_forex_rate=date_acquired_forex_rate,
            notes=f"Acquired {date_acquired.isoformat()}",
        )
```

- [ ] **Step 4: Update `parse()` to append one transaction per row**

In `parse()`, change the block that calls `_parse_match`:

```python
                        if in_sales and ticker:
                            m = _SALE_ROW_RE.search(line)
                            if m:
                                try:
                                    sell_txn = self._parse_match(m, ticker)
                                    result.transactions.append(sell_txn)
                                except ValueError as e:
                                    print(f"ERROR parsing row for ticker {ticker}: {e}")
                                    result.errors.append(f"Row parse error: {e}")
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/unit/test_fidelity_pdf_importer.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/importers/fidelity_pdf_importer.py tests/unit/test_fidelity_pdf_importer.py
git commit -m "feat: refactor FidelityPDFImporter to emit SELL-only with acquisition metadata"
```

---

## Task 8: Implement `FidelityPreCommitProcessor`

**Files:**
- Create: `app/services/imports/post_processors/fidelity.py`
- Modify: `app/services/imports/post_processors/__init__.py`
- Test: `tests/unit/test_fidelity_pre_commit_processor.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_fidelity_pre_commit_processor.py`:

```python
"""
Unit tests for FidelityPreCommitProcessor.

Uses a fake UoW with in-memory transaction/asset repos — no DB needed.
"""
import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.importers.base import ImportResult, ParsedTransaction


# ---------------------------------------------------------------------------
# Helpers to build ParsedTransaction (SELL with acquisition fields)
# ---------------------------------------------------------------------------

def _make_sell(
    ticker: str,
    date_sold: date,
    date_acquired: date,
    units: float,
    proceeds_inr: float,
    cost_inr: float,
    acq_forex: float = 85.0,
    lot_id: Optional[str] = None,
) -> ParsedTransaction:
    raw = f"fidelity_sale|{ticker}|{date_sold.isoformat()}|{date_acquired.isoformat()}|{round(units * 10000)}"
    txn_id = "fidelity_sale_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    return ParsedTransaction(
        source="fidelity_sale",
        asset_name=ticker,
        asset_identifier=ticker,
        asset_type="STOCK_US",
        txn_type="SELL",
        date=date_sold,
        units=units,
        amount_inr=proceeds_inr,
        acquisition_date=date_acquired,
        acquisition_cost=cost_inr,
        acquisition_forex_rate=acq_forex,
        txn_id=txn_id,
        lot_id=lot_id,
    )


# ---------------------------------------------------------------------------
# Fake UoW / repos
# ---------------------------------------------------------------------------

@dataclass
class FakeTransaction:
    id: int
    type: object           # string or enum-like with .value
    date: date
    units: float
    amount_inr: int        # paise
    lot_id: Optional[str]
    txn_id: str = ""


@dataclass
class FakeAsset:
    id: int
    identifier: str


class FakeTransactionRepo:
    def __init__(self, txns: list[FakeTransaction]):
        self._txns = txns

    def list_by_asset(self, asset_id: int) -> list[FakeTransaction]:
        return self._txns

    def get_by_txn_id(self, txn_id: str):
        return None


class FakeAssetRepo:
    def __init__(self, assets: list[FakeAsset]):
        self._assets = assets

    def get_by_identifier(self, identifier: str) -> Optional[FakeAsset]:
        return next((a for a in self._assets if a.identifier == identifier), None)


class FakeUoW:
    def __init__(self, assets=None, txns=None):
        self.assets = FakeAssetRepo(assets or [])
        self.transactions = FakeTransactionRepo(txns or [])


def _make_buy_txn(lot_id: str, buy_date: date, units: float, asset_id: int = 1) -> FakeTransaction:
    from enum import Enum
    class TType(Enum):
        BUY = "BUY"
        VEST = "VEST"
    return FakeTransaction(
        id=1, type=TType.BUY,
        date=buy_date, units=units,
        amount_inr=-int(units * 10000 * 100),
        lot_id=lot_id,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFidelityPreCommitProcessor:
    def _processor(self):
        from app.services.imports.post_processors.fidelity import FidelityPreCommitProcessor
        return FidelityPreCommitProcessor()

    def _result(self, txns: list) -> ImportResult:
        return ImportResult(source="fidelity_sale", transactions=txns)

    # --- Asset not found ---

    def test_sell_passed_through_unchanged_when_asset_not_found(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 10, 1000.0, 800.0)
        uow = FakeUoW(assets=[])   # no AMZN asset in DB
        result = self._processor().process(self._result([sell]), uow)
        assert len(result.transactions) == 1
        assert result.transactions[0].lot_id is None

    # --- Lot found: single lot, exact match ---

    def test_single_lot_found_sell_gets_lot_id(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 10, 1000.0, 800.0)
        buy = _make_buy_txn("lot-uuid-1", date(2023, 1, 1), 20)
        uow = FakeUoW(
            assets=[FakeAsset(id=1, identifier="AMZN")],
            txns=[buy],
        )
        result = self._processor().process(self._result([sell]), uow)
        assert len(result.transactions) == 1
        assert result.transactions[0].lot_id == "lot-uuid-1"
        assert result.transactions[0].units == pytest.approx(10.0)

    # --- Two lots on same date: SELL splits into 2 partials ---

    def test_two_same_date_lots_sell_splits_into_partials(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 36, 3600.0, 2800.0)
        lot_a = _make_buy_txn("lot-a", date(2023, 1, 1), 20)
        lot_a.id = 1
        lot_b = _make_buy_txn("lot-b", date(2023, 1, 1), 16)
        lot_b.id = 2
        uow = FakeUoW(
            assets=[FakeAsset(id=1, identifier="AMZN")],
            txns=[lot_a, lot_b],
        )
        result = self._processor().process(self._result([sell]), uow)
        assert len(result.transactions) == 2
        lot_ids = {t.lot_id for t in result.transactions}
        assert lot_ids == {"lot-a", "lot-b"}
        total_units = sum(t.units for t in result.transactions)
        assert total_units == pytest.approx(36.0)

    def test_partial_sells_have_proportional_amounts(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 36, 3600.0, 2800.0)
        lot_a = _make_buy_txn("lot-a", date(2023, 1, 1), 20); lot_a.id = 1
        lot_b = _make_buy_txn("lot-b", date(2023, 1, 1), 16); lot_b.id = 2
        uow = FakeUoW(
            assets=[FakeAsset(id=1, identifier="AMZN")],
            txns=[lot_a, lot_b],
        )
        result = self._processor().process(self._result([sell]), uow)
        price_per_unit = 3600.0 / 36.0
        for t in result.transactions:
            assert t.amount_inr == pytest.approx(price_per_unit * t.units, rel=1e-4)

    def test_partial_sell_txn_ids_are_stable(self):
        """Re-running produces the same txn_ids."""
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 36, 3600.0, 2800.0)
        lot_a = _make_buy_txn("lot-a", date(2023, 1, 1), 20); lot_a.id = 1
        lot_b = _make_buy_txn("lot-b", date(2023, 1, 1), 16); lot_b.id = 2
        uow = FakeUoW(
            assets=[FakeAsset(id=1, identifier="AMZN")],
            txns=[lot_a, lot_b],
        )
        r1 = self._processor().process(self._result([sell]), uow)
        r2 = self._processor().process(self._result([sell]), uow)
        ids1 = sorted(t.txn_id for t in r1.transactions)
        ids2 = sorted(t.txn_id for t in r2.transactions)
        assert ids1 == ids2

    # --- Sell-to-cover: date_acquired == date_sold, no existing lot ---

    def test_sell_to_cover_creates_buy_sell_pair(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2024, 3, 1), 10, 1000.0, 800.0, acq_forex=84.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        types = {t.txn_type for t in result.transactions}
        assert types == {"BUY", "SELL"}

    def test_sell_to_cover_buy_and_sell_share_lot_id(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2024, 3, 1), 10, 1000.0, 800.0, acq_forex=84.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        buy = next(t for t in result.transactions if t.txn_type == "BUY")
        sell_out = next(t for t in result.transactions if t.txn_type == "SELL")
        assert buy.lot_id == sell_out.lot_id
        assert buy.lot_id is not None

    def test_sell_to_cover_buy_price_per_unit_in_usd(self):
        # cost_inr=840.0, units=10, acq_forex=84.0 → price_per_unit = 840/(10*84) = 1.0 USD
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2024, 3, 1), 10, 1000.0, 840.0, acq_forex=84.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        buy = next(t for t in result.transactions if t.txn_type == "BUY")
        assert buy.price_per_unit == pytest.approx(1.0)

    def test_sell_to_cover_buy_amount_inr_is_negative(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2024, 3, 1), 10, 1000.0, 840.0, acq_forex=84.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        buy = next(t for t in result.transactions if t.txn_type == "BUY")
        assert buy.amount_inr < 0

    # --- Orphaned sale (no matching lot, dates differ) ---

    def test_orphaned_sale_creates_buy_sell_pair(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2021, 6, 1), 5, 500.0, 400.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        types = {t.txn_type for t in result.transactions}
        assert types == {"BUY", "SELL"}

    def test_orphaned_sale_buy_txn_id_is_stable(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2021, 6, 1), 5, 500.0, 400.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        r1 = self._processor().process(self._result([sell]), uow)
        r2 = self._processor().process(self._result([sell]), uow)
        buy1 = next(t for t in r1.transactions if t.txn_type == "BUY")
        buy2 = next(t for t in r2.transactions if t.txn_type == "BUY")
        assert buy1.txn_id == buy2.txn_id

    # --- Non-SELL transactions pass through unchanged ---

    def test_non_sell_transactions_pass_through(self):
        other = ParsedTransaction(
            source="fidelity_sale",
            asset_name="AMZN", asset_identifier="AMZN",
            asset_type="STOCK_US", txn_type="DIVIDEND",
            date=date(2024, 1, 1), amount_inr=100.0,
        )
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([other]), uow)
        assert len(result.transactions) == 1
        assert result.transactions[0].txn_type == "DIVIDEND"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/unit/test_fidelity_pre_commit_processor.py -v
```

Expected: FAIL — `FidelityPreCommitProcessor` doesn't exist yet.

- [ ] **Step 3: Implement `FidelityPreCommitProcessor`**

Create `app/services/imports/post_processors/fidelity.py`:

```python
"""
FidelityPreCommitProcessor — resolves lot_id on SELL transactions from Fidelity PDF imports.

Runs inside ImportOrchestrator.commit() before the transaction loop.
For each SELL with acquisition_date:
  - Queries DB for BUY/VEST transactions on that date for the asset (FIFO among same-date lots)
  - Splits the SELL into N partial-SELL transactions, each pinned to a specific lot_id
  - If no lots found and acquisition_date == date_sold: sell-to-cover → BUY+SELL pair
  - If no lots found and dates differ: orphaned sale → synthetic BUY + SELL pair
"""
import hashlib
import logging
import uuid
from dataclasses import replace
from datetime import date
from typing import ClassVar, Optional

from app.importers.base import ImportResult, ParsedTransaction

logger = logging.getLogger(__name__)

_LOT_TYPES = {"BUY", "VEST"}


class FidelityPreCommitProcessor:
    source: ClassVar[str] = "fidelity_sale"

    def process(self, result: ImportResult, uow) -> ImportResult:
        """Return modified ImportResult with SELL transactions resolved to specific lots."""
        new_transactions: list[ParsedTransaction] = []

        for txn in result.transactions:
            if txn.txn_type != "SELL" or txn.acquisition_date is None:
                new_transactions.append(txn)
                continue

            expanded = self._resolve_sell(txn, uow)
            new_transactions.extend(expanded)

        result.transactions = new_transactions
        return result

    def _resolve_sell(self, sell: ParsedTransaction, uow) -> list[ParsedTransaction]:
        # Step 1: find asset in DB
        asset = uow.assets.get_by_identifier(sell.asset_identifier)
        if asset is None:
            logger.warning(
                "FidelityPreCommitProcessor: no asset found for %r — passing SELL through",
                sell.asset_identifier,
            )
            return [sell]

        # Step 2: find same-date BUY/VEST lots ordered by id (FIFO among same date)
        all_txns = uow.transactions.list_by_asset(asset.id)
        same_date_lots = sorted(
            [
                t for t in all_txns
                if t.date == sell.acquisition_date
                and self._txn_type_str(t) in _LOT_TYPES
                and t.lot_id
            ],
            key=lambda t: t.id,
        )

        if same_date_lots:
            return self._split_sell(sell, same_date_lots)

        # Step 3: no lots found — sell-to-cover or orphaned
        return self._create_buy_sell_pair(sell)

    def _split_sell(self, sell: ParsedTransaction, lots: list) -> list[ParsedTransaction]:
        """FIFO split of sell across same-date lots."""
        remaining = sell.units
        sell_price_per_unit = sell.amount_inr / sell.units if sell.units else 0.0
        partials: list[ParsedTransaction] = []

        for lot in lots:
            if remaining <= 0:
                break
            consumed = min(lot.units, remaining)
            remaining -= consumed

            partial_txn_id = self._partial_txn_id(sell.txn_id, lot.lot_id)
            partials.append(replace(
                sell,
                units=consumed,
                amount_inr=round(sell_price_per_unit * consumed, 4),
                lot_id=lot.lot_id,
                txn_id=partial_txn_id,
            ))

        if remaining > 0:
            logger.warning(
                "FidelityPreCommitProcessor: %s units of %r on %s unmatched by same-date lots — creating fallback buy",
                remaining, sell.asset_identifier, sell.acquisition_date,
            )
            gap_sell = replace(sell, units=remaining, amount_inr=round(sell_price_per_unit * remaining, 4))
            partials.extend(self._create_buy_sell_pair(gap_sell))

        return partials

    def _create_buy_sell_pair(self, sell: ParsedTransaction) -> list[ParsedTransaction]:
        """Create a synthetic BUY + the SELL, sharing a fresh lot_id."""
        new_lot_id = str(uuid.uuid4())
        is_stc = sell.acquisition_date == sell.date
        prefix = "fidelity_stc_buy" if is_stc else "fidelity_orphan_buy"
        qty_int = round((sell.units or 0) * 10000)
        raw = f"{prefix}|{sell.asset_identifier}|{sell.acquisition_date.isoformat()}|{qty_int}"
        buy_txn_id = prefix + "_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        acq_cost = sell.acquisition_cost or 0.0
        acq_forex = sell.acquisition_forex_rate or 1.0
        units = sell.units or 0.0
        price_per_unit_usd = (acq_cost / acq_forex / units) if (acq_forex and units) else 0.0

        if not is_stc:
            logger.warning(
                "FidelityPreCommitProcessor: no matching buy found for %r acquired %s — synthetic lot created",
                sell.asset_identifier, sell.acquisition_date,
            )

        buy = replace(
            sell,
            txn_type="BUY",
            date=sell.acquisition_date,
            amount_inr=-acq_cost,
            price_per_unit=price_per_unit_usd,
            forex_rate=sell.acquisition_forex_rate,
            lot_id=new_lot_id,
            txn_id=buy_txn_id,
            notes=f"Synthetic lot ({'sell-to-cover' if is_stc else 'orphaned sale'})",
            acquisition_date=None,
            acquisition_cost=None,
            acquisition_forex_rate=None,
        )
        sell_out = replace(sell, lot_id=new_lot_id)
        return [buy, sell_out]

    @staticmethod
    def _txn_type_str(txn) -> str:
        t = getattr(txn, "type", None)
        if t is None:
            return str(getattr(txn, "txn_type", ""))
        return t.value if hasattr(t, "value") else str(t)

    @staticmethod
    def _partial_txn_id(original_txn_id: str, lot_id: str) -> str:
        raw = f"fidelity_partial|{original_txn_id}|{lot_id}"
        return "fidelity_partial_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
```

- [ ] **Step 4: Register `FidelityPreCommitProcessor`**

In `app/services/imports/post_processors/__init__.py`, add a single line:

```python
from app.services.imports.post_processors.fidelity import FidelityPreCommitProcessor
```

- [ ] **Step 5: Run unit tests**

```bash
cd backend && uv run pytest tests/unit/test_fidelity_pre_commit_processor.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/imports/post_processors/fidelity.py \
        app/services/imports/post_processors/__init__.py \
        tests/unit/test_fidelity_pre_commit_processor.py
git commit -m "feat: implement FidelityPreCommitProcessor for specific-lot SELL resolution"
```

---

## Task 9: Inject `FidelityPreCommitProcessor` into `ImportOrchestrator`

**Files:**
- Modify: `app/api/dependencies.py`

- [ ] **Step 1: Add import and inject**

In `app/api/dependencies.py`, add to imports (around line 22-26):

```python
from app.services.imports.post_processors.fidelity import FidelityPreCommitProcessor
```

Then in `get_import_orchestrator`, update the `ImportOrchestrator(...)` call to add `pre_commit_processors`:

```python
    return ImportOrchestrator(
        uow_factory=uow_factory,
        pipeline=pipeline,
        preview_store=_preview_store,
        post_processors=[StockPostProcessor(), MFPostProcessor(), PPFPostProcessor(), EPFPostProcessor()],
        pre_commit_processors=[FidelityPreCommitProcessor()],   # NEW
        event_bus=_event_bus,
    )
```

- [ ] **Step 2: Run full test suite**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/api/dependencies.py
git commit -m "feat: inject FidelityPreCommitProcessor into ImportOrchestrator"
```

---

## Task 10: Integration tests

**Files:**
- Modify: `tests/integration/test_fidelity_imports.py`

- [ ] **Step 1: Write integration tests**

Add to `tests/integration/test_fidelity_imports.py` (or create it if it doesn't exist):

```python
"""
Integration tests for Fidelity PDF lot matching.

These tests use the full ImportOrchestrator pipeline with a real SQLite DB
to verify that:
  1. After importing Fidelity CSV (BUY lots), a subsequent PDF import resolves
     SELL transactions to the correct lot_ids.
  2. Re-importing the same PDF produces no new rows (idempotent).
  3. Sell-to-cover rows create a BUY+SELL pair sharing a lot_id.
"""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import Transaction, TransactionType
from app.importers.base import ImportResult, ParsedTransaction
from app.repositories.unit_of_work import UnitOfWork
from app.services.imports.post_processors.fidelity import FidelityPreCommitProcessor


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def uow(db_session):
    return UnitOfWork(db_session)


def _seed_asset_and_buy(uow, ticker: str, lot_id: str, buy_date: date, units: float) -> Asset:
    """Create an AMZN asset and a BUY transaction with a specific lot_id."""
    asset = uow.assets.create(
        name=ticker,
        identifier=ticker,
        asset_type=AssetType.STOCK_US,
        asset_class=AssetClass.EQUITY,
        currency="USD",
        is_active=True,
    )
    uow.transactions.create(
        asset_id=asset.id,
        txn_id=f"seed-buy-{lot_id}",
        type=TransactionType.BUY,
        date=buy_date,
        units=units,
        price_per_unit=100.0,
        forex_rate=83.0,
        amount_inr=-int(units * 100.0 * 83.0 * 100),
        charges_inr=0,
        lot_id=lot_id,
        notes="seeded",
    )
    return asset


def _make_sell_txn(ticker, date_sold, date_acquired, units, proceeds_inr, cost_inr, acq_forex=83.0):
    import hashlib
    qty_int = round(units * 10000)
    raw = f"fidelity_sale|{ticker}|{date_sold.isoformat()}|{date_acquired.isoformat()}|{qty_int}"
    txn_id = "fidelity_sale_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    return ParsedTransaction(
        source="fidelity_sale",
        asset_name=ticker, asset_identifier=ticker,
        asset_type="STOCK_US", txn_type="SELL",
        date=date_sold, units=units,
        amount_inr=proceeds_inr,
        acquisition_date=date_acquired,
        acquisition_cost=cost_inr,
        acquisition_forex_rate=acq_forex,
        txn_id=txn_id,
    )


class TestFidelityLotResolutionIntegration:

    def test_sell_resolves_to_existing_lot_id(self, uow):
        """PDF SELL for a ticker already in DB gets the correct lot_id."""
        lot_id = "test-lot-uuid-1"
        _seed_asset_and_buy(uow, "AMZN", lot_id, date(2023, 1, 15), 50.0)

        sell = _make_sell_txn("AMZN", date(2024, 3, 1), date(2023, 1, 15), 10, 1000.0, 800.0)
        result = ImportResult(source="fidelity_sale", transactions=[sell])
        processor = FidelityPreCommitProcessor()
        out = processor.process(result, uow)

        assert len(out.transactions) == 1
        assert out.transactions[0].lot_id == lot_id
        assert out.transactions[0].txn_type == "SELL"

    def test_sell_to_cover_creates_buy_sell_pair(self, uow):
        """When date_acquired == date_sold and no lot found, BUY+SELL pair is created."""
        # No asset or buy in DB
        sell = _make_sell_txn("MSFT", date(2024, 3, 1), date(2024, 3, 1), 5, 500.0, 450.0)
        result = ImportResult(source="fidelity_sale", transactions=[sell])
        processor = FidelityPreCommitProcessor()
        out = processor.process(result, uow)

        types = {t.txn_type for t in out.transactions}
        assert types == {"BUY", "SELL"}
        buy = next(t for t in out.transactions if t.txn_type == "BUY")
        sell_out = next(t for t in out.transactions if t.txn_type == "SELL")
        assert buy.lot_id == sell_out.lot_id

    def test_reprocess_produces_same_partial_txn_ids(self, uow):
        """Running the processor twice on the same sell produces identical txn_ids."""
        lot_id = "test-lot-uuid-2"
        _seed_asset_and_buy(uow, "AMZN", lot_id, date(2023, 6, 1), 100.0)

        sell = _make_sell_txn("AMZN", date(2024, 6, 1), date(2023, 6, 1), 20, 2000.0, 1600.0)
        processor = FidelityPreCommitProcessor()

        r1 = processor.process(ImportResult(source="fidelity_sale", transactions=[sell]), uow)
        r2 = processor.process(ImportResult(source="fidelity_sale", transactions=[sell]), uow)

        assert r1.transactions[0].txn_id == r2.transactions[0].txn_id

    def test_split_across_two_same_date_lots(self, uow):
        """36 shares sold, split across two lots of 20 and 16 bought on same date."""
        _seed_asset_and_buy(uow, "AMZN", "lot-a", date(2023, 3, 15), 20.0)
        _seed_asset_and_buy(uow, "AMZN", "lot-b", date(2023, 3, 15), 16.0)

        sell = _make_sell_txn("AMZN", date(2024, 3, 1), date(2023, 3, 15), 36, 3600.0, 2800.0)
        result = ImportResult(source="fidelity_sale", transactions=[sell])
        out = FidelityPreCommitProcessor().process(result, uow)

        assert len(out.transactions) == 2
        assert sum(t.units for t in out.transactions) == pytest.approx(36.0)
        lot_ids = {t.lot_id for t in out.transactions}
        assert lot_ids == {"lot-a", "lot-b"}
```

- [ ] **Step 2: Run integration tests**

```bash
cd backend && uv run pytest tests/integration/test_fidelity_imports.py -v
```

Expected: All 4 integration tests pass.

- [ ] **Step 3: Run full test suite**

```bash
cd backend && uv run pytest tests/ --tb=short
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_fidelity_imports.py
git commit -m "test: add integration tests for Fidelity lot matching pipeline"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] `ParsedTransaction` gets 3 acquisition fields — Task 1
- [x] `_Sell.lot_id` populated — Task 2
- [x] `match_lots` with specific-lot + FIFO fallback — Task 3
- [x] `MarketBasedStrategy` uses `match_lots` — Task 4
- [x] `import_service.py` respects pre-assigned `lot_id` — Task 5
- [x] `IPreCommitProcessor` protocol — Task 6
- [x] Orchestrator `pre_commit_processors` registry — Task 6
- [x] `FidelityPDFImporter` emits SELL-only — Task 7
- [x] `FidelityPreCommitProcessor` lot resolution — Task 8
- [x] `dependencies.py` injection — Task 9
- [x] Integration tests — Task 10

**No placeholders found.**

**Type consistency:**
- `FidelityPreCommitProcessor.source = "fidelity_sale"` matches importer's `source = "fidelity_sale"`
- `IPreCommitProcessor.process(result, uow) -> ImportResult` matches orchestrator call signature
- `_partial_txn_id` used consistently in both implementation and test assertions
- `_Sell.lot_id` field name matches usage in `match_lots` (`getattr(sell, "lot_id", None)`)

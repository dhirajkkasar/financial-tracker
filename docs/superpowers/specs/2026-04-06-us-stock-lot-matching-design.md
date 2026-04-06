# US Stock Specific Lot Matching — Design Spec

**Date:** 2026-04-06  
**Status:** Approved  
**Scope:** Accurate realized gain/loss computation for STOCK_US by matching Fidelity PDF sale rows to their exact source lots instead of assuming FIFO.

---

## Problem

The lot engine uses FIFO for all asset types. For Indian stocks and MFs, FIFO is mandated by tax rules — correct. For US stocks (`STOCK_US`), users can sell any specific lot at Fidelity/Schwab. The Fidelity PDF includes `Date acquired` and `Quantity` per sale row, which uniquely identifies which buy lot was sold. The current engine ignores this, producing incorrect STCG/LTCG splits when the user did not sell the oldest lot.

---

## Chosen Approach

**Post-processor with SELL splitting (Approach A):**

- `FidelityPDFImporter` emits SELL-only transactions (no synthetic BUY), with acquisition metadata attached.
- A new `FidelityPostProcessor` runs after parse, queries the DB for matching BUY/VEST lots by `date_acquired`, and splits each SELL into N partial-SELL transactions — one per consumed lot.
- Each partial SELL carries the `lot_id` of the matched BUY/VEST row.
- The lot engine gets a `match_lots` function that does specific-lot matching when `lot_id` is set on a SELL, falling back to FIFO otherwise.

This keeps the engine simple (no anchor/overflow logic), puts complexity where DB access is available (post-processor), and makes each DB SELL record have clean 1:1 lot provenance.

---

## Section 1 — Data Model Changes

### `ParsedTransaction` (`app/importers/base.py`)

Add three optional fields (import pipeline only — not persisted directly):

```python
acquisition_date: Optional[date] = None       # date_acquired from Fidelity PDF
acquisition_cost: Optional[float] = None      # cost basis in INR (cost_usd * acquisition_forex_rate)
acquisition_forex_rate: Optional[float] = None # USD/INR rate at acquisition date
```

### `_Sell` dataclass (`app/engine/lot_helper.py`)

```python
@dataclass
class _Sell:
    date: date
    units: float
    amount_inr: float
    lot_id: Optional[str] = None   # NEW — populated from t.lot_id for SELL-type transactions
```

`LotHelper.build_lots_sells` populates `lot_id` from `t.lot_id` when building SELL entries.

### `import_service.py` — lot_id assignment

Change unconditional UUID generation to respect pre-assigned `lot_id`:

```python
# Before:
lot_id = str(uuid.uuid4()) if txn.txn_type in LOT_TYPES else None

# After:
lot_id = txn.lot_id or (str(uuid.uuid4()) if txn.txn_type in LOT_TYPES else None)
```

This allows the post-processor to pass pre-assigned `lot_id`s on both BUY and SELL rows without overwriting them.

No DB migration required — `lot_id` column is already `nullable=True` on all transaction types.

---

## Section 2 — FidelityPDFImporter Refactor

`_parse_match` stops creating a `buy_txn`. It returns a single SELL `ParsedTransaction`:

```python
def _parse_match(self, m, ticker) -> ParsedTransaction:
    # parse dates, quantity, costs as today...

    sell_txn = ParsedTransaction(
        source="fidelity_sale",
        asset_name=ticker,
        asset_identifier=ticker,
        asset_type="STOCK_US",
        txn_type="SELL",
        date=date_sold,
        units=quantity,
        amount_inr=sale_amount_inr,             # proceeds in INR
        price_per_unit=sale_price_per_unit_usd,
        forex_rate=date_sold_forex_rate,
        txn_id=self._make_txn_id(...),          # unchanged: hash(ticker|date_sold|date_acquired|qty)
        lot_id=None,                             # post-processor fills this
        acquisition_date=date_acquired,          # NEW
        acquisition_cost=acquire_amount_inr,     # NEW: cost_usd * acquisition_forex_rate
        acquisition_forex_rate=date_acquired_forex_rate,  # NEW
        notes=f"Acquired {date_acquired.isoformat()}",
    )
    return sell_txn
```

`parse()` appends one transaction per sale row instead of two. The importer no longer owns any BUY creation.

`txn_id` for the original SELL is unchanged: `hash(ticker|date_sold|date_acquired|quantity)` — stable across re-imports.

---

## Section 3 — FidelityPreCommitProcessor

### Why a new protocol

The existing `IPostProcessor` runs **after** transactions are persisted (called with the committed `asset` object). Our processor needs to run **before** the transaction loop to expand/replace `result.transactions` in memory. This requires a distinct protocol:

```python
# app/services/imports/post_processors/base.py — add alongside IPostProcessor
class IPreCommitProcessor(Protocol):
    source: ClassVar[str]   # keyed by import source, not asset_type

    def process(self, result: ImportResult, uow: UnitOfWork) -> ImportResult:
        """Called in commit() before the transaction loop. Returns modified ImportResult."""
        ...
```

The orchestrator gains a `pre_commit_processors: dict[str, IPreCommitProcessor]` registry. At the start of `commit()`, before the transaction loop:

```python
pre_processor = self._pre_commit_processors.get(result.source)
if pre_processor:
    result = pre_processor.process(result, uow)
```

**Re-import idempotency note:** The preview step stores the original (un-split) SELL transactions. On re-import, the original SELL `txn_id` is never in DB (only partial SELL `txn_id`s are), so it passes pipeline deduplication and shows in preview as "new". At commit, the pre-processor re-expands it to the same partials, which are then caught by the second-pass `get_by_txn_id` safety check and skipped. Known limitation: preview count won't match commit count on re-import of a previously committed PDF.

**File:** `app/services/imports/post_processors/fidelity.py`

```python
class FidelityPreCommitProcessor(IPreCommitProcessor):
    source = "fidelity_sale"

    def process(self, result: ImportResult, uow: UnitOfWork) -> ImportResult:
        ...
```

### Main Loop

For each SELL with `acquisition_date` in `result.transactions`:

**Step 1 — Find asset.** Query DB by `asset_identifier` (ticker). If not found, leave SELL unchanged (`lot_id=None`) — the engine will FIFO-fallback.

**Step 2 — Query same-date lots.** Fetch all BUY/VEST transactions for that asset where `date == acquisition_date`, ordered by `id` ascending (FIFO among same-date lots).

**Step 3a — Lots found → split SELL into partials:**
- Walk lots in order, consume `min(lot.units, remaining_units)` from each.
- Each partial SELL:
  - `lot_id = lot.lot_id`
  - `units = consumed`
  - `amount_inr = sell_price_per_unit * consumed` (proportional proceeds)
  - `txn_id = hash("fidelity_partial|" + original_txn_id + "|" + lot.lot_id)` — stable across re-imports
- If units remain after exhausting all same-date lots, create a fallback BUY + remaining-SELL pair (see Step 3c). Log a warning.

**Step 3b — No lots found AND `acquisition_date == date_sold` → sell-to-cover:**
- Create BUY:
  - `date = acquisition_date`, `units = quantity`, `amount_inr = -acquisition_cost`
  - `price_per_unit = acquisition_cost / (units * acquisition_forex_rate)` — USD
  - `forex_rate = acquisition_forex_rate`
  - `lot_id = new_uuid`
  - `txn_id = hash("fidelity_stc_buy|ticker|date_acquired|qty")`
- SELL keeps original `txn_id`, shares the same `lot_id`.

**Step 3c — No lots found AND dates differ → orphaned historical sale:**
- Same BUY creation as Step 3b.
- `txn_id = hash("fidelity_orphan_buy|ticker|date_acquired|qty")`
- Log warning: `"No matching buy found — synthetic lot created for {ticker} on {acquisition_date}"`

The processor replaces the original SELL in `result.transactions` with the expanded list. All other transaction types pass through unchanged.

**Registration:** Add `FidelityPreCommitProcessor` to `post_processors/__init__.py`. Inject into `ImportOrchestrator` via `dependencies.py` as a `pre_commit_processors` list alongside the existing `post_processors` list.

---

## Section 4 — Lot Engine Changes

### `match_lots` (`app/engine/lot_engine.py`)

New function alongside `match_lots_fifo` (which remains unchanged for other asset types):

```python
def match_lots(lots: list, sells: list, stcg_days: int = 365) -> list[dict]:
    remaining = {lot.lot_id: lot.units for lot in lots}
    lot_index = {lot.lot_id: lot for lot in lots}
    ordered_ids = [lot.lot_id for lot in sorted(lots, key=lambda l: l.buy_date)]

    matches = []
    for sell in sells:
        if sell.lot_id and sell.lot_id in lot_index:
            # Specific lot matching — consume from exactly this lot
            _consume(sell, [sell.lot_id], remaining, lot_index, sell.units, stcg_days, matches)
        else:
            # FIFO fallback
            _consume(sell, ordered_ids, remaining, lot_index, sell.units, stcg_days, matches)

    return matches
```

If `sell.lot_id` is set but not found in `lot_index`, log a warning and fall back to FIFO for that sell — no silent data loss.

### `MarketBasedStrategy`

`_match_and_get_open_lots` calls `match_lots` instead of `match_lots_fifo`. Since `_Sell.lot_id` is `None` for STOCK_IN/MF/GOLD/etc, they fall through to FIFO automatically — no strategy-level changes needed.

---

## Section 5 — Error Handling & Edge Cases

| Scenario | Behaviour |
|---|---|
| Re-import same PDF | Partial SELL `txn_id`s are stable → deduplicator skips, DB unchanged |
| `sell.units` > sum of same-date lot units | Exhaust found lots, create fallback BUY+SELL for gap, log warning |
| Ticker has no asset record yet | SELL passed through with `lot_id=None`, FIFO fallback; re-import after asset created resolves correctly |
| `lot_id` on SELL but lot not in engine | `match_lots` logs warning, falls back to FIFO for that sell |
| Fidelity CSV BUY rows | Already get UUID `lot_id` from `import_service.py` — no additional work |

### txn_id Stability Reference

| Transaction | txn_id scheme |
|---|---|
| Original SELL (from PDF) | `hash(ticker\|date_sold\|date_acquired\|qty)` — unchanged |
| Partial SELL (split) | `hash("fidelity_partial\|" + original_txn_id + "\|" + lot_id)` |
| Sell-to-cover BUY | `hash("fidelity_stc_buy\|ticker\|date_acquired\|qty")` |
| Orphaned sale BUY | `hash("fidelity_orphan_buy\|ticker\|date_acquired\|qty")` |

---

## Section 6 — Testing

### Unit: `tests/unit/test_lot_engine.py`
- `match_lots` with specific `lot_id` on SELL consumes from correct lot, not FIFO order
- `match_lots` with `lot_id=None` falls back to FIFO (existing tests still pass)
- `match_lots` with unknown `lot_id` falls back to FIFO with warning logged
- SELL units > lot units with specific matching: consumes available, remainder unmatched

### Unit: `tests/unit/test_fidelity_pdf_importer.py`
- `_parse_match` returns single SELL (not tuple)
- SELL has `acquisition_date`, `acquisition_cost`, `acquisition_forex_rate` populated
- `lot_id` is `None` on emitted SELL
- `txn_id` scheme unchanged

### Unit: `tests/unit/test_fidelity_pre_commit_processor.py`
- Found same-date lots → SELL split into N partials, correct `lot_id`s, proportional amounts, stable `txn_id`s
- Multiple same-date lots → FIFO order respected
- No lots + `date_acquired == date_sold` → BUY+SELL pair, `price_per_unit` in USD, shared `lot_id`
- No lots + dates differ → orphaned BUY created, warning logged
- Units exceed all same-date lots → fallback BUY+SELL for gap
- Missing asset → SELL passed through unchanged

### Integration: `tests/integration/test_fidelity_imports.py`
- Import Fidelity CSV first (creates lots with `lot_id`), then import PDF → SELLs resolve to correct `lot_id`s
- Re-import PDF → all rows deduplicated, DB unchanged
- Lot engine produces correct STCG/LTCG split after specific-lot matching
- Sell-to-cover: BUY+SELL pair created, gains computed correctly

---

## Files Changed

| File | Change |
|---|---|
| `app/importers/base.py` | Add 3 fields to `ParsedTransaction` |
| `app/importers/fidelity_pdf_importer.py` | Emit SELL-only; populate acquisition fields |
| `app/services/imports/post_processors/base.py` | Add `IPreCommitProcessor` protocol |
| `app/services/imports/post_processors/fidelity.py` | New `FidelityPreCommitProcessor` |
| `app/services/imports/post_processors/__init__.py` | Register `FidelityPreCommitProcessor` |
| `app/services/imports/orchestrator.py` | Add `pre_commit_processors` registry; call before transaction loop in `commit()` |
| `app/api/dependencies.py` | Inject `FidelityPreCommitProcessor` into `ImportOrchestrator` |
| `app/engine/lot_engine.py` | Add `match_lots` function |
| `app/engine/lot_helper.py` | Add `lot_id` to `_Sell`; populate in `build_lots_sells` |
| `app/services/returns/strategies/market_based.py` | Call `match_lots` instead of `match_lots_fifo` |
| `app/services/import_service.py` | Respect pre-assigned `lot_id` on `ParsedTransaction` |
| `tests/unit/test_lot_engine.py` | New test cases for specific-lot matching |
| `tests/unit/test_fidelity_pdf_importer.py` | Update for SELL-only output |
| `tests/unit/test_fidelity_pre_commit_processor.py` | New test file |
| `tests/integration/test_fidelity_imports.py` | New integration scenarios |

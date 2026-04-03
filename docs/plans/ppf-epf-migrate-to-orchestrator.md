# Plan: Migrate PPF/EPF imports to ImportOrchestrator

**Goal:** Remove `PPFEPFImportService` and route PPF/EPF through the same `ImportOrchestrator` pipeline used by all other asset types.

## Background

`PPFEPFImportService` exists because PPF/EPF have two behaviours the generic orchestrator doesn't support:
1. Asset must pre-exist — raises `NotFoundError` if not found (no auto-create).
2. Valuation creation — a `Valuation` entry is written from the CSV closing balance (PPF) or passbook net balance (EPF) after import.

All other assets go through `ImportOrchestrator` (preview → commit). PPF/EPF use a direct single-step import and bypass the orchestrator entirely. The migration will adopt the full preview/commit flow — PPF/EPF will behave identically to other assets from the user's perspective.

---

## Structural gaps to bridge

### Gap 1 — PPF valuation creation
`PPFStrategy` inherits `ValuationBasedStrategy` — `get_current_value()` reads the latest `Valuation` row. Without one, current value is `null`. The CSV closing balance must be stored as a `Valuation` entry after import.

EPF does **not** need this. `EPFStrategy.get_current_value()` computes directly from transactions (`sum(CONTRIBUTION) + sum(INTEREST)`). The valuation `PPFEPFImportService` was creating for EPF is dead data — the returns engine never reads it. It is dropped entirely.

### Gap 2 — EPF `is_active` always `True`
EPF asset must never be auto-closed. Needs a post-processor to enforce this.

> **Note:** Asset auto-creation via `_find_or_create_asset` works fine for PPF/EPF — same as all other asset types. No special "asset must pre-exist" flag needed or No error if asset is missing find_or_create_asset should create it.

---

## Changes

### 1. `app/importers/base.py`
Add four optional fields to the `ImportResult` dataclass:

```python
closing_valuation_inr: Optional[float] = None
closing_valuation_date: Optional[date] = None
closing_valuation_source: Optional[str] = None
closing_valuation_notes: Optional[str] = None
```

### 2. `app/importers/ppf_csv_importer.py`
At the end of `PPFCSVImporter.parse()`, populate the new base fields:

```python
result.closing_valuation_inr = closing_balance_inr
result.closing_valuation_date = closing_balance_date
result.closing_valuation_source = "ppf_csv"
result.closing_valuation_notes = f"Closing balance from CSV import (account {account_number})"
```

### 3. `app/importers/epf_pdf_importer.py`
No changes needed. EPF current value is computed from transactions by `EPFStrategy` — no valuation fields to populate.

### 4. `app/services/imports/orchestrator.py`
One change — create valuation after the transaction loop, still inside the `with self._uow_factory() as uow:` block:

```python
if result.closing_valuation_inr is not None and result.closing_valuation_date is not None:
    first_txn = result.transactions[0] if result.transactions else None
    if first_txn:
        asset = self._find_or_create_asset(first_txn, uow)
        uow.valuations.create(
            asset_id=asset.id,
            date=result.closing_valuation_date,
            value_inr=int(result.closing_valuation_inr * 100),
            source=result.closing_valuation_source or "import",
            notes=result.closing_valuation_notes,
        )
```

No new helpers needed — `_find_or_create_asset` handles asset lookup as usual.

### 5. `app/services/imports/post_processors/epf.py` — new file (Gap 2)
```python
from typing import ClassVar

class EPFPostProcessor:
    asset_types: ClassVar[list[str]] = ["EPF"]

    def process(self, asset, txns: list, uow) -> None:
        """EPF asset is never auto-closed."""
        asset.is_active = True
```

### 6. `app/api/dependencies.py`
- Import `EPFPostProcessor` and `MFPostProcessor` (note: `MFPostProcessor` is currently used but not imported — fix this here).
- Register both in `get_import_orchestrator()`:

```python
from app.services.imports.post_processors.mf import MFPostProcessor
from app.services.imports.post_processors.ppf_epf import EPFPostProcessor

post_processors=[StockPostProcessor(), MFPostProcessor(), EPFPostProcessor()]
```

### 7. `app/api/imports.py`
Update the `/import/ppf-csv` and `/import/epf-pdf` route handlers to use ImportService as done for /import/nps-csv or /import/cas-pdf

Remove the `PPFEPFImportService` import from this file.

### 8. `cli.py`
Update `cmd_import_ppf` and `cmd_import_epf` to use existing endpoints but change result keys to created_count and skipped_count:

```python

```

### 9. Delete `app/services/ppf_epf_import_service.py`

### 10. `tests/integration/test_import_flow.py`
The two tests that patch at `app.services.ppf_epf_import_service.PPFCSVImporter` / `EPFPDFImporter` need to be updated to patch at their actual module paths:
- `app.importers.ppf_csv_importer.PPFCSVImporter`
- `app.importers.epf_pdf_importer.EPFPDFImporter`

And the test setup/assertions should reflect the orchestrator response shape (`ImportCommitResponse`) instead of the old `{inserted, skipped, valuation_created, ...}` dict.

---

## Notes
- Update / add tests for all the touched files.
- Use feature branch feature/refactor to commit code changes once done.
- The old `/import/ppf-csv` and `/import/epf-pdf` endpoints are deleted — the generic `/import/preview-file` + `/import/commit-file/{preview_id}` endpoints handle everything.
- The response shape changes from `{inserted, skipped, valuation_created, valuation_value, ...}` to `ImportCommitResponse(inserted, skipped, errors)`. The `valuation_created` field is dropped — the valuation is still created as a side effect but not surfaced in the response. This is acceptable for a personal tool.
- `uow.valuations` is already present on `UnitOfWork` — no repo changes needed.
- The PPF/EPF importers keep their subclass result types (`PPFCSVImportResult`, `EPFImportResult`) for internal use; the new base fields are the contract the orchestrator reads.

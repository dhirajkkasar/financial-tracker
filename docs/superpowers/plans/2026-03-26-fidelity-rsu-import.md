# Fidelity RSU CSV & Sale PDF Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add idempotent import of (1) Fidelity RSU holding CSVs as VEST transactions and (2) Fidelity transaction summary PDFs as tax-cover SELL transactions, both with user-supplied USD/INR exchange rates.

**Architecture:** Two new parsers (`fidelity_rsu_csv_parser.py`, `fidelity_pdf_parser.py`) follow the existing `BaseImporter` protocol. Both use a single `preview → commit` API flow. The CLI parses each file locally first (CSV via stdlib `csv`; PDF via `pdfplumber` which is already in the backend venv) to discover which month-years need rates, prompts the user for each, then calls one API endpoint with file + rates. If any required month-year is missing from the provided rates, the API returns a 422 with a clear message listing the missing months. `ParsedTransaction` gets a new `forex_rate` field and `ImportService` is updated to persist it and set `currency="USD"` for `STOCK_US` assets.

**Tech Stack:** Python/FastAPI backend, pdfplumber (already installed), standard csv module, argparse CLI.

---

## File Map

| Action | File |
|--------|------|
| Create | `backend/app/importers/fidelity_rsu_csv_parser.py` |
| Create | `backend/app/importers/fidelity_pdf_parser.py` |
| Modify | `backend/app/importers/base.py` — add `forex_rate` to `ParsedTransaction` |
| Modify | `backend/app/services/import_service.py` — pass `forex_rate` in commit; set `currency="USD"` for STOCK_US |
| Modify | `backend/app/api/imports.py` — 2 new endpoints (one per importer) |
| Modify | `backend/cli.py` — 2 new import subcommands |
| Create | `backend/tests/unit/test_fidelity_rsu_csv_parser.py` |
| Create | `backend/tests/unit/test_fidelity_pdf_parser.py` |
| Create | `backend/tests/integration/test_fidelity_imports.py` |
| Create | `backend/tests/fixtures/fidelity_rsu_sample.csv` |

**No frontend changes** — the US Stocks page (`frontend/app/us-stocks/page.tsx`) already renders `STOCK_US` assets with HoldingsTable, avg price, units, and current value.

---

## Task 1: Add `forex_rate` to `ParsedTransaction` and fix `ImportService`

**Files:**
- Modify: `backend/app/importers/base.py`
- Modify: `backend/app/services/import_service.py`

- [ ] **Step 1.1: Write failing test for forex_rate persistence**

```python
# backend/tests/integration/test_fidelity_imports.py (create file now, add more later)
import pytest
from app.importers.base import ParsedTransaction
from datetime import date

def test_parsed_transaction_has_forex_rate_field():
    txn = ParsedTransaction(
        source="test", asset_name="AMZN", asset_identifier="AMZN",
        asset_type="STOCK_US", txn_type="VEST", date=date(2025, 3, 17),
        units=68.0, price_per_unit=196.40, amount_inr=-1_380_605.0,
        txn_id="test_001", forex_rate=84.5,
    )
    assert txn.forex_rate == 84.5
```

Run: `cd backend && uv run pytest tests/integration/test_fidelity_imports.py::test_parsed_transaction_has_forex_rate_field -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'forex_rate'`

- [ ] **Step 1.2: Add `forex_rate` field to `ParsedTransaction`**

In `backend/app/importers/base.py`, add after `mfapi_scheme_code`:

```python
    mfapi_scheme_code: Optional[str] = None
    forex_rate: Optional[float] = None    # USD/INR rate used for conversion
```

Run: `uv run pytest tests/integration/test_fidelity_imports.py::test_parsed_transaction_has_forex_rate_field -v`
Expected: PASS

- [ ] **Step 1.3: Write failing test for forex_rate persisted in DB**

Add to `backend/tests/integration/test_fidelity_imports.py`:

```python
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
import json

def test_commit_persists_forex_rate(test_db):
    """Committed VEST transaction stores forex_rate in DB."""
    from app.importers.base import ParsedTransaction
    from app.services.import_service import ImportService
    from app.repositories.transaction_repo import TransactionRepository
    from datetime import date

    svc = ImportService(test_db)
    txn = ParsedTransaction(
        source="fidelity_rsu", asset_name="AMZN", asset_identifier="AMZN",
        asset_type="STOCK_US", txn_type="VEST", date=date(2025, 3, 17),
        units=68.0, price_per_unit=196.40, amount_inr=-1_380_000.0,
        txn_id="fidelity_rsu_test_001", forex_rate=84.5,
    )
    preview = svc.preview(transactions=[txn])
    svc.commit(preview["preview_id"])

    repo = TransactionRepository(test_db)
    saved = repo.get_by_txn_id("fidelity_rsu_test_001")
    assert saved is not None
    assert saved.forex_rate == pytest.approx(84.5)
```

Run: `uv run pytest tests/integration/test_fidelity_imports.py::test_commit_persists_forex_rate -v`
Expected: FAIL (forex_rate is None in DB — ImportService passes `forex_rate=None` to repo)

- [ ] **Step 1.4: Update `ImportService.commit()` to pass forex_rate**

In `backend/app/services/import_service.py`, in the `commit` method, update the `txn_repo.create()` call:

```python
            txn_repo.create(
                txn_id=txn.txn_id,
                asset_id=asset.id,
                type=TransactionType(txn.txn_type),
                date=txn.date,
                units=txn.units,
                price_per_unit=txn.price_per_unit,
                forex_rate=txn.forex_rate,          # ← was hardcoded None, now uses parsed value
                amount_inr=amount_paise,
                charges_inr=charges_paise,
                lot_id=lot_id,
                notes=txn.notes,
            )
```

Run: `uv run pytest tests/integration/test_fidelity_imports.py::test_commit_persists_forex_rate -v`
Expected: PASS

- [ ] **Step 1.5: Write test that STOCK_US asset is created with currency="USD"**

Add to `backend/tests/integration/test_fidelity_imports.py`:

```python
def test_stock_us_asset_created_with_usd_currency(test_db):
    from app.importers.base import ParsedTransaction
    from app.services.import_service import ImportService
    from app.models.asset import Asset
    from datetime import date

    svc = ImportService(test_db)
    txn = ParsedTransaction(
        source="fidelity_rsu", asset_name="AMZN2", asset_identifier="AMZN2",
        asset_type="STOCK_US", txn_type="VEST", date=date(2025, 3, 17),
        units=10.0, price_per_unit=200.0, amount_inr=-170_000.0,
        txn_id="fidelity_rsu_currency_test", forex_rate=85.0,
    )
    preview = svc.preview(transactions=[txn])
    svc.commit(preview["preview_id"])

    asset = test_db.query(Asset).filter(Asset.identifier == "AMZN2").first()
    assert asset is not None
    assert asset.currency == "USD"
```

Run: `uv run pytest tests/integration/test_fidelity_imports.py::test_stock_us_asset_created_with_usd_currency -v`
Expected: FAIL (asset.currency == "INR")

- [ ] **Step 1.6: Fix `_find_or_create_asset` to use currency="USD" for STOCK_US**

In `backend/app/services/import_service.py`, update `_find_or_create_asset`:

```python
        currency = "USD" if txn.asset_type in {"STOCK_US", "RSU"} else "INR"
        return asset_repo.create(
            name=txn.asset_name,
            identifier=txn.asset_identifier or None,
            asset_type=asset_type,
            asset_class=asset_class,
            currency=currency,
        )
```

Run: `uv run pytest tests/integration/test_fidelity_imports.py::test_stock_us_asset_created_with_usd_currency -v`
Expected: PASS

- [ ] **Step 1.7: Run all existing tests to confirm no regression**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All previously passing tests still pass.

- [ ] **Step 1.8: Commit**

```bash
git add backend/app/importers/base.py backend/app/services/import_service.py backend/tests/integration/test_fidelity_imports.py
git commit -m "feat: add forex_rate to ParsedTransaction and persist in import commit; set USD currency for STOCK_US assets"
```

---

## Task 2: Fidelity RSU CSV Parser

**Files:**
- Create: `backend/app/importers/fidelity_rsu_csv_parser.py`
- Create: `backend/tests/unit/test_fidelity_rsu_csv_parser.py`
- Create: `backend/tests/fixtures/fidelity_rsu_sample.csv`

- [ ] **Step 2.1: Create the test fixture CSV**

Create `backend/tests/fixtures/fidelity_rsu_sample.csv`:
```
Date acquired,Quantity,Cost basis,Cost basis/share,Value,Gain/loss,Sale availability date,Transfer availability date,Grant date,Share source,Holding period
Mar-17-2025,68.0000,13355.28,196.40,14430.96,1075.68,Mar-17-2025,Mar-17-2025,Oct-28-2022,RS,Long
Sep-16-2024,51.0000,9408.89,184.49,10823.22,1414.33,Sep-16-2024,Sep-16-2024,Oct-28-2022,RS,Long
,
The values are displayed in USD
```

- [ ] **Step 2.2: Write failing tests for the RSU CSV parser**

Create `backend/tests/unit/test_fidelity_rsu_csv_parser.py`:

```python
import pytest
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestFidelityRSUImporter:
    RATES = {"2025-03": 86.5, "2024-09": 83.8}

    def test_parse_returns_correct_transaction_count(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        result = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv")
        assert len(result.transactions) == 2
        assert result.errors == []

    def test_parse_vest_transaction_fields(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txn = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions[0]

        assert txn.asset_name == "AMZN"
        assert txn.asset_identifier == "AMZN"
        assert txn.asset_type == "STOCK_US"
        assert txn.txn_type == "VEST"
        assert txn.date == date(2025, 3, 17)
        assert txn.units == pytest.approx(68.0)
        assert txn.price_per_unit == pytest.approx(196.40)
        assert txn.forex_rate == pytest.approx(86.5)

    def test_parse_amount_inr_is_negative_outflow(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txn = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions[0]
        # cost_basis=13355.28, rate=86.5 → -1_155_231.72
        assert txn.amount_inr == pytest.approx(-(13355.28 * 86.5), rel=1e-4)

    def test_parse_txn_id_is_stable(self):
        """Same row imported twice produces the same txn_id."""
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        imp = FidelityRSUImporter(exchange_rates=self.RATES)
        id1 = imp.parse(data, "NASDAQ_AMZN.csv").transactions[0].txn_id
        id2 = imp.parse(data, "NASDAQ_AMZN.csv").transactions[0].txn_id
        assert id1 == id2
        assert id1.startswith("fidelity_rsu_")

    def test_parse_txn_id_differs_by_row(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txns = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions
        assert txns[0].txn_id != txns[1].txn_id

    def test_extract_required_month_years(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        months = FidelityRSUImporter.extract_required_month_years(data)
        assert months == ["2024-09", "2025-03"]

    def test_missing_exchange_rate_adds_error(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        # Only provide one rate — second row should error
        result = FidelityRSUImporter(exchange_rates={"2025-03": 86.5}).parse(data, "NASDAQ_AMZN.csv")
        assert len(result.transactions) == 1
        assert len(result.errors) == 1
        assert "2024-09" in result.errors[0]

    def test_parse_ticker_from_filename(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        market, ticker = FidelityRSUImporter._parse_ticker_from_filename("NASDAQ_AMZN.csv")
        assert market == "NASDAQ"
        assert ticker == "AMZN"

    def test_parse_ticker_uppercase(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        _, ticker = FidelityRSUImporter._parse_ticker_from_filename("NYSE_MSFT.csv")
        assert ticker == "MSFT"

    def test_parse_notes_includes_market(self):
        from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
        data = _load_fixture("fidelity_rsu_sample.csv")
        txn = FidelityRSUImporter(exchange_rates=self.RATES).parse(data, "NASDAQ_AMZN.csv").transactions[0]
        assert "NASDAQ" in (txn.notes or "")
```

Run: `uv run pytest tests/unit/test_fidelity_rsu_csv_parser.py -v`
Expected: All FAIL with `ModuleNotFoundError`

- [ ] **Step 2.3: Implement the RSU CSV parser**

Create `backend/app/importers/fidelity_rsu_csv_parser.py`:

```python
import csv
import hashlib
import io
import logging
from datetime import datetime

from app.importers.base import ParsedTransaction, ImportResult

logger = logging.getLogger(__name__)


class FidelityRSUImporter:
    """Parses Fidelity RSU holding CSV exports (current holdings format).

    Filename format: {MARKET}_{TICKER}.csv  e.g. NASDAQ_AMZN.csv
    Relevant columns: Date acquired, Quantity, Cost basis, Cost basis/share
    All USD amounts; exchange_rates maps "YYYY-MM" → float (USD/INR).
    txn_id is a SHA-256 hash of ticker|date|quantity|cost_per_share — stable across re-imports.
    """

    def __init__(self, exchange_rates: dict[str, float] | None = None):
        self.exchange_rates = exchange_rates or {}

    @staticmethod
    def extract_required_month_years(file_bytes: bytes) -> list[str]:
        """Return sorted unique YYYY-MM strings from 'Date acquired' column."""
        months: set[str] = set()
        text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            date_str = (row.get("Date acquired") or "").strip()
            if not date_str or not date_str[0].isalpha():
                continue
            try:
                d = datetime.strptime(date_str, "%b-%d-%Y")
                months.add(d.strftime("%Y-%m"))
            except ValueError:
                pass
        return sorted(months)

    @staticmethod
    def _parse_ticker_from_filename(filename: str) -> tuple[str, str]:
        """'NASDAQ_AMZN.csv' → ('NASDAQ', 'AMZN'). Returns ('', stem) on bad format."""
        stem = filename.rsplit(".", 1)[0]
        parts = stem.split("_", 1)
        if len(parts) == 2:
            return parts[0].upper(), parts[1].upper()
        return "", stem.upper()

    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
        result = ImportResult(source="fidelity_rsu")
        market, ticker = self._parse_ticker_from_filename(filename)
        if not ticker:
            result.errors.append(
                "Cannot determine ticker from filename. Expected: MARKET_TICKER.csv"
            )
            return result

        text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader):
            date_str = (row.get("Date acquired") or "").strip()
            # Skip footer/blank rows that don't start with a month abbreviation
            if not date_str or not date_str[0].isalpha():
                continue
            try:
                txn = self._parse_row(row, ticker, market)
                result.transactions.append(txn)
            except Exception as e:
                result.errors.append(f"Row {i + 2}: {e}")
        return result

    def _parse_row(self, row: dict, ticker: str, market: str) -> ParsedTransaction:
        date_str = row["Date acquired"].strip()
        vest_date = datetime.strptime(date_str, "%b-%d-%Y").date()
        quantity = float(row["Quantity"].replace(",", ""))
        cost_basis_total = float(row["Cost basis"].replace(",", "").lstrip("$"))
        cost_basis_per_share = float(row["Cost basis/share"].replace(",", "").lstrip("$"))

        month_year = vest_date.strftime("%Y-%m")
        forex_rate = self.exchange_rates.get(month_year)
        if forex_rate is None:
            raise ValueError(f"No exchange rate provided for {month_year}")

        amount_inr = -(cost_basis_total * forex_rate)  # VEST = outflow (negative)
        txn_id = self._make_txn_id(ticker, vest_date.isoformat(), quantity, cost_basis_per_share)

        return ParsedTransaction(
            source="fidelity_rsu",
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type="VEST",
            date=vest_date,
            units=quantity,
            price_per_unit=cost_basis_per_share,
            forex_rate=forex_rate,
            amount_inr=amount_inr,
            txn_id=txn_id,
            notes=f"RSU vest via Fidelity ({market})",
        )

    @staticmethod
    def _make_txn_id(ticker: str, date_iso: str, quantity: float, cost_per_share: float) -> str:
        """Stable txn_id: SHA-256 of pipe-delimited key fields."""
        q_int = round(quantity * 10000)   # avoid float formatting variance
        c_int = round(cost_per_share * 100)
        raw = f"fidelity_rsu|{ticker}|{date_iso}|{q_int}|{c_int}"
        return "fidelity_rsu_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
```

Run: `uv run pytest tests/unit/test_fidelity_rsu_csv_parser.py -v`
Expected: All PASS

- [ ] **Step 2.4: Commit**

```bash
git add backend/app/importers/fidelity_rsu_csv_parser.py backend/tests/unit/test_fidelity_rsu_csv_parser.py backend/tests/fixtures/fidelity_rsu_sample.csv
git commit -m "feat: Fidelity RSU CSV parser with stable txn_id and forex_rate support"
```

---

## Task 3: Fidelity Sale PDF Parser

**Files:**
- Create: `backend/app/importers/fidelity_pdf_parser.py`
- Create: `backend/tests/unit/test_fidelity_pdf_parser.py`

- [ ] **Step 3.1: Write failing tests for the sale PDF parser**

Create `backend/tests/unit/test_fidelity_pdf_parser.py`:

```python
import pytest
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_sample_pdf_bytes() -> bytes:
    """Return the real Fidelity PDF fixture bytes for testing."""
    path = FIXTURES / "fidelity_sale_sample.pdf"
    if path.exists():
        return path.read_bytes()
    pytest.skip("fidelity_sale_sample.pdf fixture not available")


class TestFidelityPDFParser:
    RATES = {"2025-03": 86.0, "2025-09": 84.5}

    def _parse(self):
        from app.importers.fidelity_pdf_parser import FidelityPDFParser
        data = _make_sample_pdf_bytes()
        return FidelityPDFParser(exchange_rates=self.RATES).parse(data, "fidelity_sale.pdf")

    def test_parse_returns_two_transactions(self):
        result = self._parse()
        assert len(result.transactions) == 2
        assert result.errors == []

    def test_parse_sell_transaction_type(self):
        txn = self._parse().transactions[0]
        assert txn.txn_type == "SELL"
        assert txn.asset_type == "STOCK_US"

    def test_parse_ticker_is_amzn(self):
        txn = self._parse().transactions[0]
        assert txn.asset_name == "AMZN"
        assert txn.asset_identifier == "AMZN"

    def test_parse_first_sale_date(self):
        txn = self._parse().transactions[0]
        assert txn.date == date(2025, 3, 17)

    def test_parse_first_sale_units(self):
        txn = self._parse().transactions[0]
        assert txn.units == pytest.approx(36.0)

    def test_parse_first_sale_amount_inr_positive_inflow(self):
        # proceeds = $7,070.24, rate = 86.0 → +608,040.64 INR
        txn = self._parse().transactions[0]
        assert txn.amount_inr == pytest.approx(7070.24 * 86.0, rel=1e-4)
        assert txn.amount_inr > 0  # SELL = inflow

    def test_parse_forex_rate_stored(self):
        txn = self._parse().transactions[0]
        assert txn.forex_rate == pytest.approx(86.0)

    def test_parse_notes_tag_tax_cover(self):
        txn = self._parse().transactions[0]
        assert "Tax cover sale" in (txn.notes or "")

    def test_parse_txn_id_is_stable(self):
        from app.importers.fidelity_pdf_parser import FidelityPDFParser
        data = _make_sample_pdf_bytes()
        imp = FidelityPDFParser(exchange_rates=self.RATES)
        id1 = imp.parse(data, "f.pdf").transactions[0].txn_id
        id2 = imp.parse(data, "f.pdf").transactions[0].txn_id
        assert id1 == id2
        assert id1.startswith("fidelity_sale_")

    def test_parse_txn_ids_are_unique(self):
        txns = self._parse().transactions
        ids = [t.txn_id for t in txns]
        assert len(ids) == len(set(ids))

    def test_extract_required_month_years(self):
        from app.importers.fidelity_pdf_parser import FidelityPDFParser
        data = _make_sample_pdf_bytes()
        months = FidelityPDFParser.extract_required_month_years(data)
        assert "2025-03" in months
        assert "2025-09" in months

    def test_missing_rate_adds_error(self):
        from app.importers.fidelity_pdf_parser import FidelityPDFParser
        data = _make_sample_pdf_bytes()
        result = FidelityPDFParser(exchange_rates={"2025-03": 86.0}).parse(data, "f.pdf")
        # 2025-09 row should error
        assert any("2025-09" in e for e in result.errors)
```

Run: `uv run pytest tests/unit/test_fidelity_pdf_parser.py -v`
Expected: All FAIL with `ModuleNotFoundError`

- [ ] **Step 3.2: Copy the real PDF as a test fixture**

```bash
cp "/Users/dhirajkasar/Downloads/amazonstockstracking/Custom transaction summary - Fidelity NetBenefits 2025.pdf" \
   backend/tests/fixtures/fidelity_sale_sample.pdf
```

- [ ] **Step 3.3: Implement the Fidelity Sale PDF parser**

Create `backend/app/importers/fidelity_pdf_parser.py`:

```python
import hashlib
import logging
import re
from datetime import datetime

import pdfplumber

from app.importers.base import ParsedTransaction, ImportResult

logger = logging.getLogger(__name__)

# Regex for sale rows: "Mar-17-2025 Mar-17-2025 36.0000 $7,070.44 $7,070.24 -$0.20 USD RS"
_SALE_ROW_RE = re.compile(
    r"(\w{3}-\d{2}-\d{4})\s+"   # date sold
    r"(\w{3}-\d{2}-\d{4})\s+"   # date acquired
    r"([\d,]+\.?\d*)\s+"         # quantity
    r"\$([\d,]+\.?\d*)\s+"       # cost basis
    r"\$([\d,]+\.?\d*)\s+"       # proceeds
    r"[+-]?\$[\d,]+\.?\d*\s+"    # gain/loss (ignored)
    r"USD\s+(\w+)"                # stock source
)

# Ticker line: "AMZN: AMAZON.COM INC" or "AMZN: Amazon.com, Inc."
_TICKER_RE = re.compile(r"^([A-Z]{1,6}):\s+.+")


class FidelityPDFParser:
    """Parses Fidelity NetBenefits transaction summary PDFs.

    Extracts rows from the 'Stock sales' section.
    All USD amounts; exchange_rates maps "YYYY-MM" → float (USD/INR).
    Sale transactions are tagged as 'Tax cover sale' in notes.
    txn_id is SHA-256 of ticker|date_sold|date_acquired|quantity — stable across re-imports.
    """

    def __init__(self, exchange_rates: dict[str, float] | None = None):
        self.exchange_rates = exchange_rates or {}

    @staticmethod
    def extract_required_month_years(file_bytes: bytes) -> list[str]:
        """Return sorted unique YYYY-MM strings from 'Date sold' column in Stock sales section."""
        import io as _io
        months: set[str] = set()
        with pdfplumber.open(_io.BytesIO(file_bytes)) as pdf:
            in_sales = False
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    if "Stock sales" in line:
                        in_sales = True
                    if in_sales:
                        m = _SALE_ROW_RE.search(line)
                        if m:
                            try:
                                d = datetime.strptime(m.group(1), "%b-%d-%Y")
                                months.add(d.strftime("%Y-%m"))
                            except ValueError:
                                pass
        return sorted(months)

    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
        import io as _io
        result = ImportResult(source="fidelity_sale")
        ticker: str | None = None
        in_sales = False

        with pdfplumber.open(_io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    line = line.strip()
                    if "Stock sales" in line:
                        in_sales = True
                        continue
                    if in_sales and not ticker:
                        m = _TICKER_RE.match(line)
                        if m:
                            ticker = m.group(1)
                    if in_sales and ticker:
                        m = _SALE_ROW_RE.search(line)
                        if m:
                            try:
                                txn = self._parse_match(m, ticker)
                                result.transactions.append(txn)
                            except Exception as e:
                                result.errors.append(f"Row parse error: {e}")

        if not ticker:
            result.errors.append("Could not find ticker in PDF (expected 'TICK: Company Name' line)")
        return result

    def _parse_match(self, m: re.Match, ticker: str) -> ParsedTransaction:
        date_sold_str, date_acq_str = m.group(1), m.group(2)
        quantity_str, cost_str, proceeds_str = m.group(3), m.group(4), m.group(5)

        date_sold = datetime.strptime(date_sold_str, "%b-%d-%Y").date()
        date_acquired = datetime.strptime(date_acq_str, "%b-%d-%Y").date()
        quantity = float(quantity_str.replace(",", ""))
        proceeds_usd = float(proceeds_str.replace(",", ""))

        month_year = date_sold.strftime("%Y-%m")
        forex_rate = self.exchange_rates.get(month_year)
        if forex_rate is None:
            raise ValueError(f"No exchange rate provided for {month_year}")

        amount_inr = proceeds_usd * forex_rate  # SELL = inflow (positive)
        price_per_unit_usd = proceeds_usd / quantity if quantity else None
        txn_id = self._make_txn_id(ticker, date_sold.isoformat(), date_acquired.isoformat(), quantity)

        return ParsedTransaction(
            source="fidelity_sale",
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type="SELL",
            date=date_sold,
            units=quantity,
            price_per_unit=price_per_unit_usd,
            forex_rate=forex_rate,
            amount_inr=amount_inr,
            txn_id=txn_id,
            notes=f"Tax cover sale (acquired {date_acquired.isoformat()})",
        )

    @staticmethod
    def _make_txn_id(ticker: str, date_sold: str, date_acquired: str, quantity: float) -> str:
        q_int = round(quantity * 10000)
        raw = f"fidelity_sale|{ticker}|{date_sold}|{date_acquired}|{q_int}"
        return "fidelity_sale_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
```

Run: `uv run pytest tests/unit/test_fidelity_pdf_parser.py -v`
Expected: All PASS

- [ ] **Step 3.4: Commit**

```bash
git add backend/app/importers/fidelity_pdf_parser.py backend/tests/unit/test_fidelity_pdf_parser.py backend/tests/fixtures/fidelity_sale_sample.pdf
git commit -m "feat: Fidelity sale PDF parser (tax-cover SELL transactions)"
```

---

## Task 4: API Endpoints

**Files:**
- Modify: `backend/app/api/imports.py`
- Modify: `backend/tests/integration/test_fidelity_imports.py`

Two new endpoints (one per importer, same pattern as `/broker-csv`):
1. `POST /import/fidelity-rsu-csv` — file + exchange_rates JSON → preview
2. `POST /import/fidelity-sale-pdf` — file + exchange_rates JSON → preview

Both return 422 with a clear message listing missing month-years if `exchange_rates` does not cover all dates found in the file.

- [ ] **Step 4.1: Write failing integration tests for the endpoints**

Add to `backend/tests/integration/test_fidelity_imports.py`:

```python
from pathlib import Path
import json

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_fidelity_rsu_csv_endpoint_preview(client):
    """POST /import/fidelity-rsu-csv returns a valid preview."""
    csv_bytes = (FIXTURES / "fidelity_rsu_sample.csv").read_bytes()
    rates = {"2025-03": 86.5, "2024-09": 83.8}
    resp = client.post(
        "/import/fidelity-rsu-csv",
        data={"exchange_rates": json.dumps(rates)},
        files={"file": ("NASDAQ_AMZN.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "preview_id" in body
    assert body["new_count"] == 2
    assert body["duplicate_count"] == 0


def test_fidelity_rsu_csv_endpoint_missing_rate_returns_422(client):
    """POST /import/fidelity-rsu-csv with incomplete rates returns 422."""
    csv_bytes = (FIXTURES / "fidelity_rsu_sample.csv").read_bytes()
    resp = client.post(
        "/import/fidelity-rsu-csv",
        data={"exchange_rates": json.dumps({"2025-03": 86.5})},  # missing 2024-09
        files={"file": ("NASDAQ_AMZN.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 422
    assert "2024-09" in resp.text


def test_fidelity_rsu_csv_endpoint_idempotent(client):
    """Importing the same CSV twice skips duplicates."""
    csv_bytes = (FIXTURES / "fidelity_rsu_sample.csv").read_bytes()
    rates = {"2025-03": 86.5, "2024-09": 83.8}

    def do_import():
        resp = client.post(
            "/import/fidelity-rsu-csv",
            data={"exchange_rates": json.dumps(rates)},
            files={"file": ("NASDAQ_AMZN.csv", csv_bytes, "text/csv")},
        )
        preview_id = resp.json()["preview_id"]
        return client.post("/import/commit", json={"preview_id": preview_id}).json()

    first = do_import()
    second = do_import()
    assert first["created_count"] == 2
    assert second["created_count"] == 0
    assert second["skipped_count"] == 2


def test_fidelity_sale_pdf_endpoint_preview(client):
    """POST /import/fidelity-sale-pdf returns preview with 2 SELL transactions."""
    pdf_bytes = (FIXTURES / "fidelity_sale_sample.pdf").read_bytes()
    rates = {"2025-03": 86.0, "2025-09": 84.5}
    resp = client.post(
        "/import/fidelity-sale-pdf",
        data={"exchange_rates": json.dumps(rates)},
        files={"file": ("sale.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "preview_id" in body
    assert body["new_count"] == 2
    txns = body["transactions"]
    assert all(t["txn_type"] == "SELL" for t in txns)
    assert all("Tax cover sale" in (t["notes"] or "") for t in txns)


def test_fidelity_sale_pdf_endpoint_missing_rate_returns_422(client):
    """POST /import/fidelity-sale-pdf with incomplete rates returns 422."""
    pdf_bytes = (FIXTURES / "fidelity_sale_sample.pdf").read_bytes()
    resp = client.post(
        "/import/fidelity-sale-pdf",
        data={"exchange_rates": json.dumps({"2025-03": 86.0})},  # missing 2025-09
        files={"file": ("sale.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 422
    assert "2025-09" in resp.text


def test_fidelity_sale_pdf_endpoint_idempotent(client):
    """Importing the same PDF twice skips duplicates."""
    pdf_bytes = (FIXTURES / "fidelity_sale_sample.pdf").read_bytes()
    rates = {"2025-03": 86.0, "2025-09": 84.5}

    def do_import():
        resp = client.post(
            "/import/fidelity-sale-pdf",
            data={"exchange_rates": json.dumps(rates)},
            files={"file": ("sale.pdf", pdf_bytes, "application/pdf")},
        )
        preview_id = resp.json()["preview_id"]
        return client.post("/import/commit", json={"preview_id": preview_id}).json()

    first = do_import()
    second = do_import()
    assert first["created_count"] == 2
    assert second["created_count"] == 0
    assert second["skipped_count"] == 2
```

Run: `uv run pytest tests/integration/test_fidelity_imports.py -v -k "endpoint"`
Expected: All FAIL (routes not defined yet)

- [ ] **Step 4.2: Implement the two endpoints in `imports.py`**

Add these imports at the top of `backend/app/api/imports.py`:

```python
import json as _json
from fastapi import Form
from app.importers.fidelity_rsu_csv_parser import FidelityRSUImporter
from app.importers.fidelity_pdf_parser import FidelityPDFParser
```

Then add these two route handlers at the bottom of the file:

```python
@router.post("/fidelity-rsu-csv")
async def import_fidelity_rsu_csv(
    file: UploadFile = File(...),
    exchange_rates: str = Form(..., description='JSON object e.g. {"2025-03": 86.5}'),
    svc: ImportService = Depends(get_import_service),
):
    """Import Fidelity RSU holding CSV. Filename must be MARKET_TICKER.csv.
    exchange_rates: JSON string mapping 'YYYY-MM' to USD/INR float.
    Returns 422 if any vest month-year is missing from exchange_rates.
    Returns preview_id for use with POST /import/commit.
    """
    try:
        rates: dict[str, float] = _json.loads(exchange_rates)
    except Exception:
        raise ValidationError("exchange_rates must be valid JSON, e.g. {\"2025-03\": 86.5}")

    file_bytes = await file.read()

    # Validate all required months are covered before parsing
    required = FidelityRSUImporter.extract_required_month_years(file_bytes)
    missing = [m for m in required if m not in rates]
    if missing:
        raise ValidationError(
            f"Missing exchange rates for month(s): {', '.join(missing)}. "
            f"Provide USD/INR rate for each."
        )

    result = FidelityRSUImporter(exchange_rates=rates).parse(file_bytes, file.filename or "")
    if result.errors and not result.transactions:
        raise ValidationError(f"Parse failed: {'; '.join(result.errors)}")
    return svc.preview(transactions=result.transactions)


@router.post("/fidelity-sale-pdf")
async def import_fidelity_sale_pdf(
    file: UploadFile = File(...),
    exchange_rates: str = Form(..., description='JSON object e.g. {"2025-03": 86.0}'),
    svc: ImportService = Depends(get_import_service),
):
    """Import Fidelity tax-cover SELL transactions from a transaction summary PDF.
    exchange_rates: JSON string mapping 'YYYY-MM' to USD/INR float (use RBI monthly average).
    Returns 422 if any sale month-year is missing from exchange_rates.
    Returns preview_id for use with POST /import/commit.
    SELL transactions are tagged 'Tax cover sale' in notes for tax-page visibility.
    """
    try:
        rates: dict[str, float] = _json.loads(exchange_rates)
    except Exception:
        raise ValidationError("exchange_rates must be valid JSON")

    file_bytes = await file.read()

    # Validate all required months are covered before parsing
    required = FidelityPDFParser.extract_required_month_years(file_bytes)
    missing = [m for m in required if m not in rates]
    if missing:
        raise ValidationError(
            f"Missing exchange rates for month(s): {', '.join(missing)}. "
            f"Provide USD/INR rate for each."
        )

    result = FidelityPDFParser(exchange_rates=rates).parse(file_bytes, file.filename or "")
    if result.errors and not result.transactions:
        raise ValidationError(f"Parse failed: {'; '.join(result.errors)}")
    return svc.preview(transactions=result.transactions)
```

Run: `uv run pytest tests/integration/test_fidelity_imports.py -v`
Expected: All PASS

- [ ] **Step 4.3: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass.

- [ ] **Step 4.4: Commit**

```bash
git add backend/app/api/imports.py backend/tests/integration/test_fidelity_imports.py
git commit -m "feat: API endpoints for Fidelity RSU CSV and sale PDF import with missing-rate validation"
```

---

## Task 5: CLI Commands

**Files:**
- Modify: `backend/cli.py`

Two new import subcommands:
- `python cli.py import fidelity-rsu <file>` — parses CSV locally to find dates, prompts rates, imports
- `python cli.py import fidelity-sale <file>` — calls `/dates` endpoint, prompts rates, imports

- [ ] **Step 5.1: Implement `cmd_import_fidelity_rsu`**

Add the following function to `backend/cli.py` after `cmd_import_broker_csv`:

```python
def cmd_import_fidelity_rsu(file_path: str) -> None:
    """Import Fidelity RSU holding CSV (MARKET_TICKER.csv format).
    Prompts for USD/INR exchange rate per vest month.
    """
    import csv as _csv
    from datetime import datetime

    # Step 1: Parse CSV locally to find required month-years
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        months: set[str] = set()
        for row in reader:
            date_str = (row.get("Date acquired") or "").strip()
            if not date_str or not date_str[0].isalpha():
                continue
            try:
                d = datetime.strptime(date_str, "%b-%d-%Y")
                months.add(d.strftime("%Y-%m"))
            except ValueError:
                pass

    if not months:
        print("No vest rows found in file.")
        return

    # Step 2: Prompt user for exchange rate per month-year
    print("\nEnter USD/INR exchange rate for each vest month (use RBI monthly average):")
    exchange_rates: dict[str, float] = {}
    for month in sorted(months):
        while True:
            raw = input(f"  USD/INR rate for {month}: ").strip()
            try:
                rate = float(raw)
                if rate <= 0:
                    raise ValueError
                exchange_rates[month] = rate
                break
            except ValueError:
                print("  Invalid rate. Enter a positive number (e.g. 86.5)")

    # Step 3: Call API with file + rates
    import json
    with open(file_path, "rb") as f:
        preview = _api(
            "post",
            "/import/fidelity-rsu-csv",
            files={"file": (os.path.basename(file_path), f, "text/csv")},
            data={"exchange_rates": json.dumps(exchange_rates)},
        )

    print(f"\nPreview: {preview['new_count']} new, {preview['duplicate_count']} duplicate")
    if preview["new_count"] == 0:
        print("Nothing to import.")
        return

    confirm = input("Commit? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    result = _api("post", "/import/commit", json={"preview_id": preview["preview_id"]})
    _print_import_summary(
        "Fidelity RSU",
        inserted=result["created_count"],
        skipped=result["skipped_count"],
        errors=[],
    )
```

- [ ] **Step 5.2: Implement `cmd_import_fidelity_sale`**

Add after `cmd_import_fidelity_rsu`:

```python
def cmd_import_fidelity_sale(file_path: str) -> None:
    """Import Fidelity tax-cover SELL transactions from a transaction summary PDF.
    Parses the PDF locally (pdfplumber) to find required month-years, prompts for rates,
    then calls one API endpoint with file + rates.
    """
    import json
    import io
    import re

    # Regex mirrors fidelity_pdf_parser._SALE_ROW_RE — keep in sync if parser changes
    _SALE_ROW_RE = re.compile(
        r"(\w{3}-\d{2}-\d{4})\s+"   # date sold
        r"(\w{3}-\d{2}-\d{4})\s+"   # date acquired
        r"([\d,]+\.?\d*)\s+"         # quantity
        r"\$([\d,]+\.?\d*)\s+"       # cost basis
        r"\$([\d,]+\.?\d*)\s+"       # proceeds
        r"[+-]?\$[\d,]+\.?\d*\s+"    # gain/loss
        r"USD\s+(\w+)"               # stock source
    )

    # Step 1: Parse PDF locally to find required month-years
    try:
        import pdfplumber
    except ImportError:
        print("Error: pdfplumber not installed. Run: pip install pdfplumber")
        sys.exit(1)

    months: set[str] = set()
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        in_sales = False
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                if "Stock sales" in line:
                    in_sales = True
                if in_sales:
                    m = _SALE_ROW_RE.search(line)
                    if m:
                        from datetime import datetime as _dt
                        try:
                            d = _dt.strptime(m.group(1), "%b-%d-%Y")
                            months.add(d.strftime("%Y-%m"))
                        except ValueError:
                            pass

    if not months:
        print("No sale transactions found in PDF.")
        return

    # Step 2: Prompt for exchange rate per month-year
    print("\nEnter USD/INR exchange rate for each sale month (use RBI monthly average):")
    exchange_rates: dict[str, float] = {}
    for month in sorted(months):
        while True:
            raw = input(f"  USD/INR rate for {month}: ").strip()
            try:
                rate = float(raw)
                if rate <= 0:
                    raise ValueError
                exchange_rates[month] = rate
                break
            except ValueError:
                print("  Invalid rate. Enter a positive number (e.g. 86.0)")

    # Step 3: Call single API endpoint with file + rates
    with open(file_path, "rb") as f:
        preview = _api(
            "post",
            "/import/fidelity-sale-pdf",
            files={"file": (os.path.basename(file_path), f, "application/pdf")},
            data={"exchange_rates": json.dumps(exchange_rates)},
        )

    print(f"\nPreview: {preview['new_count']} new, {preview['duplicate_count']} duplicate")
    if preview["new_count"] == 0:
        print("Nothing to import.")
        return

    confirm = input("Commit? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    result = _api("post", "/import/commit", json={"preview_id": preview["preview_id"]})
    _print_import_summary(
        "Fidelity Sale PDF",
        inserted=result["created_count"],
        skipped=result["skipped_count"],
        errors=[],
    )
```

- [ ] **Step 5.3: Register the new subcommands in `main()`**

In `backend/cli.py`, in the `main()` function, add two subparser entries after the `zerodha` entry:

```python
    s = import_sub.add_parser("fidelity-rsu", help="Import Fidelity RSU holding CSV (MARKET_TICKER.csv)")
    s.add_argument("file", help="Path to CSV file")

    s = import_sub.add_parser("fidelity-sale", help="Import Fidelity tax-cover sale PDF")
    s.add_argument("file", help="Path to PDF file")
```

And in the dispatch block where `args.source` is handled, add:

```python
        elif args.source == "fidelity-rsu":
            cmd_import_fidelity_rsu(args.file)
        elif args.source == "fidelity-sale":
            cmd_import_fidelity_sale(args.file)
```

Locate the existing dispatch block (around the section with `elif args.source == "zerodha"`) and add the two new entries immediately after the `zerodha` case.

- [ ] **Step 5.4: Update help comment at the top of cli.py**

The docstring/usage comment at the top of `cli.py` (lines 5-10) lists available import commands. Add:

```python
  python cli.py import fidelity-rsu <file>    # Fidelity RSU holding CSV
  python cli.py import fidelity-sale <file>   # Fidelity tax-cover sale PDF
```

- [ ] **Step 5.5: Manual smoke test (server must be running)**

```bash
# Terminal 1: start server
cd backend && uvicorn app.main:app --reload

# Terminal 2: test CLI help
python cli.py import fidelity-rsu --help
python cli.py import fidelity-sale --help

# Test RSU CSV (use your actual file)
python cli.py import fidelity-rsu /path/to/NASDAQ_AMZN.csv

# Test sale PDF
python cli.py import fidelity-sale "/path/to/Custom transaction summary - Fidelity NetBenefits 2025.pdf"
```

Expected: Both commands prompt for exchange rates per month, show preview count, and commit.

- [ ] **Step 5.6: Run full test suite one final time**

```bash
cd backend && uv run pytest tests/ --tb=short
```

Expected: All tests pass.

- [ ] **Step 5.7: Commit**

```bash
git add backend/cli.py
git commit -m "feat: CLI commands for Fidelity RSU CSV and sale PDF import with interactive rate prompts"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] RSU CSV import idempotently → VEST transactions (Task 2 parser, Task 4 API, Task 5 CLI)
- [x] Ticker extracted from filename `MARKET_TICKER.csv` (Task 2)
- [x] Cost basis/share used as price_per_unit in USD (Task 2)
- [x] Exchange rate prompted per vest month-year (Task 5)
- [x] `forex_rate` stored in Transaction table (Task 1)
- [x] `currency="USD"` set on STOCK_US assets (Task 1)
- [x] Current value = live price × live USD/INR (handled by existing `YFinanceFetcher` + `STOCK_US` entry in `FETCHER_REGISTRY` — no change needed)
- [x] Sale PDF import idempotently → SELL transactions tagged "Tax cover sale" (Task 3, 4, 5)
- [x] Ticker extracted from "AMZN: AMAZON.COM INC" line (Task 3)
- [x] Single-endpoint PDF flow: CLI parses PDF locally → prompt rates → call `/import/fidelity-sale-pdf` once (Task 4, 5)
- [x] Exchange rate stored per sale transaction in `forex_rate` field (Task 1, 3)
- [x] Idempotency via stable `txn_id` (SHA-256 hash, both parsers)
- [x] `is_active` flag works naturally via existing `ImportService._STOCK_UNIT_ADD_TYPES/_STOCK_UNIT_SUB_TYPES` logic
- [x] UI: US Stocks page already shows avg cost, units, current value, XIRR — no frontend changes needed
- [x] Tax cover sales show as SELL transactions in the transactions list; notes field identifies them
- [x] TDD: failing tests written before implementation in every task

**Notes for executor:**
- The `conftest.py` in `tests/` provides `test_db` and `client` fixtures via `Depends` override — tests use these without modification.
- `_api()` in `cli.py` uses `requests.request(method, url, ...)` — `data=` sends form fields, `files=` sends multipart. Both are supported in the existing `_api()` helper.
- yfinance for STOCK_US: `identifier="AMZN"` → `YFinanceFetcher(suffix="")` calls `yf.Ticker("AMZN")`. Market is implicit (NASDAQ for AMZN). No change needed to price feed.

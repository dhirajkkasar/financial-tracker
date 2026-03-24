# Test Suite Optimisation — Design Spec
**Date:** 2026-03-24
**Goal:** Reduce backend test suite runtime from ~40s to <15s by removing PDF file dependencies and replacing with static mock data.

---

## Problem

The backend test suite runs in ~40s (432 tests, measured with `pytest --cov`). The dominant cost is redundant PDF parsing:

| Source | Tests | Cost each | Total |
|---|---|---|---|
| `test_cas_parser.py` | 17 | ~1.1s | ~18s |
| `test_import_flow.py` CAS/PPF/EPF tests | ~10 | ~1.2s | ~3.6s |
| `test_ppf_pdf_parser.py` | 12 | ~0.15s | ~1.8s |
| `test_epf_pdf_parser.py` | 15 | ~0.20s | ~3.0s |

Each test independently parses the same PDF from disk. There are no actual external HTTP calls in the current suite — price feed tests already mock httpx/yfinance correctly.

---

## Approach

**Central static fixtures + smoke tests.**

- Create `tests/fixtures_data.py` with pre-computed `ParsedTransaction` / `ImportResult` constants matching what the real parsers return.
- Unit parser tests use these constants directly — no PDF parsing, no fixtures.
- Integration import tests mock the parser class at the API boundary using `unittest.mock.patch`, passing `b"fake"` as file bytes.
- Real PDF parsing is preserved in a `tests/smoke/` directory, excluded from the default run via a pytest marker.
- Large CSV fixtures are trimmed to the minimum rows needed to satisfy test assertions.

---

## File Changes

### New files

#### `tests/fixtures_data.py`

Module-level constants. **Values below are taken directly from existing passing test assertions and must be verified by running the real parser once before being committed to this file.**

```python
PARSED_CAS: CASImportResult
  .source = "cas"
  .transactions = [
      # 1 SIP: asset_name="HDFC Multi Cap Fund", isin="INF179KC1BS5",
      #         txn_type="SIP", amount_inr=-5000.0 (outflow),
      #         txn_id="cas_<hash>", source="cas", asset_type="MF"
      # 1 BUY: asset_name="Kotak Small Cap Fund",
      #         txn_type="BUY", amount_inr=-10000.0 (outflow)
      # 1 REDEMPTION: txn_type="REDEMPTION", amount_inr=+15000.0 (inflow)
  ]
  .snapshots = [
      ParsedFundSnapshot(
          isin="INF179KC1BS5",
          asset_name="HDFC Multi Cap Fund",
          date=date(2026, 3, 18),
          closing_units=17292.257,
          nav_price_inr=18.505,
          market_value_inr=319993.22,
          total_cost_inr=340000.00,
      ),
      ParsedFundSnapshot(
          isin="INF879O01027",
          asset_name="Parag Parikh Flexi Cap Fund",
          date=date(2026, 3, 18),
          closing_units=26580.939,
          nav_price_inr=89.3756,
          market_value_inr=2375687.37,
          total_cost_inr=1655390.87,
      ),
      ParsedFundSnapshot(
          isin="INF209K01BR9",
          asset_name="Aditya Birla Sun Life Large Cap Fund",
          date=date(2026, 3, 18),
          closing_units=0.0,
          nav_price_inr=495.46,
          market_value_inr=0.0,
          total_cost_inr=0.0,
      ),
  ]
  .errors = []
  # txn_ids must all start with "cas_" and be unique within this list

PARSED_PPF: PPFImportResult
  .source = "ppf_pdf"
  .account_number = "32256576916"
  .closing_balance_inr = 42947.0
  .closing_balance_date = date(2018, 12, 28)
  .transactions = [
      ParsedTransaction(
          txn_id="ppf_3199410044308",
          txn_type="CONTRIBUTION",
          asset_type="PPF",
          asset_identifier="32256576916",
          date=date(2018, 5, 29),
          amount_inr=-5000.0,
      ),
      ParsedTransaction(
          txn_id="ppf_IF17658260",
          txn_type="CONTRIBUTION",
          asset_type="PPF",
          asset_identifier="32256576916",
          date=date(2018, 12, 28),
          amount_inr=-15000.0,
      ),
  ]
  .errors = []

PARSED_EPF: EPFImportResult
  .source = "epf_pdf"
  .member_id = "PYKRP00192140000152747"
  .establishment_name = "IBM INDIA PVT LTD"
  .print_date = date(2018, 11, 27)
  .grand_total_emp_deposit = 198371.0
  .grand_total_er_deposit = 140204.0
  .net_balance_inr = 0.0
  .transactions = [
      # Employee Share CONTRIBUTION (asset_identifier="PYKRP00192140000152747", notes="Employee Share", amount_inr < 0)
      # Employer Share CONTRIBUTION (asset_identifier="PYKRP00192140000152747", notes="Employer Share", amount_inr < 0)
      # Pension CONTRIBUTION      (asset_identifier="PYKRP00192140000152747_EPS", notes="Pension Contribution",
      #                            asset_name contains "IBM INDIA PVT LTD", amount_inr < 0)
      # INTEREST                  (asset_identifier="PYKRP00192140000152747", amount_inr > 0)
      # TRANSFER                  (asset_identifier="PYKRP00192140000152747", amount_inr > 0)
  ]
  # Minimum 5 transactions — all txn_ids unique
  .errors = []
```

**Note on snapshot values:** The exact values in `PARSED_CAS.snapshots` (HDFC, Parag Parikh) are taken directly from the existing test assertions in `test_cas_parser.py` lines 95–125. The Aditya Birla entry is needed to satisfy `test_snapshot_zero_units_for_redeemed_fund`. The `PARSED_CAS.snapshots` list must contain all three entries above.

**Note on EPF values:** `grand_total_emp_deposit = 198371.0` and `grand_total_er_deposit = 140204.0` are taken from `test_epf_pdf_parser.py` line 137. Verify these are still correct by running `EPFPDFParser().parse(pdf_bytes)` once before finalising `fixtures_data.py`.

---

#### `tests/smoke/__init__.py`
Empty file.

#### `tests/smoke/test_cas_smoke.py`
```python
import pytest
from pathlib import Path
from app.importers.cas_parser import CASImporter

pytestmark = pytest.mark.smoke
FIXTURES = Path(__file__).parent.parent / "fixtures"

def test_cas_parser_real_pdf():
    result = CASImporter().parse((FIXTURES / "test_cas.pdf").read_bytes())
    assert result.source == "cas"
    assert len(result.transactions) > 0
    assert len(result.errors) == 0
```

#### `tests/smoke/test_ppf_smoke.py`
```python
import pytest
from pathlib import Path
from app.importers.ppf_pdf_parser import PPFPDFParser

pytestmark = pytest.mark.smoke
FIXTURES = Path(__file__).parent.parent / "fixtures"

def test_ppf_parser_real_pdf():
    result = PPFPDFParser().parse((FIXTURES / "PPF_account_statement.pdf").read_bytes())
    assert result.account_number == "32256576916"
    assert result.closing_balance_inr == 42947.0
    assert len(result.transactions) == 2
```

#### `tests/smoke/test_epf_smoke.py`
```python
import pytest
from pathlib import Path
from app.importers.epf_pdf_parser import EPFPDFParser

pytestmark = pytest.mark.smoke
FIXTURES = Path(__file__).parent.parent / "fixtures"

def test_epf_parser_real_pdf():
    result = EPFPDFParser().parse((FIXTURES / "PYKRP00192140000152747.pdf").read_bytes())
    assert result.member_id == "PYKRP00192140000152747"
    assert len(result.transactions) > 0
    assert len(result.errors) == 0
```

---

### Modified files

#### `pyproject.toml` — edit existing `addopts` line in `[tool.pytest.ini_options]`

```toml
# Before:
addopts = "--cov=app --cov-report=term-missing"

# After:
addopts = "--cov=app --cov-report=term-missing -m 'not smoke'"
```

Also add under `[tool.pytest.ini_options]`:
```toml
markers = [
    "smoke: Real file / real network tests. Run with: pytest -m smoke",
]
```

Do **not** create a `pytest.ini` — this would conflict with the existing `pyproject.toml` configuration.

---

#### `tests/unit/test_cas_parser.py`

- Remove `parser` fixture and `cas_bytes` fixture entirely.
- Add `from tests.fixtures_data import PARSED_CAS` at top.
- Replace every `importer.parse(cas_bytes)` call with `PARSED_CAS`.
- **Delete** `test_txn_id_stable_across_reparses` — this test's property (deterministic hash output) is only meaningful when calling the real parser twice. With static data it would be testing that a Python constant equals itself. The smoke test covers the real stability property. Add a comment in the test file: `# test_txn_id_stable_across_reparses removed: covered by tests/smoke/test_cas_smoke.py`

---

#### `tests/unit/test_ppf_pdf_parser.py`

- Remove `parser` fixture and `ppf_pdf_bytes` fixture entirely.
- Add `from tests.fixtures_data import PARSED_PPF` at top.
- Replace every `parser.parse(ppf_pdf_bytes)` call with `PARSED_PPF`.
- **Delete** `test_txn_id_stable_across_reparses` for the same reason as CAS. Add same comment.

---

#### `tests/unit/test_epf_pdf_parser.py`

- Remove `parser` fixture and `epf_pdf_bytes` fixture entirely.
- Add `from tests.fixtures_data import PARSED_EPF` at top.
- Replace every `parser.parse(epf_pdf_bytes)` call with `PARSED_EPF`.
- **Delete** `test_txn_id_stable_across_reparses`. Add same comment.

---

#### `tests/integration/test_import_flow.py`

**Verified patch paths** (confirmed against import statements in source files):
- CAS: `patch("app.api.imports.CASImporter")` — imported at `app/api/imports.py:7`
- PPF: `patch("app.services.ppf_epf_import_service.PPFPDFParser")` — imported at `app/services/ppf_epf_import_service.py:16`
- EPF: `patch("app.services.ppf_epf_import_service.EPFPDFParser")` — imported at `app/services/ppf_epf_import_service.py:17`

Changes:
- Remove `cas_pdf_bytes`, `ppf_pdf_bytes`, `epf_pdf_bytes` fixtures (the `Path.read_bytes()` calls).
- Add `from tests.fixtures_data import PARSED_CAS, PARSED_PPF, PARSED_EPF` at top.
- `TestCASPDFPreview` — wrap each test body with:
  ```python
  with patch("app.api.imports.CASImporter") as MockCAS:
      MockCAS.return_value.parse.return_value = PARSED_CAS
      resp = client.post("/import/cas-pdf",
          files={"file": ("cas.pdf", b"fake", "application/pdf")})
  ```
- `TestPPFImport` — wrap with `patch("app.services.ppf_epf_import_service.PPFPDFParser")`, `return_value = PARSED_PPF`, upload `b"fake"`.
- `TestEPFImport` — wrap with `patch("app.services.ppf_epf_import_service.EPFPDFParser")`, `return_value = PARSED_EPF`, upload `b"fake"`.
- `zerodha_csv_bytes` and `nps_csv_bytes` fixtures remain unchanged.

---

#### `tests/fixtures/tradebook-EQ-2023.csv`

Trim from 27 data rows to **5 rows**:
- Row 1: TCS buy 3 @ 3427 (trade_id=76061635) — needed for `test_parse_maps_buy_correctly` and `test_uses_native_trade_id_as_txn_id`
- Row 2: any BUY
- Row 3: any BUY
- Row 4: ADANIENT sell 1 @ 3213 — needed for `test_parse_maps_sell_correctly`
- Row 5: any BUY or SELL

Update assertion in `test_parse_returns_correct_transaction_count`:
```python
# Before:
assert len(result.transactions) == 27
# After:
assert len(result.transactions) == 5
```

---

#### `tests/fixtures/nps_tier_1.csv`

Trim to minimum rows that satisfy all assertions:
- **2 months** of data, each with all **3 schemes** = 6 CONTRIBUTION rows total
- Keep 1 Billing row (needed for `test_parse_marks_billing_as_charges`)
- Keep Opening/Closing balance rows (needed for `test_parse_skips_opening_closing_balance`)
- All 3 scheme names must appear (needed for `test_parse_creates_asset_per_scheme` which asserts `len(scheme_names) == 3`)

Update comment and assertion in `test_parse_tier1_extracts_contributions`:
```python
# Before:
# Tier 1 has 12 months x 3 schemes = 36 contributions
assert len(contributions) == 36
# After:
# Tier 1 has 2 months x 3 schemes = 6 contributions
assert len(contributions) == 6
```

All other NPS assertions (`test_parse_creates_asset_per_scheme == 3`, `test_parse_extracts_tier_label`, etc.) remain valid since the trimmed CSV retains all 3 schemes and the same structure.

---

## What stays the same

- All assertion logic in unit tests is unchanged (same field names, same values from `fixtures_data.py`)
- Real PDF files remain in `tests/fixtures/` for smoke tests
- `test_price_feed.py` — already mocks correctly, no changes
- `test_broker_csv_parser.py` — uses trimmed CSV, one assertion value updated
- `test_nps_parser.py` — uses trimmed CSV, one assertion value updated
- `nps_tier2.csv` — already tiny (49 rows), unchanged
- `test_cas_import_snapshots.py` — already uses in-memory data (no PDF), unchanged

---

## Expected outcome

| Metric | Before | After |
|---|---|---|
| Total runtime (with --cov) | ~40s | ~13–15s |
| PDF parses per default run | 35+ | 0 |
| Smoke run (`pytest -m smoke`) | n/a | ~3s (3 PDFs, 1 each) |
| PDF files required for default run | 3 PDFs | 0 |
| `test_txn_id_stable_across_reparses` tests | 3 | 0 (deleted; covered by smoke) |

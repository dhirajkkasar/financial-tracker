# Quick-Start Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `python cli.py quick-start` — an interactive wizard that guides a first-time user through importing all their investments (PPF, EPF, MF, NPS, Indian Stocks, FD, RD, Gold, Real Estate) without knowing individual CLI commands.

**Architecture:** Wizard logic lives in a new `backend/quick_start.py` module. `cli.py` is only changed to add the dispatcher and remove deprecated `add rsu`/`add us-stock` from the docstring. `quick_start.py` imports the existing `cmd_*` functions from `cli.py` so there is zero logic duplication. All interactive prompts use `input()` — no new dependencies.

**Tech Stack:** Python 3.11+, `requests` (already used), `pytest` + `unittest.mock` for tests. No new packages.

---

### Task 1: Write failing tests for `_check_db_empty`

**Files:**
- Create: `backend/tests/unit/test_quick_start.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_quick_start.py
import pytest
from unittest.mock import patch


# --- _check_db_empty ---

def test_check_db_empty_exits_with_help_when_assets_exist(capsys):
    with patch("quick_start._api", return_value=[{"id": 1}]):
        with pytest.raises(SystemExit) as exc_info:
            import quick_start
            quick_start._check_db_empty()
        assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "existing data" in captured.out
    assert "python cli.py import ppf" in captured.out
    assert "python cli.py add fd" in captured.out


def test_check_db_empty_returns_when_no_assets():
    with patch("quick_start._api", return_value=[]):
        import quick_start
        # Should not raise
        quick_start._check_db_empty()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -v
```

Expected: `ModuleNotFoundError: No module named 'quick_start'`

---

### Task 2: Create `quick_start.py` skeleton and implement `_check_db_empty`

**Files:**
- Create: `backend/quick_start.py`

- [ ] **Step 1: Create the file**

```python
# backend/quick_start.py
"""
Interactive first-time setup wizard.
Guides the user through importing all investment types without knowing CLI commands.
Called via: python cli.py quick-start
"""
import os
import sys

from cli import (
    _api,
    cmd_import_ppf,
    cmd_import_epf,
    cmd_import_cas,
    cmd_import_nps,
    cmd_import_broker_csv,
    cmd_add_fd,
    cmd_add_rd,
    cmd_add_gold,
    cmd_add_real_estate,
)

_HELP_TEXT = """\
Your database already has existing data. Use individual commands to add more:

  Import commands (server must be running):
    python cli.py import ppf <file> --pan <PAN>
    python cli.py import epf <file> --pan <PAN>
    python cli.py import cas <file> --pan <PAN>
    python cli.py import nps <file> --pan <PAN>
    python cli.py import zerodha <file> --pan <PAN>

  Manual add commands:
    python cli.py add fd --name ... --pan <PAN> --bank ... --principal ... --rate ... --start ... --maturity ... --compounding ...
    python cli.py add rd --name ... --pan <PAN> --bank ... --installment ... --rate ... --start ... --maturity ... --compounding ...
    python cli.py add gold --name ... --pan <PAN> --date ... --units ... --price ...
    python cli.py add real-estate --name ... --pan <PAN> --purchase-amount ... --purchase-date ... --current-value ... --value-date ...
"""


def _check_db_empty():
    """Exit with help text if any assets already exist in the DB."""
    assets = _api("get", "/assets")
    if assets:
        print(_HELP_TEXT)
        sys.exit(0)


def _resolve_member():
    pass


def _ask_member(members, label):
    pass


def _section_file(label, import_fn, members, single_member_id):
    pass


def _section_manual(label, add_fn, members, single_member_id):
    pass


def _prompt(prompt_text, cast=str, validate=None):
    pass


def _add_fd_interactive(member_id):
    pass


def _add_rd_interactive(member_id):
    pass


def _add_gold_interactive(member_id):
    pass


def _add_real_estate_interactive(member_id):
    pass


def run():
    pass
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py::test_check_db_empty_exits_with_help_when_assets_exist tests/unit/test_quick_start.py::test_check_db_empty_returns_when_no_assets -v
```

Expected: PASS (both tests green)

- [ ] **Step 3: Commit**

```bash
git add backend/quick_start.py backend/tests/unit/test_quick_start.py
git commit -m "feat: add quick_start.py skeleton with _check_db_empty"
```

---

### Task 3: Write failing tests for `_resolve_member` and `_ask_member`

**Files:**
- Modify: `backend/tests/unit/test_quick_start.py`

- [ ] **Step 1: Append these tests**

```python
# --- _resolve_member ---

def test_resolve_member_creates_member_when_none_exist(capsys):
    with patch("quick_start._api") as mock_api:
        mock_api.side_effect = [
            [],  # GET /members → empty
            {"id": 1, "pan": "ABCDE1234F", "name": "Dhiraj"},  # POST /members
        ]
        with patch("builtins.input", side_effect=["ABCDE1234F", "Dhiraj"]):
            import quick_start
            members, single_id = quick_start._resolve_member()
    assert single_id == 1
    assert len(members) == 1
    assert members[0]["pan"] == "ABCDE1234F"


def test_resolve_member_auto_selects_single_member(capsys):
    with patch("quick_start._api", return_value=[{"id": 2, "pan": "ZZZZZ9999Z", "name": "Priya"}]):
        import quick_start
        members, single_id = quick_start._resolve_member()
    assert single_id == 2
    captured = capsys.readouterr()
    assert "Using: Priya" in captured.out


def test_resolve_member_returns_none_for_multi_member(capsys):
    two_members = [
        {"id": 1, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 2, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    with patch("quick_start._api", return_value=two_members):
        import quick_start
        members, single_id = quick_start._resolve_member()
    assert single_id is None
    assert len(members) == 2


# --- _ask_member ---

def test_ask_member_returns_correct_member_id():
    members = [
        {"id": 10, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 20, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    with patch("builtins.input", return_value="2"):
        import quick_start
        result = quick_start._ask_member(members, "EPF")
    assert result == 20


def test_ask_member_retries_on_invalid_input():
    members = [
        {"id": 10, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 20, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    with patch("builtins.input", side_effect=["0", "abc", "1"]):
        import quick_start
        result = quick_start._ask_member(members, "FD")
    assert result == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -k "resolve_member or ask_member" -v
```

Expected: FAIL — functions return `None`

---

### Task 4: Implement `_resolve_member` and `_ask_member`

**Files:**
- Modify: `backend/quick_start.py`

- [ ] **Step 1: Replace the stub implementations**

```python
def _resolve_member() -> tuple[list[dict], int | None]:
    """
    Set up member for the session.
    Returns (all_members, single_member_id).
    single_member_id is None when there are 2+ members (caller must prompt per file/entry).
    """
    members = _api("get", "/members")
    if len(members) == 0:
        print("No members found. Let's create one first.")
        pan = input("PAN (e.g. ABCDE1234F): ").strip().upper()
        name = input("Name: ").strip()
        if not pan or not name:
            sys.exit("PAN and name are required.")
        result = _api("post", "/members", json={"pan": pan, "name": name})
        print(f"  → created member: {result['name']} (PAN: {result['pan']})")
        return [result], result["id"]
    elif len(members) == 1:
        m = members[0]
        print(f"Using: {m['name']} (PAN: {m['pan']})")
        return members, m["id"]
    else:
        print("Multiple members found:")
        for i, m in enumerate(members, 1):
            print(f"  {i}. {m['name']} (PAN: {m['pan']})")
        return members, None


def _ask_member(members: list[dict], label: str) -> int:
    """Prompt user to pick a member from the list. Returns member_id."""
    print(f"\nWhich member does this {label} belong to?")
    for i, m in enumerate(members, 1):
        print(f"  {i}. {m['name']} (PAN: {m['pan']})")
    while True:
        raw = input(f"Enter number [1-{len(members)}]: ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(members):
                return members[idx]["id"]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(members)}.")
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -k "resolve_member or ask_member" -v
```

Expected: PASS (all 5 tests green)

- [ ] **Step 3: Commit**

```bash
git add backend/quick_start.py backend/tests/unit/test_quick_start.py
git commit -m "feat: implement _resolve_member and _ask_member"
```

---

### Task 5: Write failing tests for `_section_file`

**Files:**
- Modify: `backend/tests/unit/test_quick_start.py`

- [ ] **Step 1: Append these tests**

```python
# --- _section_file ---

def test_section_file_skips_when_user_says_no(capsys):
    import quick_start
    mock_import = MagicMock()
    with patch("builtins.input", return_value="n"):
        quick_start._section_file("PPF", mock_import, [], 1)
    mock_import.assert_not_called()


def test_section_file_imports_one_file_then_stops():
    import quick_start
    mock_import = MagicMock()
    with patch("builtins.input", side_effect=["y", "/tmp/ppf.csv", "n"]), \
         patch("os.path.isfile", return_value=True):
        quick_start._section_file("PPF", mock_import, [], 1)
    mock_import.assert_called_once_with("/tmp/ppf.csv", 1)


def test_section_file_imports_multiple_files():
    import quick_start
    mock_import = MagicMock()
    with patch("builtins.input", side_effect=["y", "/tmp/a.csv", "y", "/tmp/b.csv", "n"]), \
         patch("os.path.isfile", return_value=True):
        quick_start._section_file("EPF", mock_import, [], 1)
    assert mock_import.call_count == 2
    mock_import.assert_any_call("/tmp/a.csv", 1)
    mock_import.assert_any_call("/tmp/b.csv", 1)


def test_section_file_retries_on_missing_file():
    import quick_start
    mock_import = MagicMock()
    # First path doesn't exist, second does
    with patch("builtins.input", side_effect=["y", "/bad/path.csv", "/tmp/good.csv", "n"]), \
         patch("os.path.isfile", side_effect=[False, True]):
        quick_start._section_file("PPF", mock_import, [], 1)
    mock_import.assert_called_once_with("/tmp/good.csv", 1)


def test_section_file_prompts_member_when_multi_member():
    import quick_start
    mock_import = MagicMock()
    members = [
        {"id": 1, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 2, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    # answers: has investments? y, member=1, file path, another? n
    with patch("builtins.input", side_effect=["y", "1", "/tmp/epf.pdf", "n"]), \
         patch("os.path.isfile", return_value=True):
        quick_start._section_file("EPF", mock_import, members, None)
    mock_import.assert_called_once_with("/tmp/epf.pdf", 1)
```

Add `from unittest.mock import MagicMock` to the imports at the top of the test file.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -k "section_file" -v
```

Expected: FAIL — `_section_file` is a stub returning `None`

---

### Task 6: Implement `_section_file`

**Files:**
- Modify: `backend/quick_start.py`

- [ ] **Step 1: Replace the stub**

```python
def _section_file(label: str, import_fn, members: list[dict], single_member_id: int | None):
    """Handle one file-based asset type — loop until user says no more files."""
    answer = input(f"\nDo you have {label} investments? [y/n]: ").strip().lower()
    if answer != "y":
        return

    while True:
        if single_member_id is None:
            member_id = _ask_member(members, label)
        else:
            member_id = single_member_id

        while True:
            file_path = os.path.expanduser(input(f"Enter file path for {label}: ").strip())
            if os.path.isfile(file_path):
                break
            print(f"  File not found: {file_path}. Please try again.")

        try:
            import_fn(file_path, member_id)
        except SystemExit as exc:
            print(f"  Import failed: {exc}")

        again = input(f"Import another file for {label}? [y/N]: ").strip().lower()
        if again != "y":
            break
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -k "section_file" -v
```

Expected: PASS (all 5 tests green)

- [ ] **Step 3: Commit**

```bash
git add backend/quick_start.py backend/tests/unit/test_quick_start.py
git commit -m "feat: implement _section_file with file retry and multi-member support"
```

---

### Task 7: Write failing tests for manual entry helpers

**Files:**
- Modify: `backend/tests/unit/test_quick_start.py`

- [ ] **Step 1: Append these tests**

```python
# --- _prompt helper ---

def test_prompt_returns_string_by_default():
    import quick_start
    with patch("builtins.input", return_value="  HDFC FD  "):
        result = quick_start._prompt("Name: ")
    assert result == "HDFC FD"


def test_prompt_casts_to_float():
    import quick_start
    with patch("builtins.input", return_value="7.5"):
        result = quick_start._prompt("Rate: ", cast=float)
    assert result == 7.5


def test_prompt_retries_on_invalid_cast():
    import quick_start
    with patch("builtins.input", side_effect=["abc", "-1", "500000"]):
        result = quick_start._prompt("Amount: ", cast=float, validate=lambda x: x > 0)
    assert result == 500000.0


# --- _add_fd_interactive ---

def test_add_fd_interactive_calls_cmd_add_fd():
    import quick_start
    inputs = [
        "HDFC FD 2024",   # name
        "HDFC",           # bank
        "500000",         # principal
        "7.1",            # rate
        "2024-01-15",     # start
        "2025-01-15",     # maturity
        "QUARTERLY",      # compounding
    ]
    with patch("builtins.input", side_effect=inputs), \
         patch("quick_start.cmd_add_fd") as mock_cmd:
        quick_start._add_fd_interactive(member_id=1)
    mock_cmd.assert_called_once_with(
        "HDFC FD 2024", "HDFC", 500000.0, 7.1,
        "2024-01-15", "2025-01-15", "QUARTERLY", 1
    )


# --- _add_rd_interactive ---

def test_add_rd_interactive_calls_cmd_add_rd():
    import quick_start
    inputs = [
        "SBI RD 2024",   # name
        "SBI",           # bank
        "10000",         # installment
        "6.5",           # rate
        "2024-01-01",    # start
        "2026-01-01",    # maturity
        "QUARTERLY",     # compounding
    ]
    with patch("builtins.input", side_effect=inputs), \
         patch("quick_start.cmd_add_rd") as mock_cmd:
        quick_start._add_rd_interactive(member_id=2)
    mock_cmd.assert_called_once_with(
        "SBI RD 2024", "SBI", 10000.0, 6.5,
        "2024-01-01", "2026-01-01", "QUARTERLY", 2
    )


# --- _add_gold_interactive ---

def test_add_gold_interactive_calls_cmd_add_gold():
    import quick_start
    inputs = [
        "Digital Gold",  # name
        "2023-06-01",    # date
        "10",            # units
        "5800",          # price
    ]
    with patch("builtins.input", side_effect=inputs), \
         patch("quick_start.cmd_add_gold") as mock_cmd:
        quick_start._add_gold_interactive(member_id=1)
    mock_cmd.assert_called_once_with("Digital Gold", "2023-06-01", 10.0, 5800.0, 1)


# --- _add_real_estate_interactive ---

def test_add_real_estate_interactive_calls_cmd_add_real_estate():
    import quick_start
    inputs = [
        "Venezia Flat",   # name
        "7500000",        # purchase amount
        "2020-11-09",     # purchase date
        "12000000",       # current value
        "2024-01-01",     # value date
    ]
    with patch("builtins.input", side_effect=inputs), \
         patch("quick_start.cmd_add_real_estate") as mock_cmd:
        quick_start._add_real_estate_interactive(member_id=3)
    mock_cmd.assert_called_once_with(
        "Venezia Flat", 7500000.0, "2020-11-09", 12000000.0, "2024-01-01", 3
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -k "prompt or fd_interactive or rd_interactive or gold_interactive or real_estate_interactive" -v
```

Expected: FAIL — stubs return `None`

---

### Task 8: Implement `_prompt` and manual entry helpers

**Files:**
- Modify: `backend/quick_start.py`

- [ ] **Step 1: Replace the stubs**

```python
def _prompt(prompt_text: str, cast=str, validate=None):
    """Prompt user for input with optional type casting and validation. Retries on bad input."""
    while True:
        raw = input(prompt_text).strip()
        try:
            value = cast(raw)
            if validate is not None and not validate(value):
                raise ValueError
            return value
        except (ValueError, TypeError):
            print("  Invalid input. Please try again.")


def _add_fd_interactive(member_id: int):
    name = _prompt("Name (e.g. HDFC FD 2024): ")
    bank = _prompt("Bank: ")
    principal = _prompt("Principal amount (INR): ", cast=float, validate=lambda x: x > 0)
    rate = _prompt("Interest rate (%): ", cast=float, validate=lambda x: x > 0)
    start = _prompt("Start date (YYYY-MM-DD): ")
    maturity = _prompt("Maturity date (YYYY-MM-DD): ")
    compounding = _prompt("Compounding [MONTHLY/QUARTERLY/HALF_YEARLY/YEARLY] (default QUARTERLY): ") or "QUARTERLY"
    cmd_add_fd(name, bank, principal, rate, start, maturity, compounding, member_id)


def _add_rd_interactive(member_id: int):
    name = _prompt("Name (e.g. SBI RD 2024): ")
    bank = _prompt("Bank: ")
    installment = _prompt("Monthly installment (INR): ", cast=float, validate=lambda x: x > 0)
    rate = _prompt("Interest rate (%): ", cast=float, validate=lambda x: x > 0)
    start = _prompt("Start date (YYYY-MM-DD): ")
    maturity = _prompt("Maturity date (YYYY-MM-DD): ")
    compounding = _prompt("Compounding [MONTHLY/QUARTERLY/HALF_YEARLY/YEARLY] (default QUARTERLY): ") or "QUARTERLY"
    cmd_add_rd(name, bank, installment, rate, start, maturity, compounding, member_id)


def _add_gold_interactive(member_id: int):
    name = _prompt("Name (e.g. Digital Gold): ")
    date = _prompt("Purchase date (YYYY-MM-DD): ")
    units = _prompt("Units (grams): ", cast=float, validate=lambda x: x > 0)
    price = _prompt("Price per unit (INR/gram): ", cast=float, validate=lambda x: x > 0)
    cmd_add_gold(name, date, units, price, member_id)


def _add_real_estate_interactive(member_id: int):
    name = _prompt("Name (e.g. Venezia Flat): ")
    purchase_amount = _prompt("Purchase amount (INR): ", cast=float, validate=lambda x: x > 0)
    purchase_date = _prompt("Purchase date (YYYY-MM-DD): ")
    current_value = _prompt("Current value (INR): ", cast=float, validate=lambda x: x > 0)
    value_date = _prompt("Value date (YYYY-MM-DD): ")
    cmd_add_real_estate(name, purchase_amount, purchase_date, current_value, value_date, member_id)
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -k "prompt or fd_interactive or rd_interactive or gold_interactive or real_estate_interactive" -v
```

Expected: PASS (all tests green)

- [ ] **Step 3: Commit**

```bash
git add backend/quick_start.py backend/tests/unit/test_quick_start.py
git commit -m "feat: implement _prompt and manual entry helpers for FD, RD, Gold, Real Estate"
```

---

### Task 9: Write failing tests for `_section_manual`

**Files:**
- Modify: `backend/tests/unit/test_quick_start.py`

- [ ] **Step 1: Append these tests**

```python
# --- _section_manual ---

def test_section_manual_skips_when_user_says_no():
    import quick_start
    mock_add = MagicMock()
    with patch("builtins.input", return_value="n"):
        quick_start._section_manual("FD", mock_add, [], 1)
    mock_add.assert_not_called()


def test_section_manual_adds_one_then_stops():
    import quick_start
    mock_add = MagicMock()
    with patch("builtins.input", side_effect=["y", "n"]):
        quick_start._section_manual("FD", mock_add, [], 1)
    mock_add.assert_called_once_with(1)


def test_section_manual_adds_multiple():
    import quick_start
    mock_add = MagicMock()
    with patch("builtins.input", side_effect=["y", "y", "n"]):
        quick_start._section_manual("FD", mock_add, [], 1)
    assert mock_add.call_count == 2


def test_section_manual_prompts_member_when_multi_member():
    import quick_start
    mock_add = MagicMock()
    members = [
        {"id": 1, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 2, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    # has investments? y, member=2, add another? n
    with patch("builtins.input", side_effect=["y", "2", "n"]):
        quick_start._section_manual("FD", mock_add, members, None)
    mock_add.assert_called_once_with(2)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -k "section_manual" -v
```

Expected: FAIL — stub returns `None`

---

### Task 10: Implement `_section_manual` and `run()`

**Files:**
- Modify: `backend/quick_start.py`

- [ ] **Step 1: Replace `_section_manual` stub**

```python
def _section_manual(label: str, add_fn, members: list[dict], single_member_id: int | None):
    """Handle one manually-entered asset type — loop until user says no more."""
    answer = input(f"\nDo you have {label} investments? [y/n]: ").strip().lower()
    if answer != "y":
        return

    while True:
        if single_member_id is None:
            member_id = _ask_member(members, label)
        else:
            member_id = single_member_id

        try:
            add_fn(member_id)
        except SystemExit as exc:
            print(f"  Add failed: {exc}")

        again = input(f"Add another {label}? [y/N]: ").strip().lower()
        if again != "y":
            break
```

- [ ] **Step 2: Replace `run()` stub**

```python
def run():
    """Entry point for the quick-start wizard. Called from cli.py dispatcher."""
    print("\n=== Portfolio Quick-Start ===")
    print("This wizard will guide you through importing all your investments.\n")

    _check_db_empty()
    members, single_member_id = _resolve_member()

    # File-based asset types
    _section_file("PPF", cmd_import_ppf, members, single_member_id)
    _section_file("EPF", cmd_import_epf, members, single_member_id)
    _section_file(
        "Mutual Funds (CAS PDF)",
        cmd_import_cas,
        members, single_member_id,
    )
    _section_file("NPS", cmd_import_nps, members, single_member_id)
    _section_file(
        "Indian Stocks (Zerodha CSV)",
        lambda path, mid: cmd_import_broker_csv(path, "zerodha", mid),
        members, single_member_id,
    )

    # Manual asset types
    _section_manual("FD", _add_fd_interactive, members, single_member_id)
    _section_manual("RD", _add_rd_interactive, members, single_member_id)
    _section_manual("Gold", _add_gold_interactive, members, single_member_id)
    _section_manual("Real Estate", _add_real_estate_interactive, members, single_member_id)

    print("\nQuick-start complete! Next steps:")
    print("  python cli.py refresh-prices   # fetch current prices for all assets")
    print("  python cli.py snapshot         # save a portfolio snapshot")
```

- [ ] **Step 3: Run all quick_start tests**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -v
```

Expected: PASS (all tests green)

- [ ] **Step 4: Commit**

```bash
git add backend/quick_start.py backend/tests/unit/test_quick_start.py
git commit -m "feat: implement _section_manual and run() — quick-start wizard complete"
```

---

### Task 11: Wire `cli.py` dispatcher and clean up docstring

**Files:**
- Modify: `backend/cli.py`

- [ ] **Step 1: Add `quick-start` to the module docstring**

In `backend/cli.py`, find the docstring at the top (lines 1-45). After the line:
```
  python cli.py list assets
```
Add:
```
  python cli.py quick-start
```

- [ ] **Step 2: Remove `add rsu` and `add us-stock` from the docstring**

In the same docstring, remove these two lines entirely:
```
  python cli.py add rsu   --name "AMZN RSU" --pan ABCDE1234F --date 2024-03-01 --units 10 --price 180.50 --forex 83.5 --notes "Perquisite tax: ..."
  python cli.py add us-stock --name "Apple" --pan ABCDE1234F --identifier AAPL --date 2023-01-15 --units 5 --price 142.50 --forex 82.0
```
Also check ReadMe.md file and claude.md file if it mentions these commands and remove it.

- [ ] **Step 3: Add `quick-start` subcommand to `build_parser()`**

In `build_parser()` (around line 911 where other utilities are registered), add before the `return parser` line:

```python
    sub.add_parser("quick-start", help="Interactive first-time setup wizard")
```

- [ ] **Step 4: Add dispatcher in `main()`**

In `main()` (around line 1038, after the `backup` elif block and before the `else`), add:

```python
    elif args.command == "quick-start":
        from quick_start import run
        run()
```

- [ ] **Step 5: Run the full test suite to verify nothing is broken**

```bash
cd backend
uv run pytest tests/unit/ -v
```

Expected: all existing tests still pass, all quick_start tests pass

- [ ] **Step 6: Smoke test the dispatcher (server must be running)**

```bash
cd backend
uvicorn app.main:app --reload &
sleep 2
python cli.py quick-start --help
```

Expected: shows help text for `quick-start` subcommand (no error)

- [ ] **Step 7: Commit**

```bash
git add backend/cli.py
git commit -m "feat: wire quick-start to cli.py dispatcher, remove deprecated rsu/us-stock add commands from docs"
```

---

### Task 12: Final verification

- [ ] **Step 1: Run full backend test suite with coverage**

```bash
cd backend
uv run pytest --cov=app --cov-report=term-missing -v
```

Expected: all tests pass, no regressions

- [ ] **Step 2: Run quick_start tests specifically**

```bash
cd backend
uv run pytest tests/unit/test_quick_start.py -v
```

Expected: all tests pass

- [ ] **Step 3: Update ReadMe.md and Claude.md**

    Update ReadMe.md file about quick-start command and setting up things quickly to use this app. Update claude's context file (claude.md) about new command (can use claude-md-management skill)

- [ ] **Step 4: Commit if any cleanup was needed, otherwise done**

```bash
git add -p  # stage only if there are uncommitted changes
git commit -m "chore: final cleanup after quick-start implementation"
```

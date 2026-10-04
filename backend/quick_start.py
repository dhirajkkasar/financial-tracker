"""
Interactive first-time setup wizard.
Guides the user through importing all investment types without knowing CLI commands.
Called via: python cli.py quick-start
"""
import os
import re
import sys
from datetime import datetime

import requests

from cli import (
    _api,
    cmd_import_ppf,
    cmd_import_epf,
    cmd_import_cas,
    cmd_import_nps,
    cmd_import_broker_csv,
    cmd_import_fidelity_lots,
    cmd_import_ibkr,
    cmd_add_fd,
    cmd_add_rd,
    cmd_add_gold,
    cmd_add_real_estate,
)

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
MAX_PROMPT_ATTEMPTS = 3

_HELP_TEXT = """\
Your database already has existing data. Use individual commands to add more:

  Import commands (server must be running):
    python cli.py import ppf <file> --pan <PAN>
    python cli.py import epf <file> --pan <PAN>
    python cli.py import cas <file> --pan <PAN>
    python cli.py import nps <file> --pan <PAN>
    python cli.py import zerodha <file> --pan <PAN>
    python cli.py import fidelity-lots --open open.csv --closed closed.csv --ticker AMZN --pan <PAN> --exchange-rates '{"2025-03": 86.5}'
    python cli.py import ibkr <file> --pan <PAN> --exchange-rates '{"2026-05": 86.0}'

  Manual add commands:
    python cli.py add fd --name ... --pan <PAN> --bank ... --principal ... --rate ... --start ... --maturity ... --compounding ...
    python cli.py add rd --name ... --pan <PAN> --bank ... --installment ... --rate ... --start ... --maturity ... --compounding ...
    python cli.py add gold --name ... --pan <PAN> --date ... --units ... --price ...
    python cli.py add real-estate --name ... --pan <PAN> --purchase-amount ... --purchase-date ... --current-value ... --value-date ...
"""


def _check_db_empty():
    """Exit with help text if any assets already exist in the DB."""
    try:
        assets = _api("get", "/assets")
    except requests.exceptions.RequestException as exc:
        sys.exit(f"Cannot reach the API server: {exc}. Is the server running?")
    if assets:
        print(_HELP_TEXT)
        sys.exit(0)


def _prompt_pan(prompt_text: str = "PAN (e.g. ABCDE1234F): ") -> str:
    """Prompt for a PAN with format validation. Up to MAX_PROMPT_ATTEMPTS tries."""
    for _ in range(MAX_PROMPT_ATTEMPTS):
        raw = input(prompt_text).strip().upper()
        if PAN_RE.match(raw):
            return raw
        print("  Invalid PAN. Expected format: 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)")
    sys.exit("Too many invalid attempts. Aborting.")


def _resolve_member() -> tuple[list[dict], int | None]:
    """
    Set up member for the session.
    Returns (all_members, single_member_id).
    single_member_id is None when there are 2+ members (caller must prompt per file/entry).
    """
    try:
        members = _api("get", "/members")
    except requests.exceptions.RequestException as exc:
        sys.exit(f"Cannot reach the API server: {exc}. Is the server running?")
    if len(members) == 0:
        print("No members found. Let's create one first.")
        pan = _prompt_pan()
        name = input("Name: ").strip()
        if not pan or not name:
            sys.exit("PAN and name are required.")
        try:
            result = _api("post", "/members", json={"pan": pan, "name": name})
        except requests.exceptions.RequestException as exc:
            sys.exit(f"Failed to create member: {exc}")
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
        except requests.exceptions.RequestException as exc:
            print(f"  Import failed (server error): {exc}")

        again = input(f"Import another file for {label}? [y/N]: ").strip().lower()
        if again != "y":
            break


def _section_fidelity_lots(members: list[dict], single_member_id: int | None):
    """Fidelity open-lots + closed-lots pair — one ticker per pair, repeatable."""
    answer = input("\nDo you have US Stocks — Fidelity lots CSVs (open + closed)? [y/n]: ").strip().lower()
    if answer != "y":
        return

    while True:
        if single_member_id is None:
            member_id = _ask_member(members, "Fidelity lots")
        else:
            member_id = single_member_id

        def _ask_path(kind: str) -> str:
            while True:
                file_path = os.path.expanduser(input(f"Enter {kind} lots file path: ").strip())
                if os.path.isfile(file_path):
                    return file_path
                print(f"  File not found: {file_path}. Please try again.")

        open_path = _ask_path("open")
        closed_path = _ask_path("closed")
        ticker = input("Ticker for these lots (e.g. AMZN): ").strip().upper()

        try:
            cmd_import_fidelity_lots(open_path, closed_path, member_id, ticker=ticker or None)
        except SystemExit as exc:
            print(f"  Import failed: {exc}")
        except requests.exceptions.RequestException as exc:
            print(f"  Import failed (server error): {exc}")

        again = input("Import another Fidelity lots pair? [y/N]: ").strip().lower()
        if again != "y":
            break


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
        except requests.exceptions.RequestException as exc:
            print(f"  Add failed (server error): {exc}")

        again = input(f"Add another {label}? [y/N]: ").strip().lower()
        if again != "y":
            break


def _prompt(prompt_text: str, cast=str, validate=None, max_attempts: int = MAX_PROMPT_ATTEMPTS):
    """Prompt user for input with optional type casting and validation.

    Retries up to max_attempts times, then exits.
    """
    for _ in range(max_attempts):
        raw = input(prompt_text).strip()
        try:
            value = cast(raw)
            if validate is not None and not validate(value):
                raise ValueError
            return value
        except (ValueError, TypeError):
            print("  Invalid input. Please try again.")
    sys.exit("Too many invalid attempts. Aborting.")


def _prompt_date(prompt_text: str) -> str:
    """Prompt for a YYYY-MM-DD date with validation. Up to MAX_PROMPT_ATTEMPTS tries."""
    def _parse(v: str) -> str:
        datetime.strptime(v.strip(), "%Y-%m-%d")
        return v.strip()
    return _prompt(prompt_text, cast=_parse)


def _add_fd_interactive(member_id: int):
    name = _prompt("Name (e.g. HDFC FD 2024): ")
    bank = _prompt("Bank: ")
    principal = _prompt("Principal amount (INR): ", cast=float, validate=lambda x: x > 0)
    rate = _prompt("Interest rate (%): ", cast=float, validate=lambda x: x > 0)
    start = _prompt_date("Start date (YYYY-MM-DD): ")
    maturity = _prompt_date("Maturity date (YYYY-MM-DD): ")
    compounding = _prompt("Compounding [MONTHLY/QUARTERLY/HALF_YEARLY/YEARLY] (default QUARTERLY): ") or "QUARTERLY"
    cmd_add_fd(name, bank, principal, rate, start, maturity, compounding, member_id)


def _add_rd_interactive(member_id: int):
    name = _prompt("Name (e.g. SBI RD 2024): ")
    bank = _prompt("Bank: ")
    installment = _prompt("Monthly installment (INR): ", cast=float, validate=lambda x: x > 0)
    rate = _prompt("Interest rate (%): ", cast=float, validate=lambda x: x > 0)
    start = _prompt_date("Start date (YYYY-MM-DD): ")
    maturity = _prompt_date("Maturity date (YYYY-MM-DD): ")
    compounding = _prompt("Compounding [MONTHLY/QUARTERLY/HALF_YEARLY/YEARLY] (default QUARTERLY): ") or "QUARTERLY"
    cmd_add_rd(name, bank, installment, rate, start, maturity, compounding, member_id)


def _add_gold_interactive(member_id: int):
    name = _prompt("Name (e.g. Digital Gold): ")
    date = _prompt_date("Purchase date (YYYY-MM-DD): ")
    units = _prompt("Units (grams): ", cast=float, validate=lambda x: x > 0)
    price = _prompt("Price per unit (INR/gram): ", cast=float, validate=lambda x: x > 0)
    cmd_add_gold(name, date, units, price, member_id)


def _add_real_estate_interactive(member_id: int):
    name = _prompt("Name (e.g. Venezia Flat): ")
    purchase_amount = _prompt("Purchase amount (INR): ", cast=float, validate=lambda x: x > 0)
    purchase_date = _prompt_date("Purchase date (YYYY-MM-DD): ")
    current_value = _prompt("Current value (INR): ", cast=float, validate=lambda x: x > 0)
    value_date = _prompt_date("Value date (YYYY-MM-DD): ")
    cmd_add_real_estate(name, purchase_amount, purchase_date, current_value, value_date, member_id)


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
    _section_fidelity_lots(members, single_member_id)
    _section_file(
        "US Stocks — IBKR Flex Trades CSV",
        cmd_import_ibkr,
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

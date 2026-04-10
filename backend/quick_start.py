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

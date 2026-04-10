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

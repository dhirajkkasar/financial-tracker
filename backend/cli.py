"""
Portfolio CLI — wraps the backend REST API for data loading and updates.

Usage (server must be running):
  python cli.py add-member --pan ABCDE1234F --name "Dhiraj"

  python cli.py import ppf <file> --pan ABCDE1234F
  python cli.py import epf <file> --pan ABCDE1234F
  python cli.py import cas <file> --pan ABCDE1234F
  python cli.py import nps <file> --pan ABCDE1234F
  python cli.py import zerodha <file> --pan ABCDE1234F
  python cli.py import fidelity-rsu <file> --pan ABCDE1234F    # Fidelity RSU holding CSV
  python cli.py import fidelity-sale <file> --pan ABCDE1234F   # Fidelity tax-cover sale PDF

  python cli.py add fd   --name "HDFC FD" --bank HDFC --principal 500000 --rate 7.1 --start 2024-01-15 --maturity 2025-01-15 --compounding QUARTERLY
  python cli.py add rd   --name "SBI RD"  --bank SBI  --installment 10000 --rate 6.5 --start 2024-01-01 --maturity 2026-01-01 --compounding QUARTERLY
  python cli.py add real-estate --name "Venezia Flat" --purchase-amount 7500000 --purchase-date 2020-11-09 --current-value 12000000 --value-date 2024-01-01
  python cli.py add gold  --name "Digital Gold" --date 2023-06-01 --units 10 --price 5800
  python cli.py add sgb   --name "SGB 2023-24 S3" --date 2023-12-01 --units 50 --price 6200
  python cli.py add rsu   --name "AMZN RSU" --date 2024-03-01 --units 10 --price 180.50 --forex 83.5 --notes "Perquisite tax: ..."
  python cli.py add us-stock --name "Apple" --identifier AAPL --date 2023-01-15 --units 5 --price 142.50 --forex 82.0

  python cli.py add valuation --asset "Venezia Flat" --value 13000000 --date 2025-01-01
  python cli.py add txn  --asset "AMZN RSU" --type VEST --date 2024-09-01 --amount -90000 --units 5 --price 215 --forex 84

  # EPF monthly contribution (use after initial PDF import)
  python cli.py add epf-contribution --asset "My EPF" --month-year 03/2026 --employee-share 5000
  python cli.py add epf-contribution --asset "My EPF" --month-year 03/2026 --employee-share 5000 --eps-share 1250 --employer-share 3750
  python cli.py add epf-contribution --asset "My EPF" --month-year 03/2026 --employee-share 5000 --employee-interest 500 --employer-interest 400 --eps-interest 50

  python cli.py add goal --name "Retirement" --target 10000000 --date 2040-01-01 --asset "HDFC MF:50" --asset "PPF SBI:50"
  python cli.py add goal --name "Emergency Fund" --target 500000 --date 2026-12-31

  python cli.py update goal-allocation --goal "Retirement" --asset "HDFC MF" --pct 30
  python cli.py remove goal-allocation --goal "Retirement" --asset "HDFC MF"
  python cli.py delete goal --name "Retirement"

  python cli.py list assets
  python cli.py refresh-prices
  python cli.py snapshot

Set PORTFOLIO_API env var to override the default base URL (http://localhost:8000).
"""

import argparse
import calendar
import hashlib
import os
import sys
from difflib import get_close_matches

import requests

BASE = os.getenv("PORTFOLIO_API", "http://localhost:8000")


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _api(method: str, path: str, **kwargs):
    try:
        r = getattr(requests, method)(f"{BASE}{path}", **kwargs)
    except requests.ConnectionError:
        sys.exit(f"Cannot connect to {BASE}. Is the server running?")
    if not r.ok:
        sys.exit(f"API error {r.status_code}: {r.text}")
    if r.status_code == 204 or not r.content:
        return {}
    return r.json()


# ── Asset lookup ──────────────────────────────────────────────────────────────

def find_asset(name_query: str) -> dict:
    """Fuzzy-match an asset by name. Exits if no match found."""
    assets = _api("get", "/assets")
    name_map = {a["name"]: a for a in assets}
    matches = get_close_matches(name_query, name_map.keys(), n=1, cutoff=0.4)
    if not matches:
        sys.exit(f"No asset matching '{name_query}'. Run 'list assets' to see all assets.")
    asset = name_map[matches[0]]
    print(f"  → matched: {asset['name']} (id={asset['id']})")
    return asset


def find_goal(name_query: str) -> dict:
    """Fuzzy-match a goal by name. Exits if no match found."""
    goals = _api("get", "/goals")
    name_map = {g["name"]: g for g in goals}
    matches = get_close_matches(name_query, name_map.keys(), n=1, cutoff=0.4)
    if not matches:
        sys.exit(f"No goal matching '{name_query}'. Check existing goals via GET /goals.")
    goal = name_map[matches[0]]
    print(f"  → matched goal: {goal['name']} (id={goal['id']})")
    return goal


def resolve_member_id(pan: str) -> int:
    """Look up member by PAN via GET /members. Exit if not found."""
    members = _api("get", "/members")
    for m in members:
        if m["pan"].upper() == pan.upper():
            print(f"  → matched member: {m['name']} (id={m['id']}, PAN={m['pan']})")
            return m["id"]
    sys.exit(f"No member with PAN '{pan}'. Run 'add-member --pan {pan} --name <name>' first.")


def _find_or_create_asset(name: str, asset_type: str, asset_class: str,
                           identifier: str | None = None, currency: str = "INR") -> dict:
    """Return existing asset by exact name, or create a new one."""
    assets = _api("get", "/assets")
    for a in assets:
        if a["name"] == name:
            print(f"  → using existing asset: {a['name']} (id={a['id']})")
            return a
    payload = {"name": name, "asset_type": asset_type, "asset_class": asset_class, "currency": currency}
    if identifier:
        payload["identifier"] = identifier
    asset = _api("post", "/assets", json=payload)
    print(f"  → created asset: {asset['name']} (id={asset['id']})")
    return asset


# ── Import commands ───────────────────────────────────────────────────────────

def cmd_import_ppf(file_path: str, member_id: int) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        preview = _api("post", f"/import/preview-file?source=ppf&format=csv&member_id={member_id}", files={"file": f})
    result = _api("post", f"/import/commit-file/{preview['preview_id']}")
    _print_import_summary("PPF", inserted=result["inserted"], skipped=result["skipped"])
    return result


def cmd_import_epf(file_path: str, member_id: int) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        preview = _api("post", f"/import/preview-file?source=epf&format=pdf&member_id={member_id}", files={"file": f})
    result = _api("post", f"/import/commit-file/{preview['preview_id']}")
    _print_import_summary("EPF", inserted=result["inserted"], skipped=result["skipped"])
    return result


def cmd_import_cas(file_path: str, member_id: int) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        preview = _api("post", f"/import/preview-file?source=cas&format=pdf&member_id={member_id}", files={"file": f})
    result = _api("post", f"/import/commit-file/{preview['preview_id']}")
    _print_import_summary("CAS", inserted=result["inserted"], skipped=result["skipped"])
    return result


def cmd_import_nps(file_path: str, member_id: int) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        preview = _api("post", f"/import/preview-file?source=nps&format=csv&member_id={member_id}", files={"file": f})
    result = _api("post", f"/import/commit-file/{preview['preview_id']}")
    cmd_refresh_prices()
    _print_import_summary("NPS", inserted=result["inserted"], skipped=result["skipped"])
    return result


def cmd_import_broker_csv(file_path: str, broker: str, member_id: int) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        preview = _api("post", f"/import/preview-file?source={broker}&format=csv&member_id={member_id}", files={"file": f})
    result = _api("post", f"/import/commit-file/{preview['preview_id']}")
    _print_import_summary(broker.title(), inserted=result["inserted"], skipped=result["skipped"])
    return result


def cmd_import_fidelity_rsu(file_path: str, member_id: int) -> None:
    """Import Fidelity RSU holding CSV (MARKET_TICKER.csv format).
    Prompts for USD/INR exchange rate per vest month.
    """
    _check_file(file_path)
    from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter

    # Step 1: Parse CSV locally to find required month-years
    with open(file_path, "rb") as f:
        csv_bytes = f.read()
    months_list = FidelityRSUImporter.extract_required_month_years(csv_bytes)
    months = set(months_list)

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
            f"/import/preview-file?source=fidelity_rsu&format=csv&member_id={member_id}",
            files={"file": (os.path.basename(file_path), f, "text/csv")},
            data={"user_inputs": json.dumps(exchange_rates)},
        )

    print(f"\nPreview: {preview['new_count']} new, {preview['duplicate_count']} duplicate")
    if preview["new_count"] == 0:
        print("Nothing to import.")
        return

    confirm = input("Commit? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    result = _api("post", f"/import/commit-file/{preview['preview_id']}")
    cmd_refresh_prices()
    _print_import_summary(
        "Fidelity RSU",
        inserted=result.get("inserted", 0),
        skipped=result.get("skipped", 0),
        errors=[],
    )


def cmd_import_fidelity_sale(file_path: str, member_id: int) -> None:
    """Import Fidelity tax-cover SELL transactions from a transaction summary PDF.
    Parses the PDF locally (pdfplumber) to find required month-years, prompts for rates,
    then calls one API endpoint with file + rates.
    """
    _check_file(file_path)
    import json
    from app.importers.fidelity_pdf_importer import FidelityPDFImporter

    # Step 1: Parse PDF locally to find required month-years
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()
    months_list = FidelityPDFImporter.extract_required_month_years(pdf_bytes)
    months = set(months_list)

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
            f"/import/preview-file?source=fidelity_sale&format=pdf&member_id={member_id}",
            files={"file": (os.path.basename(file_path), f, "application/pdf")},
            data={"user_inputs": json.dumps(exchange_rates)},
        )

    print(f"\nPreview: {preview['new_count']} new, {preview['duplicate_count']} duplicate")
    if preview["new_count"] == 0:
        print("Nothing to import.")
        return

    confirm = input("Commit? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    result = _api("post", f"/import/commit-file/{preview['preview_id']}")
    _print_import_summary(
        "Fidelity Sale PDF",
        inserted=result.get("inserted", 0),
        skipped=result.get("skipped", 0),
        errors=[],
    )


# ── Member commands ───────────────────────────────────────────────────────────

def cmd_add_member(pan: str, name: str) -> dict:
    result = _api("post", "/members", json={"pan": pan, "name": name})
    print(f"  → created member: {result['name']} (id={result['id']}, PAN={result['pan']})")
    return result


# ── Add commands ──────────────────────────────────────────────────────────────

def cmd_add_fd(name: str, bank: str, principal: float, rate: float,
               start: str, maturity: str, compounding: str, matured: bool = None) -> dict:
    from datetime import date as _date
    if matured is None:
        matured = _date.fromisoformat(maturity) < _date.today()
    asset = _api("post", "/assets", json={
        "name": name, "asset_type": "FD", "asset_class": "DEBT", "currency": "INR",
    })
    asset_id = asset["id"]
    _api("post", f"/assets/{asset_id}/fd-detail", json={
        "bank": bank, "fd_type": "FD",
        "principal_amount": principal,
        "interest_rate_pct": rate,
        "compounding": compounding,
        "start_date": start,
        "maturity_date": maturity,
        "is_matured": matured,
    })
    txn = _api("post", f"/assets/{asset_id}/transactions", json={
        "type": "CONTRIBUTION", "date": start,
        "amount_inr": -principal, "charges_inr": 0.0,
    })
    status = "matured" if matured else "active"
    print(f"✓ FD created: {name} (id={asset_id}) — ₹{principal:,.0f} @ {rate}% until {maturity} [{status}]")
    return txn


def cmd_add_rd(name: str, bank: str, installment: float, rate: float,
               start: str, maturity: str, compounding: str) -> dict:
    asset = _api("post", "/assets", json={
        "name": name, "asset_type": "RD", "asset_class": "DEBT", "currency": "INR",
    })
    asset_id = asset["id"]
    _api("post", f"/assets/{asset_id}/fd-detail", json={
        "bank": bank, "fd_type": "RD",
        "principal_amount": installment,
        "interest_rate_pct": rate,
        "compounding": compounding,
        "start_date": start,
        "maturity_date": maturity,
    })
    txn = _api("post", f"/assets/{asset_id}/transactions", json={
        "type": "CONTRIBUTION", "date": start,
        "amount_inr": -installment, "charges_inr": 0.0,
    })
    print(f"✓ RD created: {name} (id={asset_id}) — ₹{installment:,.0f}/month @ {rate}% until {maturity}")
    return txn


def cmd_add_real_estate(name: str, purchase_amount: float, purchase_date: str,
                        current_value: float, value_date: str) -> dict:
    asset = _api("post", "/assets", json={
        "name": name, "asset_type": "REAL_ESTATE", "asset_class": "REAL_ESTATE", "currency": "INR",
    })
    asset_id = asset["id"]
    _api("post", f"/assets/{asset_id}/transactions", json={
        "type": "CONTRIBUTION", "date": purchase_date,
        "amount_inr": -purchase_amount, "charges_inr": 0.0,
    })
    val = _api("post", f"/assets/{asset_id}/valuations", json={
        "date": value_date, "value_inr": current_value, "source": "manual",
    })
    print(f"✓ Real estate created: {name} (id={asset_id}) — purchased ₹{purchase_amount:,.0f}, current ₹{current_value:,.0f}")
    return val


def cmd_add_gold(name: str, date: str, units: float, price: float) -> dict:
    asset = _find_or_create_asset(name, "GOLD", "GOLD")
    txn = _api("post", f"/assets/{asset['id']}/transactions", json={
        "type": "BUY", "date": date,
        "units": units, "price_per_unit": price,
        "amount_inr": -(units * price), "charges_inr": 0.0,
    })
    print(f"✓ Gold BUY: {units}g × ₹{price:,.2f} = ₹{units * price:,.2f} on {date}")
    return txn


def cmd_add_sgb(name: str, date: str, units: float, price: float) -> dict:
    asset = _find_or_create_asset(name, "SGB", "GOLD")
    txn = _api("post", f"/assets/{asset['id']}/transactions", json={
        "type": "BUY", "date": date,
        "units": units, "price_per_unit": price,
        "amount_inr": -(units * price), "charges_inr": 0.0,
    })
    print(f"✓ SGB BUY: {units} units × ₹{price:,.2f} = ₹{units * price:,.2f} on {date}")
    return txn


def cmd_add_rsu(name: str, date: str, units: float, price: float,
                forex: float, notes: str | None = None, identifier: str | None = None) -> dict:
    asset = _find_or_create_asset(name, "STOCK_US", "EQUITY", identifier=identifier)
    amount = -(units * price * forex)
    txn = _api("post", f"/assets/{asset['id']}/transactions", json={
        "type": "VEST", "date": date,
        "units": units, "price_per_unit": price, "forex_rate": forex,
        "amount_inr": amount, "charges_inr": 0.0,
        "notes": notes,
    })
    print(f"✓ RSU VEST: {units} × ${price:.2f} @ ₹{forex} = ₹{abs(amount):,.2f} on {date}")
    return txn


def cmd_add_us_stock(name: str, date: str, units: float, price: float,
                     forex: float, identifier: str | None = None) -> dict:
    asset = _find_or_create_asset(name, "STOCK_US", "EQUITY", identifier=identifier)
    amount = -(units * price * forex)
    txn = _api("post", f"/assets/{asset['id']}/transactions", json={
        "type": "BUY", "date": date,
        "units": units, "price_per_unit": price, "forex_rate": forex,
        "amount_inr": amount, "charges_inr": 0.0,
    })
    print(f"✓ US Stock BUY: {units} × ${price:.2f} @ ₹{forex} = ₹{abs(amount):,.2f} on {date}")
    return txn


def _epf_txn_id(*parts) -> str:
    """Generate a stable EPF txn_id matching the EPF PDF parser convention."""
    raw = "|".join(str(p) for p in parts)
    return "epf_" + hashlib.sha256(raw.encode()).hexdigest()


def cmd_add_epf_contribution(
    asset_name: str,
    month_year: str,
    employee_share: float,
    eps_share: float = 1250.0,
    employer_share: float | None = None,
    employee_interest: float | None = None,
    employer_interest: float | None = None,
    eps_interest: float | None = None,
) -> list:
    """
    Add a monthly EPF contribution (and optionally interest) for one month.

    Creates up to 3 CONTRIBUTION transactions (employee, employer, EPS) and
    up to 3 INTEREST transactions (if interest amounts are provided).
    Transactions are deduplicated via stable txn_ids matching the EPF PDF parser.
    """
    from datetime import date as _date

    # Parse MM/YYYY
    try:
        month_str, year_str = month_year.split("/")
        month, year = int(month_str), int(year_str)
        if not (1 <= month <= 12 and year >= 2000):
            raise ValueError
    except ValueError:
        sys.exit("--month-year must be MM/YYYY (e.g. 03/2026)")

    if employer_share is None:
        employer_share = employee_share - eps_share

    last_day = calendar.monthrange(year, month)[1]
    txn_date = _date(year, month, last_day).isoformat()
    mmyyyy = f"{month:02d}{year}"

    asset = find_asset(asset_name)
    asset_id = asset["id"]
    member_id = asset.get("identifier") or ""

    inserted = 0
    skipped = 0

    def _post_txn(txn_type: str, amount_inr: float, notes: str, txn_id: str):
        nonlocal inserted, skipped
        try:
            _api("post", f"/assets/{asset_id}/transactions", json={
                "type": txn_type,
                "date": txn_date,
                "amount_inr": amount_inr,
                "charges_inr": 0.0,
                "notes": notes,
                "txn_id": txn_id,
            })
            print(f"  + {txn_type} ({notes}): ₹{abs(amount_inr):,.2f}")
            inserted += 1
        except SystemExit as exc:
            msg = str(exc)
            if "409" in msg or "already exists" in msg:
                print(f"  ~ skipped (duplicate): {txn_type} ({notes})")
                skipped += 1
            else:
                raise

    # Contributions (outflows → negative)
    _post_txn("CONTRIBUTION", -employee_share, "Employee Share",
              _epf_txn_id(member_id, "CONTRIB_EMP", mmyyyy, round(employee_share * 100)))
    _post_txn("CONTRIBUTION", -employer_share, "Employer Share",
              _epf_txn_id(member_id, "CONTRIB_ER", mmyyyy, round(employer_share * 100)))
    _post_txn("CONTRIBUTION", -eps_share, "Pension Contribution (EPS)",
              _epf_txn_id(member_id, "CONTRIB_EPS", mmyyyy, round(eps_share * 100)))

    # Interest (inflows → positive), only if provided
    if employee_interest is not None:
        _post_txn("INTEREST", employee_interest, "Employee Interest",
                  _epf_txn_id(member_id, "INTEREST_EMP", txn_date, round(employee_interest * 100)))
    if employer_interest is not None:
        _post_txn("INTEREST", employer_interest, "Employer Interest",
                  _epf_txn_id(member_id, "INTEREST_ER", txn_date, round(employer_interest * 100)))
    if eps_interest is not None:
        _post_txn("INTEREST", eps_interest, "EPS Interest",
                  _epf_txn_id(member_id, "INTEREST_EPS", txn_date, round(eps_interest * 100)))

    print(f"✓ EPF {month_year}: {inserted} inserted, {skipped} skipped")


def cmd_add_valuation(asset_name: str, value: float, date: str) -> dict:
    asset = find_asset(asset_name)
    val = _api("post", f"/assets/{asset['id']}/valuations", json={
        "date": date, "value_inr": value, "source": "manual",
    })
    print(f"✓ Valuation added: {asset['name']} → ₹{value:,.0f} on {date}")
    return val


def cmd_add_txn(asset: str, txn_type: str, date: str, amount: float,
                units: float | None = None, price: float | None = None,
                forex: float | None = None, notes: str | None = None) -> dict:
    matched = find_asset(asset)
    payload = {
        "type": txn_type, "date": date,
        "amount_inr": amount, "charges_inr": 0.0,
        "notes": notes,
    }
    if units is not None:
        payload["units"] = units
    if price is not None:
        payload["price_per_unit"] = price
    if forex is not None:
        payload["forex_rate"] = forex
    txn = _api("post", f"/assets/{matched['id']}/transactions", json=payload)
    print(f"✓ Transaction added: {matched['name']} — {txn_type} ₹{amount:,.2f} on {date}")
    return txn


# ── Goal commands ─────────────────────────────────────────────────────────────

def cmd_add_goal(name: str, target: float, date: str,
                 assets: list[str] | None = None,
                 notes: str | None = None,
                 assumed_return: float = 12.0) -> dict:
    """Create a goal and optionally assign assets with allocation percentages."""
    # Parse and validate --asset "Name:pct" entries upfront
    allocations: list[tuple[str, int]] = []
    for spec in (assets or []):
        try:
            asset_name, pct_str = spec.rsplit(":", 1)
            pct = int(pct_str)
        except (ValueError, AttributeError):
            sys.exit(f"Invalid --asset format '{spec}'. Use 'AssetName:pct' (e.g. 'HDFC MF:50')")
        if pct % 10 != 0 or not (10 <= pct <= 100):
            sys.exit(f"Allocation % must be a multiple of 10 between 10 and 100, got {pct} for '{asset_name}'")
        allocations.append((asset_name.strip(), pct))

    goal = _api("post", "/goals", json={
        "name": name,
        "target_amount_inr": target,
        "target_date": date,
        "notes": notes,
        "assumed_return_pct": assumed_return,
    })
    print(f"✓ Goal created: {goal['name']} (id={goal['id']}) — ₹{target:,.0f} by {date}")

    for asset_name, pct in allocations:
        asset = find_asset(asset_name)
        try:
            _api("post", f"/goals/{goal['id']}/allocations", json={
                "asset_id": asset["id"],
                "allocation_pct": pct,
            })
            print(f"  + {asset['name']}: {pct}%")
        except SystemExit as exc:
            print(f"  ! Failed to allocate '{asset_name}' {pct}%: {exc}")

    return goal


def cmd_update_goal_allocation(goal_name: str, asset_name: str, pct: int) -> dict:
    """Update the allocation % of an asset within a goal."""
    goal = find_goal(goal_name)
    asset = find_asset(asset_name)
    allocations = _api("get", f"/goals/{goal['id']}/allocations")
    match = next((a for a in allocations if a["asset_id"] == asset["id"]), None)
    if not match:
        sys.exit(f"No allocation found for '{asset['name']}' in goal '{goal['name']}'")
    _api("put", f"/goals/{goal['id']}/allocations/{match['id']}", json={"allocation_pct": pct})
    print(f"✓ Updated: {goal['name']} → {asset['name']}: {pct}%")
    return match


def cmd_remove_goal_allocation(goal_name: str, asset_name: str) -> None:
    """Remove an asset allocation from a goal."""
    goal = find_goal(goal_name)
    asset = find_asset(asset_name)
    allocations = _api("get", f"/goals/{goal['id']}/allocations")
    match = next((a for a in allocations if a["asset_id"] == asset["id"]), None)
    if not match:
        sys.exit(f"No allocation found for '{asset['name']}' in goal '{goal['name']}'")
    _api("delete", f"/goals/{goal['id']}/allocations/{match['id']}")
    print(f"✓ Removed: '{asset['name']}' from goal '{goal['name']}'")


def cmd_delete_goal(name: str) -> None:
    """Delete a goal and all its allocations."""
    goal = find_goal(name)
    _api("delete", f"/goals/{goal['id']}")
    print(f"✓ Goal deleted: {goal['name']} (id={goal['id']})")


# ── Utility commands ──────────────────────────────────────────────────────────

def cmd_list_assets() -> list:
    assets = _api("get", "/assets")
    print(f"{'ID':<5} {'Name':<35} {'Type':<15} {'Active'}")
    print("─" * 65)
    for a in sorted(assets, key=lambda x: x["name"]):
        active = "✓" if a["is_active"] else "✗"
        print(f"{a['id']:<5} {a['name']:<35} {a['asset_type']:<15} {active}")
    return assets


def cmd_fetch_corp_actions(asset_id: int | None = None) -> dict:
    if asset_id is not None:
        result = _api("post", f"/corp-actions/fetch-asset/{asset_id}")
        print(f"✓ Corp actions for asset {asset_id}: "
              f"bonus={result.get('bonus_created', 0)}, "
              f"split={result.get('split_applied', 0)}, "
              f"dividend={result.get('dividend_created', 0)}")
    else:
        result = _api("post", "/corp-actions/fetch-all")
        print(f"✓ Corp actions (all stocks): "
              f"bonus={result.get('bonus_created', 0)}, "
              f"split={result.get('split_applied', 0)}, "
              f"dividend={result.get('dividend_created', 0)}")
    return result


def cmd_refresh_prices() -> dict:
    result = _api("post", "/prices/refresh-all")
    print("✓ Price refresh triggered")
    return result


def cmd_snapshot() -> dict:
    result = _api("post", "/snapshots/take")
    print(f"✓ Snapshot taken: {result.get('date')} — ₹{result.get('total_value_inr', 0):,.2f}")
    return result


def cmd_backup(folder: str | None = None):
    import backup as _backup
    _backup.backup_to_drive(folder_name=folder)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_file(path: str):
    if not os.path.isfile(path):
        sys.exit(f"File not found: {path}")


def _print_import_summary(label: str, inserted: int, skipped: int, errors: list | None = None):
    print(f"✓ {label}: {inserted} inserted, {skipped} skipped"
          + (f", {len(errors)} errors" if errors else ""))


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Portfolio CLI — manage financial tracker data via the REST API.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ── import ────────────────────────────────────────────────────────────────
    p_import = sub.add_parser("import", help="Import data from a PDF or CSV file")
    import_sub = p_import.add_subparsers(dest="source", metavar="SOURCE")

    for src in ("ppf", "epf", "cas", "nps"):
        s = import_sub.add_parser(src, help=f"Import {src.upper()} file")
        s.add_argument("file", help="Path to the file")
        s.add_argument("--pan", required=True, help="PAN of the member this import belongs to")

    s = import_sub.add_parser("zerodha", help="Import Zerodha tradebook CSV")
    s.add_argument("file", help="Path to CSV")
    s.add_argument("--pan", required=True, help="PAN of the member this import belongs to")

    s = import_sub.add_parser("fidelity-rsu", help="Import Fidelity RSU holding CSV (MARKET_TICKER.csv)")
    s.add_argument("file", help="Path to CSV file")
    s.add_argument("--pan", required=True, help="PAN of the member this import belongs to")

    s = import_sub.add_parser("fidelity-sale", help="Import Fidelity tax-cover sale PDF")
    s.add_argument("file", help="Path to PDF file")
    s.add_argument("--pan", required=True, help="PAN of the member this import belongs to")

    # ── add ───────────────────────────────────────────────────────────────────
    p_add = sub.add_parser("add", help="Add an asset or transaction manually")
    add_sub = p_add.add_subparsers(dest="kind", metavar="KIND")

    # add fd
    p_fd = add_sub.add_parser("fd", help="Add a Fixed Deposit")
    p_fd.add_argument("--name", required=True)
    p_fd.add_argument("--bank", required=True)
    p_fd.add_argument("--principal", type=float, required=True, help="Principal amount in INR")
    p_fd.add_argument("--rate", type=float, required=True, help="Annual interest rate %")
    p_fd.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p_fd.add_argument("--maturity", required=True, help="Maturity date YYYY-MM-DD")
    p_fd.add_argument("--compounding", default="QUARTERLY",
                      choices=["MONTHLY", "QUARTERLY", "HALF_YEARLY", "YEARLY"])
    p_fd.add_argument("--matured", action="store_true", default=None,
                      help="Mark as matured (auto-detected from maturity date if omitted)")

    # add rd
    p_rd = add_sub.add_parser("rd", help="Add a Recurring Deposit")
    p_rd.add_argument("--name", required=True)
    p_rd.add_argument("--bank", required=True)
    p_rd.add_argument("--installment", type=float, required=True, help="Monthly installment in INR")
    p_rd.add_argument("--rate", type=float, required=True, help="Annual interest rate %")
    p_rd.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p_rd.add_argument("--maturity", required=True, help="Maturity date YYYY-MM-DD")
    p_rd.add_argument("--compounding", default="QUARTERLY",
                      choices=["MONTHLY", "QUARTERLY", "HALF_YEARLY", "YEARLY"])

    # add real-estate
    p_re = add_sub.add_parser("real-estate", help="Add a real estate property")
    p_re.add_argument("--name", required=True)
    p_re.add_argument("--purchase-amount", type=float, required=True, help="Purchase price in INR")
    p_re.add_argument("--purchase-date", required=True, help="Purchase date YYYY-MM-DD")
    p_re.add_argument("--current-value", type=float, required=True, help="Current market value in INR")
    p_re.add_argument("--value-date", required=True, help="Date of current value estimate YYYY-MM-DD")

    # add gold
    p_gold = add_sub.add_parser("gold", help="Add a gold purchase")
    p_gold.add_argument("--name", required=True)
    p_gold.add_argument("--date", required=True, help="Purchase date YYYY-MM-DD")
    p_gold.add_argument("--units", type=float, required=True, help="Grams purchased")
    p_gold.add_argument("--price", type=float, required=True, help="Price per gram in INR")

    # add sgb
    p_sgb = add_sub.add_parser("sgb", help="Add a Sovereign Gold Bond purchase")
    p_sgb.add_argument("--name", required=True)
    p_sgb.add_argument("--date", required=True, help="Purchase date YYYY-MM-DD")
    p_sgb.add_argument("--units", type=float, required=True, help="Units (bonds) purchased")
    p_sgb.add_argument("--price", type=float, required=True, help="Price per unit in INR")

    # add rsu
    p_rsu = add_sub.add_parser("rsu", help="Add an RSU vest event")
    p_rsu.add_argument("--name", required=True, help="Asset name (e.g. 'AMZN RSU')")
    p_rsu.add_argument("--identifier", help="Stock ticker (e.g. AMZN)")
    p_rsu.add_argument("--date", required=True, help="Vest date YYYY-MM-DD")
    p_rsu.add_argument("--units", type=float, required=True, help="Shares vested")
    p_rsu.add_argument("--price", type=float, required=True, help="Price per share in USD")
    p_rsu.add_argument("--forex", type=float, required=True, help="USD/INR rate on vest date")
    p_rsu.add_argument("--notes", help="e.g. 'Perquisite tax: ₹1,23,000'")

    # add us-stock
    p_us = add_sub.add_parser("us-stock", help="Add a US stock purchase")
    p_us.add_argument("--name", required=True)
    p_us.add_argument("--identifier", help="Ticker symbol")
    p_us.add_argument("--date", required=True, help="Purchase date YYYY-MM-DD")
    p_us.add_argument("--units", type=float, required=True)
    p_us.add_argument("--price", type=float, required=True, help="Price per share in USD")
    p_us.add_argument("--forex", type=float, required=True, help="USD/INR rate")

    # add epf-contribution
    p_epf = add_sub.add_parser("epf-contribution", help="Add a monthly EPF contribution (post initial PDF import)")
    p_epf.add_argument("--asset", required=True, help="EPF asset name (fuzzy matched)")
    p_epf.add_argument("--month-year", required=True, dest="month_year",
                       metavar="MM/YYYY", help="Contribution month and year (e.g. 03/2026)")
    p_epf.add_argument("--employee-share", type=float, required=True, dest="employee_share",
                       help="Employee EPF contribution in INR")
    p_epf.add_argument("--eps-share", type=float, default=1250.0, dest="eps_share",
                       help="EPS (pension) contribution in INR (default: 1250)")
    p_epf.add_argument("--employer-share", type=float, default=None, dest="employer_share",
                       help="Employer EPF contribution in INR (default: employee-share minus eps-share)")
    p_epf.add_argument("--employee-interest", type=float, default=None, dest="employee_interest",
                       help="Employee interest in INR (optional)")
    p_epf.add_argument("--employer-interest", type=float, default=None, dest="employer_interest",
                       help="Employer interest in INR (optional)")
    p_epf.add_argument("--eps-interest", type=float, default=None, dest="eps_interest",
                       help="EPS interest in INR (optional)")

    # add goal
    p_goal = add_sub.add_parser("goal", help="Create a goal and optionally assign assets")
    p_goal.add_argument("--name", required=True, help="Goal name")
    p_goal.add_argument("--target", type=float, required=True, help="Target corpus in INR")
    p_goal.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    p_goal.add_argument("--asset", action="append", dest="assets", metavar="NAME:PCT",
                        help="Asset allocation in 'Name:pct' format; repeatable (e.g. 'HDFC MF:50')")
    p_goal.add_argument("--notes", help="Optional notes")
    p_goal.add_argument("--assumed-return", type=float, default=12.0, dest="assumed_return",
                        help="Expected annual return %% (default: 12.0)")

    # add valuation
    p_val = add_sub.add_parser("valuation", help="Add a manual valuation to an existing asset")
    p_val.add_argument("--asset", required=True, help="Asset name (fuzzy matched)")
    p_val.add_argument("--value", type=float, required=True, help="Current value in INR")
    p_val.add_argument("--date", required=True, help="Valuation date YYYY-MM-DD")

    # add txn
    p_txn = add_sub.add_parser("txn", help="Add a generic transaction to an existing asset")
    p_txn.add_argument("--asset", required=True, help="Asset name (fuzzy matched)")
    p_txn.add_argument("--type", dest="txn_type", required=True,
                        choices=["BUY", "SELL", "SIP", "REDEMPTION", "DIVIDEND", "INTEREST",
                                 "CONTRIBUTION", "WITHDRAWAL", "VEST", "TRANSFER", "BONUS", "SPLIT"])
    p_txn.add_argument("--date", required=True, help="Transaction date YYYY-MM-DD")
    p_txn.add_argument("--amount", type=float, required=True,
                        help="Amount in INR (negative = outflow, positive = inflow)")
    p_txn.add_argument("--units", type=float)
    p_txn.add_argument("--price", type=float, help="Price per unit")
    p_txn.add_argument("--forex", type=float, help="Forex rate (for USD assets)")
    p_txn.add_argument("--notes")

    # ── list ──────────────────────────────────────────────────────────────────
    p_list = sub.add_parser("list", help="List resources")
    list_sub = p_list.add_subparsers(dest="resource", metavar="RESOURCE")
    list_sub.add_parser("assets", help="List all assets")

    # ── update ────────────────────────────────────────────────────────────────
    p_update = sub.add_parser("update", help="Update an existing resource")
    update_sub = p_update.add_subparsers(dest="kind", metavar="KIND")

    p_update_ga = update_sub.add_parser("goal-allocation", help="Update an asset's allocation % within a goal")
    p_update_ga.add_argument("--goal", required=True, help="Goal name (fuzzy matched)")
    p_update_ga.add_argument("--asset", required=True, help="Asset name (fuzzy matched)")
    p_update_ga.add_argument("--pct", type=int, required=True, help="New allocation % (multiple of 10)")

    # ── remove ────────────────────────────────────────────────────────────────
    p_remove = sub.add_parser("remove", help="Remove an allocation or other resource")
    remove_sub = p_remove.add_subparsers(dest="kind", metavar="KIND")

    p_remove_ga = remove_sub.add_parser("goal-allocation", help="Remove an asset from a goal")
    p_remove_ga.add_argument("--goal", required=True, help="Goal name (fuzzy matched)")
    p_remove_ga.add_argument("--asset", required=True, help="Asset name (fuzzy matched)")

    # ── delete ────────────────────────────────────────────────────────────────
    p_delete = sub.add_parser("delete", help="Delete a resource")
    delete_sub = p_delete.add_subparsers(dest="kind", metavar="KIND")

    p_delete_goal = delete_sub.add_parser("goal", help="Delete a goal and all its allocations")
    p_delete_goal.add_argument("--name", required=True, help="Goal name (fuzzy matched)")

    # ── utilities ─────────────────────────────────────────────────────────────
    # ── add-member ────────────────────────────────────────────────────────────
    p_add_member = sub.add_parser("add-member", help="Register a household member")
    p_add_member.add_argument("--pan", required=True, help="PAN card number (e.g. ABCDE1234F)")
    p_add_member.add_argument("--name", required=True, help="Member name")

    sub.add_parser("refresh-prices", help="Trigger price refresh for all assets")
    sub.add_parser("snapshot", help="Take a portfolio snapshot now")
    p_backup = sub.add_parser("backup", help="Backup DB to Google Drive")
    p_backup.add_argument(
        "--folder",
        default=None,
        help="Drive folder name (overrides GOOGLE_DRIVE_BACKUP_FOLDER env var)",
    )

    # ── fetch-corp-actions ────────────────────────────────────────────────────
    p_corp = sub.add_parser("fetch-corp-actions",
                            help="Fetch and apply NSE corporate actions (bonus/split/dividend)")
    p_corp.add_argument("--asset-id", type=int, default=None, dest="asset_id",
                        help="Specific asset ID; omit to process all STOCK_IN assets")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "import":
        if not args.source:
            parser.parse_args(["import", "--help"])
            return
        member_id = resolve_member_id(args.pan)
        if args.source == "ppf":
            cmd_import_ppf(args.file, member_id)
        elif args.source == "epf":
            cmd_import_epf(args.file, member_id)
        elif args.source == "cas":
            cmd_import_cas(args.file, member_id)
        elif args.source == "nps":
            cmd_import_nps(args.file, member_id)
        elif args.source == "zerodha":
            cmd_import_broker_csv(args.file, broker="zerodha", member_id=member_id)
        elif args.source == "fidelity-rsu":
            cmd_import_fidelity_rsu(args.file, member_id)
        elif args.source == "fidelity-sale":
            cmd_import_fidelity_sale(args.file, member_id)

    elif args.command == "add":
        if not args.kind:
            parser.parse_args(["add", "--help"])
            return
        if args.kind == "fd":
            cmd_add_fd(args.name, args.bank, args.principal, args.rate,
                       args.start, args.maturity, args.compounding, args.matured)
        elif args.kind == "rd":
            cmd_add_rd(args.name, args.bank, args.installment, args.rate,
                       args.start, args.maturity, args.compounding)
        elif args.kind == "real-estate":
            cmd_add_real_estate(args.name, args.purchase_amount, args.purchase_date,
                                args.current_value, args.value_date)
        elif args.kind == "gold":
            cmd_add_gold(args.name, args.date, args.units, args.price)
        elif args.kind == "sgb":
            cmd_add_sgb(args.name, args.date, args.units, args.price)
        elif args.kind == "rsu":
            cmd_add_rsu(args.name, args.date, args.units, args.price, args.forex,
                        notes=args.notes, identifier=args.identifier)
        elif args.kind == "us-stock":
            cmd_add_us_stock(args.name, args.date, args.units, args.price, args.forex,
                             identifier=args.identifier)
        elif args.kind == "epf-contribution":
            cmd_add_epf_contribution(
                args.asset, args.month_year, args.employee_share,
                eps_share=args.eps_share,
                employer_share=args.employer_share,
                employee_interest=args.employee_interest,
                employer_interest=args.employer_interest,
                eps_interest=args.eps_interest,
            )
        elif args.kind == "valuation":
            cmd_add_valuation(args.asset, args.value, args.date)
        elif args.kind == "txn":
            cmd_add_txn(args.asset, args.txn_type, args.date, args.amount,
                        units=args.units, price=args.price, forex=args.forex, notes=args.notes)
        elif args.kind == "goal":
            cmd_add_goal(args.name, args.target, args.date,
                         assets=args.assets, notes=args.notes, assumed_return=args.assumed_return)

    elif args.command == "update":
        if not args.kind:
            parser.parse_args(["update", "--help"])
        elif args.kind == "goal-allocation":
            cmd_update_goal_allocation(args.goal, args.asset, args.pct)

    elif args.command == "remove":
        if not args.kind:
            parser.parse_args(["remove", "--help"])
        elif args.kind == "goal-allocation":
            cmd_remove_goal_allocation(args.goal, args.asset)

    elif args.command == "delete":
        if not args.kind:
            parser.parse_args(["delete", "--help"])
        elif args.kind == "goal":
            cmd_delete_goal(args.name)

    elif args.command == "list":
        if not args.resource:
            parser.parse_args(["list", "--help"])
        elif args.resource == "assets":
            cmd_list_assets()

    elif args.command == "fetch-corp-actions":
        cmd_fetch_corp_actions(args.asset_id)

    elif args.command == "add-member":
        cmd_add_member(args.pan, args.name)

    elif args.command == "refresh-prices":
        cmd_refresh_prices()

    elif args.command == "snapshot":
        cmd_snapshot()

    elif args.command == "backup":
        cmd_backup(folder=getattr(args, "folder", None))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

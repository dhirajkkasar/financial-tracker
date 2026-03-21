"""
Portfolio CLI — wraps the backend REST API for data loading and updates.

Usage (server must be running):
  python cli.py import ppf <file>
  python cli.py import epf <file>
  python cli.py import cas <file>
  python cli.py import nps <file>
  python cli.py import zerodha <file>
  python cli.py import groww <file>

  python cli.py add fd   --name "HDFC FD" --bank HDFC --principal 500000 --rate 7.1 --start 2024-01-15 --maturity 2025-01-15 --compounding QUARTERLY
  python cli.py add rd   --name "SBI RD"  --bank SBI  --installment 10000 --rate 6.5 --start 2024-01-01 --maturity 2026-01-01 --compounding QUARTERLY
  python cli.py add real-estate --name "Venezia Flat" --purchase-amount 7500000 --purchase-date 2020-11-09 --current-value 12000000 --value-date 2024-01-01
  python cli.py add gold  --name "Digital Gold" --date 2023-06-01 --units 10 --price 5800
  python cli.py add sgb   --name "SGB 2023-24 S3" --date 2023-12-01 --units 50 --price 6200
  python cli.py add rsu   --name "AMZN RSU" --date 2024-03-01 --units 10 --price 180.50 --forex 83.5 --notes "Perquisite tax: ..."
  python cli.py add us-stock --name "Apple" --identifier AAPL --date 2023-01-15 --units 5 --price 142.50 --forex 82.0

  python cli.py add valuation --asset "Venezia Flat" --value 13000000 --date 2025-01-01
  python cli.py add txn  --asset "AMZN RSU" --type VEST --date 2024-09-01 --amount -90000 --units 5 --price 215 --forex 84

  python cli.py list assets
  python cli.py refresh-prices
  python cli.py snapshot

Set PORTFOLIO_API env var to override the default base URL (http://localhost:8000).
"""

import argparse
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

def cmd_import_ppf(file_path: str) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        result = _api("post", "/import/ppf-pdf", files={"file": f})
    _print_import_summary("PPF", inserted=result["inserted"], skipped=result["skipped"], errors=result.get("errors", []))
    if result.get("valuation_created"):
        print(f"  → Valuation created: ₹{result['valuation_value']:,.2f} on {result['valuation_date']}")
    return result


def cmd_import_epf(file_path: str) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        result = _api("post", "/import/epf-pdf", files={"file": f})
    _print_import_summary("EPF", inserted=result["epf_inserted"], skipped=result["epf_skipped"], errors=result.get("errors", []))
    print(f"  EPS: {result['eps_inserted']} inserted, {result['eps_skipped']} skipped"
          + (" (asset created)" if result.get("eps_asset_created") else ""))
    return result


def cmd_import_cas(file_path: str) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        preview = _api("post", "/import/cas-pdf", files={"file": f})
    result = _api("post", "/import/commit", json={"preview_id": preview["preview_id"]})
    _print_import_summary("CAS", inserted=result["created_count"], skipped=result["skipped_count"])
    return result


def cmd_import_nps(file_path: str) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        preview = _api("post", "/import/nps-csv", files={"file": f})
    result = _api("post", "/import/commit", json={"preview_id": preview["preview_id"]})
    _print_import_summary("NPS", inserted=result["created_count"], skipped=result["skipped_count"])
    return result


def cmd_import_broker_csv(file_path: str, broker: str) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        preview = _api("post", f"/import/broker-csv?broker={broker}", files={"file": f})
    result = _api("post", "/import/commit", json={"preview_id": preview["preview_id"]})
    _print_import_summary(broker.title(), inserted=result["created_count"], skipped=result["skipped_count"])
    return result


# ── Add commands ──────────────────────────────────────────────────────────────

def cmd_add_fd(name: str, bank: str, principal: float, rate: float,
               start: str, maturity: str, compounding: str) -> dict:
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
    })
    txn = _api("post", f"/assets/{asset_id}/transactions", json={
        "type": "CONTRIBUTION", "date": start,
        "amount_inr": -principal, "charges_inr": 0.0,
    })
    print(f"✓ FD created: {name} (id={asset_id}) — ₹{principal:,.0f} @ {rate}% until {maturity}")
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


# ── Utility commands ──────────────────────────────────────────────────────────

def cmd_list_assets() -> list:
    assets = _api("get", "/assets")
    print(f"{'ID':<5} {'Name':<35} {'Type':<15} {'Active'}")
    print("─" * 65)
    for a in sorted(assets, key=lambda x: x["name"]):
        active = "✓" if a["is_active"] else "✗"
        print(f"{a['id']:<5} {a['name']:<35} {a['asset_type']:<15} {active}")
    return assets


def cmd_refresh_prices() -> dict:
    result = _api("post", "/prices/refresh-all")
    print("✓ Price refresh triggered")
    return result


def cmd_snapshot() -> dict:
    result = _api("post", "/snapshots/take")
    print(f"✓ Snapshot taken: {result.get('date')} — ₹{result.get('total_value_inr', 0):,.2f}")
    return result


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

    s = import_sub.add_parser("zerodha", help="Import Zerodha tradebook CSV")
    s.add_argument("file", help="Path to CSV")

    s = import_sub.add_parser("groww", help="Import Groww CSV")
    s.add_argument("file", help="Path to CSV")

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

    # ── utilities ─────────────────────────────────────────────────────────────
    sub.add_parser("refresh-prices", help="Trigger price refresh for all assets")
    sub.add_parser("snapshot", help="Take a portfolio snapshot now")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "import":
        if not args.source:
            parser.parse_args(["import", "--help"])
            return
        if args.source == "ppf":
            cmd_import_ppf(args.file)
        elif args.source == "epf":
            cmd_import_epf(args.file)
        elif args.source == "cas":
            cmd_import_cas(args.file)
        elif args.source == "nps":
            cmd_import_nps(args.file)
        elif args.source == "zerodha":
            cmd_import_broker_csv(args.file, broker="zerodha")
        elif args.source == "groww":
            cmd_import_broker_csv(args.file, broker="groww")

    elif args.command == "add":
        if not args.kind:
            parser.parse_args(["add", "--help"])
            return
        if args.kind == "fd":
            cmd_add_fd(args.name, args.bank, args.principal, args.rate,
                       args.start, args.maturity, args.compounding)
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
        elif args.kind == "valuation":
            cmd_add_valuation(args.asset, args.value, args.date)
        elif args.kind == "txn":
            cmd_add_txn(args.asset, args.txn_type, args.date, args.amount,
                        units=args.units, price=args.price, forex=args.forex, notes=args.notes)

    elif args.command == "list":
        if not args.resource:
            parser.parse_args(["list", "--help"])
        elif args.resource == "assets":
            cmd_list_assets()

    elif args.command == "refresh-prices":
        cmd_refresh_prices()

    elif args.command == "snapshot":
        cmd_snapshot()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

"""
PPF CSV parser for SBI Bank PPF Account Statements.

Parses transaction rows from the account statement CSV and returns a
PPFCSVImportResult with metadata for creating Valuation entries.

txn_id strategy:
  ppf_csv_{SHA256(account_number|txn_type|date_iso|amount_paise)}

Transaction type rules:
  - "INTEREST" in details  → INTEREST (positive inflow)
  - credit > 0, no interest → CONTRIBUTION (negative outflow)
  - debit > 0              → WITHDRAWAL (positive inflow)
"""
import csv
import hashlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.importers.base import ImportResult, ParsedTransaction, BaseImporter
from app.importers.registry import register_importer

logger = logging.getLogger(__name__)

# Maps first 4 chars of IFSC code → bank display name
IFSC_BANK_MAP = {
    "SBIN": "SBI",
    "HDFC": "HDFC Bank",
    "ICIC": "ICICI Bank",
    "PUNB": "Punjab National Bank",
    "BKID": "Bank of India",
    "UTIB": "Axis Bank",
    "BARB": "Bank of Baroda",
    "CNRB": "Canara Bank",
    "UBIN": "Union Bank of India",
    "IOBA": "Indian Overseas Bank",
}


@dataclass
class PPFCSVImportResult(ImportResult):
    """Extended ImportResult with PPF-specific metadata."""
    account_number: str = ""
    bank_name: str = ""
    asset_name: str = ""
    closing_balance_inr: float = 0.0
    closing_balance_date: Optional[date] = None


def _parse_inr_amount(s: str) -> Optional[float]:
    """Parse Indian number format like '1,50,000.00', '543.00', or '10,73,203.00CR'."""
    if not s or not s.strip() or s.strip() == "-":
        return None
    cleaned = s.replace(",", "").replace("CR", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date_dmy(s: str) -> Optional[date]:
    """Parse DD/MM/YYYY or DD-MM-YYYY."""
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _extract_after_colon(cell: str) -> Optional[str]:
    """Extract text after the last colon in a cell, stripped."""
    if ":" not in cell:
        return None
    return cell.split(":")[-1].strip()


def _make_txn_id(account_number: str, txn_type: str, txn_date: date, amount_paise: int) -> str:
    raw = f"{account_number}|{txn_type}|{txn_date.isoformat()}|{amount_paise}"
    return "ppf_csv_" + hashlib.sha256(raw.encode()).hexdigest()


@register_importer
class PPFCSVImporter(BaseImporter):
    source = "ppf"
    asset_type = "PPF"
    format = "csv"

    """Parses SBI PPF Account Statement CSV files."""

    def parse(self, file_bytes: bytes, filename: str = "") -> PPFCSVImportResult:
        result = PPFCSVImportResult(source="ppf_csv")

        try:
            text = file_bytes.decode("utf-8-sig", errors="replace")
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
        except Exception as e:
            result.errors.append(f"CSV read error: {e}")
            return result

        # ── Phase 1: scan header rows for metadata ──────────────────────────
        header_row_idx = None
        account_number = None
        ifsc_code = None
        closing_balance_inr = None
        closing_balance_date = None

        for idx, row in enumerate(rows):
            # Transaction header row: first cell is "Date"
            if row and row[0].strip() == "Date" and len(row) >= 7:
                header_row_idx = idx
                break

            for cell in row:
                cell = cell.strip()
                if not cell:
                    continue

                if account_number is None and "Account No" in cell:
                    val = _extract_after_colon(cell)
                    if val:
                        m = re.search(r"(\d{8,})", val)
                        if m:
                            account_number = m.group(1)

                if ifsc_code is None and "IFSC Code" in cell:
                    val = _extract_after_colon(cell)
                    if val:
                        m = re.search(r"([A-Z]{4}\d{7})", val)
                        if m:
                            ifsc_code = m.group(1)

                if closing_balance_inr is None and "Clear Balance" in cell:
                    m = re.search(r":\s*([\d,]+\.?\d*)\s*CR", cell)
                    if m:
                        closing_balance_inr = _parse_inr_amount(m.group(1))

                if closing_balance_date is None and "Date of Statement" in cell:
                    val = _extract_after_colon(cell)
                    if val:
                        closing_balance_date = _parse_date_dmy(val)

        if not account_number:
            result.errors.append("Could not extract account number from CSV")
            return result
        if header_row_idx is None:
            result.errors.append("Could not find transaction table in CSV")
            return result

        result.account_number = account_number
        bank_code = ifsc_code[:4] if ifsc_code and len(ifsc_code) >= 4 else ""
        result.bank_name = IFSC_BANK_MAP.get(bank_code, bank_code or "Unknown Bank")
        result.asset_name = f"PPF - {result.bank_name}"
        result.closing_balance_inr = closing_balance_inr or 0.0
        result.closing_balance_date = closing_balance_date

        # ── Phase 2: parse transaction rows ─────────────────────────────────
        transactions = []
        for row in rows[header_row_idx + 1:]:
            if not row or not row[0].strip():
                break  # blank row marks end of data

            txn_date = _parse_date_dmy(row[0])
            if not txn_date:
                continue

            details = row[1].strip() if len(row) > 1 else ""
            debit_str = row[5].strip() if len(row) > 5 else ""
            credit_str = row[6].strip() if len(row) > 6 else ""

            credit_amt = _parse_inr_amount(credit_str)
            debit_amt = _parse_inr_amount(debit_str)

            is_interest = "INTEREST" in details.upper()

            if credit_amt is not None and credit_amt > 0:
                if is_interest:
                    txn_type = "INTEREST"
                    amount_inr = credit_amt        # positive inflow
                else:
                    txn_type = "CONTRIBUTION"
                    amount_inr = -credit_amt       # negative outflow
            elif debit_amt is not None and debit_amt > 0:
                txn_type = "WITHDRAWAL"
                amount_inr = debit_amt             # positive inflow (money returned)
            else:
                continue

            amount_paise = round(abs(amount_inr) * 100)
            txn_id = _make_txn_id(account_number, txn_type, txn_date, amount_paise)

            transactions.append(ParsedTransaction(
                source="ppf_csv",
                asset_name=result.asset_name,
                asset_identifier=account_number,
                asset_type="PPF",
                txn_type=txn_type,
                date=txn_date,
                amount_inr=amount_inr,
                txn_id=txn_id,
            ))

        if not transactions:
            result.errors.append("No transactions found in PPF CSV")
        result.transactions = transactions

        # Fallback: use first transaction date as closing balance date
        if result.closing_balance_date is None and transactions:
            result.closing_balance_date = transactions[0].date

        return result

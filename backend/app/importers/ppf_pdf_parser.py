"""
PPF PDF parser for SBI Bank PPF Account Statements.

Parses transaction rows from the account statement PDF and returns an ImportResult
with additional metadata (closing_balance_inr, closing_balance_date, account_number)
for use by the import service when creating Valuation entries.

txn_id strategy:
  - When reference number exists: ppf_{ref_no}
  - Fallback: SHA256(account_number|CONTRIBUTION|date_iso|amount_paise)
"""
import hashlib
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pdfplumber

from app.importers.base import ImportResult, ParsedTransaction

logger = logging.getLogger(__name__)

# Month abbreviation → month number
MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


@dataclass
class PPFImportResult(ImportResult):
    """Extended ImportResult with PPF-specific metadata."""
    account_number: str = ""
    closing_balance_inr: float = 0.0
    closing_balance_date: Optional[date] = None


def _parse_date(date_str: str) -> Optional[date]:
    """Parse date strings like '29 May 2018' or '29 May\n2018'."""
    date_str = date_str.replace("\n", " ").strip()
    # Pattern: DD Mon YYYY
    m = re.match(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})", date_str)
    if m:
        day, mon, year = int(m.group(1)), MONTH_MAP[m.group(2)], int(m.group(3))
        return date(year, mon, day)
    return None


def _parse_amount(amount_str: str) -> Optional[float]:
    """Parse amount strings like '5,000.00' → 5000.0."""
    if not amount_str or not amount_str.strip():
        return None
    cleaned = amount_str.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_ref_no(ref_cell: str) -> Optional[str]:
    """
    Extract the reference number from the Ref No./Cheque No. cell.

    The cell text for the first transaction looks like:
      'TRANSFER\nFROM\n3199410044308'
    or for the second:
      'IF17658260\nTRANSFER\nFROM\n30466324987'

    We want the actual ref numbers (numeric or IF... patterns).
    """
    if not ref_cell:
        return None
    lines = [l.strip() for l in ref_cell.split("\n") if l.strip()]
    # Filter out generic words
    skip = {"TRANSFER", "FROM", "INVESTMENT", "DEPOSIT"}
    candidates = [l for l in lines if l not in skip]
    if not candidates:
        return None
    # Prefer lines that look like a reference number (purely numeric or alphanumeric starting with letters)
    for c in candidates:
        # Numeric ref: digits only (possibly long)
        if re.match(r'^\d{6,}$', c):
            return c
        # Alphanumeric ref like IF17658260
        if re.match(r'^[A-Z]{1,4}\d+$', c):
            return c
    # Fallback: first candidate
    return candidates[0] if candidates else None


def _make_txn_id(account_number: str, txn_date: date, amount_paise: int, ref_no: Optional[str]) -> str:
    if ref_no:
        return f"ppf_{ref_no}"
    raw = f"{account_number}|CONTRIBUTION|{txn_date.isoformat()}|{amount_paise}"
    return "ppf_" + hashlib.sha256(raw.encode()).hexdigest()


class PPFPDFParser:
    """Parses SBI PPF Account Statement PDFs."""

    def parse(self, file_bytes: bytes, filename: str = "") -> PPFImportResult:
        result = PPFImportResult(source="ppf_pdf")

        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                all_text = ""
                all_tables = []
                for page in pdf.pages:
                    all_text += (page.extract_text() or "") + "\n"
                    tables = page.extract_tables()
                    all_tables.extend(tables)

            # Extract account number
            account_number = self._extract_account_number(all_text)
            if not account_number:
                result.errors.append("Could not extract account number from PDF")
                return result
            result.account_number = account_number

            # Parse transactions from tables
            transactions, closing_balance, closing_date = self._parse_transactions(
                all_tables, account_number
            )

            if not transactions and not result.errors:
                result.errors.append("No transactions found in PPF statement")

            result.transactions = transactions
            result.closing_balance_inr = closing_balance or 0.0
            result.closing_balance_date = closing_date

        except Exception as e:
            logger.warning("PPF PDF parsing error: %s", e)
            result.errors.append(f"Parse error: {e}")

        return result

    def _extract_account_number(self, text: str) -> Optional[str]:
        """Extract and strip leading zeros from account number.

        The PDF may include (cid:9) sequences (tab substitutes) between the label
        and the value, so we use a broad pattern that matches any chars after the colon.
        """
        # Find line containing 'Account Number'
        for line in text.splitlines():
            if "Account Number" in line:
                # Extract the long digit sequence (account numbers are 10+ digits)
                m = re.search(r"(\d{10,})", line)
                if m:
                    raw = m.group(1).strip()
                    # Strip leading zeros but preserve at least one digit
                    return raw.lstrip("0") or raw
        return None

    def _parse_transactions(
        self, tables: list, account_number: str
    ) -> tuple[list[ParsedTransaction], Optional[float], Optional[date]]:
        """Parse transaction rows from extracted tables."""
        transactions = []
        closing_balance = None
        closing_date = None

        for table in tables:
            if not table:
                continue
            # Skip header row(s): detect by checking if first cell contains 'Txn Date' or 'Date'
            for row in table:
                if not row or len(row) < 6:
                    continue
                # Check if this is a header row
                first_cell = (row[0] or "").strip()
                if "Txn Date" in first_cell or "Date" == first_cell or "Particulars" in first_cell:
                    continue

                # Expected columns: [Txn Date, Value Date, Description, Ref No., Debit, Credit, Balance]
                txn_date_str = (row[0] or "").strip()
                ref_cell = (row[3] or "").strip() if len(row) > 3 else ""
                debit_str = (row[4] or "").strip() if len(row) > 4 else ""
                credit_str = (row[5] or "").strip() if len(row) > 5 else ""
                balance_str = (row[6] or "").strip() if len(row) > 6 else ""

                txn_date = _parse_date(txn_date_str)
                if not txn_date:
                    continue

                credit_amt = _parse_amount(credit_str)
                debit_amt = _parse_amount(debit_str)
                balance_amt = _parse_amount(balance_str)

                # Determine amount: credits are CONTRIBUTION inflows to PPF (money going in = outflow from user)
                if credit_amt is not None and credit_amt > 0:
                    amount_inr = -credit_amt  # outflow convention
                elif debit_amt is not None and debit_amt > 0:
                    amount_inr = debit_amt  # withdrawal = positive
                else:
                    continue

                amount_paise = round(abs(amount_inr) * 100)
                ref_no = _extract_ref_no(ref_cell)
                txn_id = _make_txn_id(account_number, txn_date, amount_paise, ref_no)

                txn = ParsedTransaction(
                    source="ppf_pdf",
                    asset_name=f"PPF — {account_number}",
                    asset_identifier=account_number,
                    asset_type="PPF",
                    txn_type="CONTRIBUTION",
                    date=txn_date,
                    amount_inr=amount_inr,
                    txn_id=txn_id,
                    notes=ref_no,
                )
                transactions.append(txn)

                # Track the last balance as closing balance
                if balance_amt is not None:
                    closing_balance = balance_amt
                    closing_date = txn_date

        return transactions, closing_balance, closing_date

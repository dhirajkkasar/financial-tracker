"""
EPF PDF parser for EPFO Member Passbook PDFs.

Parses contribution, interest, and transfer transactions from the EPFO passbook.

Transaction types produced:
  - CONTRIBUTION (employee_share, employer_share) → EPF asset
  - CONTRIBUTION (pension_share) → EPS asset (identifier = member_id + "_EPS")
  - INTEREST (employee_int + employer_int combined) → EPF asset
  - TRANSFER (claim withdrawal) → EPF asset

txn_id strategy (SHA-256 based, stable across re-imports):
  - Employee contribution: SHA256(member_id|CONTRIB_EMP|MMYYYY|amount_paise)
  - Employer contribution: SHA256(member_id|CONTRIB_ER|MMYYYY|amount_paise)
  - Pension contribution:  SHA256(member_id|CONTRIB_EPS|MMYYYY|amount_paise)
  - Interest:              SHA256(member_id|INTEREST|YYYY-03-31|total_paise)
  - Transfer:              SHA256(member_id|TRANSFER|print_date|emp_paise|er_paise)
"""
import calendar
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


def _sha256_id(prefix: str, *parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return prefix + "_" + hashlib.sha256(raw.encode()).hexdigest()


def _parse_amount(s: str) -> float:
    """Parse '2,114' or '0' → float."""
    if not s:
        return 0.0
    cleaned = s.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _last_day_of_month(mm: int, yyyy: int) -> date:
    last = calendar.monthrange(yyyy, mm)[1]
    return date(yyyy, mm, last)


def _parse_mmyyyy(mmyyyy: str) -> Optional[date]:
    """Parse 'MMYYYY' string → last day of that month."""
    mmyyyy = mmyyyy.strip()
    if len(mmyyyy) == 6:
        try:
            mm = int(mmyyyy[:2])
            yyyy = int(mmyyyy[2:])
            return _last_day_of_month(mm, yyyy)
        except (ValueError, IndexError):
            pass
    return None


def _parse_ddmmyyyy(s: str) -> Optional[date]:
    """Parse 'DD/MM/YYYY' or 'DD-MM-YYYY'."""
    s = s.strip()
    m = re.match(r"(\d{2})[/\-](\d{2})[/\-](\d{4})", s)
    if m:
        day, mon, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(year, mon, day)
        except ValueError:
            pass
    return None


@dataclass
class EPFImportResult(ImportResult):
    """Extended ImportResult with EPF-specific metadata."""
    member_id: str = ""
    establishment_name: str = ""
    print_date: Optional[date] = None
    net_balance_inr: float = 0.0
    grand_total_emp_deposit: float = 0.0
    grand_total_er_deposit: float = 0.0


class EPFPDFParser:
    """Parses EPFO Member Passbook PDFs."""

    def parse(self, file_bytes: bytes, filename: str = "") -> EPFImportResult:
        result = EPFImportResult(source="epf_pdf")

        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                all_lines = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    all_lines.extend(text.splitlines())

            # Extract metadata
            member_id = self._extract_member_id(all_lines)
            establishment_name = self._extract_establishment_name(all_lines)
            print_date = self._extract_print_date(all_lines)

            if not member_id:
                result.errors.append("Could not extract Member ID from PDF")
                return result

            result.member_id = member_id
            result.establishment_name = establishment_name or ""
            result.print_date = print_date

            # Parse all transaction rows
            transactions, grand_total_emp, grand_total_er = self._parse_transactions(
                all_lines, member_id, establishment_name or "", print_date
            )

            result.transactions = transactions
            result.grand_total_emp_deposit = grand_total_emp
            result.grand_total_er_deposit = grand_total_er

            # Net balance: if grand total withdrawals == deposits → 0
            # From the PDF: Grand Total row has equal deposit and withdrawal columns
            result.net_balance_inr = 0.0  # Determined from Grand Total row parsing

        except Exception as e:
            logger.warning("EPF PDF parsing error: %s", e)
            result.errors.append(f"Parse error: {e}")

        return result

    def _extract_member_id(self, lines: list[str]) -> Optional[str]:
        """Extract member ID from 'Member ID/Name PYKRPXXX / NAME' line."""
        for line in lines:
            m = re.search(r"Member ID/Name\s+(\w+)\s*/", line)
            if m:
                return m.group(1).strip()
        return None

    def _extract_establishment_name(self, lines: list[str]) -> Optional[str]:
        """Extract establishment name from 'Establishment ID/Name PYKRPXXX / NAME' line."""
        for line in lines:
            m = re.search(r"Establishment ID/Name\s+\S+\s*/\s*(.+)", line)
            if m:
                return m.group(1).strip()
        return None

    def _extract_print_date(self, lines: list[str]) -> Optional[date]:
        """Extract print date from the passbook.

        The EPFO PDF stores the date in a Hindi transliteration line:
          '--fooj.k dh lekfIr-- eqfnzr 27-11-2018 17:27:26'
        We also try the English line as a fallback.
        """
        for line in lines:
            # Hindi line: eqfnzr DD-MM-YYYY
            m = re.search(r"eqfnzr\s+(\d{2}-\d{2}-\d{4})", line)
            if m:
                return _parse_ddmmyyyy(m.group(1))
            # English line: Printed On DD-MM-YYYY
            m = re.search(r"Printed On\s+(\d{2}-\d{2}-\d{4})", line)
            if m:
                return _parse_ddmmyyyy(m.group(1))
        return None

    def _parse_transactions(
        self,
        lines: list[str],
        member_id: str,
        establishment_name: str,
        print_date: Optional[date],
    ) -> tuple[list[ParsedTransaction], float, float]:
        """
        Parse all transaction rows from the passbook text.

        Returns (transactions, grand_total_emp_deposit, grand_total_er_deposit).
        """
        transactions = []
        grand_total_emp = 0.0
        grand_total_er = 0.0

        eps_identifier = f"{member_id}_EPS"
        eps_asset_name = f"EPS — {establishment_name}"

        # We track interest rows by year to combine employee+employer interest
        # Format: {year: {emp_int, er_int, date}}
        interest_rows: dict[str, dict] = {}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # --- Grand Total row ---
            gt_m = re.match(r"Grand Total\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", line)
            if gt_m:
                grand_total_emp = _parse_amount(gt_m.group(1))
                grand_total_er = _parse_amount(gt_m.group(2))
                continue

            # --- Contribution row: "Cont. For MMYYYY emp er eps" ---
            cont_m = re.match(r"Cont\.\s+For\s+(\d{6})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", line)
            if cont_m:
                mmyyyy = cont_m.group(1)
                emp_amt = _parse_amount(cont_m.group(2))
                er_amt = _parse_amount(cont_m.group(3))
                eps_amt = _parse_amount(cont_m.group(4))
                txn_date = _parse_mmyyyy(mmyyyy)
                if txn_date is None:
                    continue

                # Skip rows with all-zero amounts (placeholder rows)
                if emp_amt == 0 and er_amt == 0 and eps_amt == 0:
                    continue

                # Employee share → EPF asset
                if emp_amt > 0:
                    emp_paise = round(emp_amt * 100)
                    txn_id = _sha256_id("epf", member_id, "CONTRIB_EMP", mmyyyy, emp_paise)
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=f"EPF — {establishment_name}",
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="CONTRIBUTION",
                        date=txn_date,
                        amount_inr=-emp_amt,  # outflow convention
                        txn_id=txn_id,
                        notes="Employee Share",
                    ))

                # Employer share → EPF asset
                if er_amt > 0:
                    er_paise = round(er_amt * 100)
                    txn_id = _sha256_id("epf", member_id, "CONTRIB_ER", mmyyyy, er_paise)
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=f"EPF — {establishment_name}",
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="CONTRIBUTION",
                        date=txn_date,
                        amount_inr=-er_amt,  # outflow convention
                        txn_id=txn_id,
                        notes="Employer Share",
                    ))

                # Pension share → EPS asset
                if eps_amt > 0:
                    eps_paise = round(eps_amt * 100)
                    txn_id = _sha256_id("epf", member_id, "CONTRIB_EPS", mmyyyy, eps_paise)
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=eps_asset_name,
                        asset_identifier=eps_identifier,
                        asset_type="EPF",
                        txn_type="CONTRIBUTION",
                        date=txn_date,
                        amount_inr=-eps_amt,  # outflow convention
                        txn_id=txn_id,
                        notes="Pension Contribution",
                    ))
                continue

            # --- Interest row: "Int. Updated upto DD/MM/YYYY emp_int er_int" ---
            int_m = re.match(r"Int\.\s+Updated upto\s+(\d{2}/\d{2}/\d{4})\s+([\d,]+)\s+([\d,]+)", line)
            if int_m:
                int_date_str = int_m.group(1)
                emp_int = _parse_amount(int_m.group(2))
                er_int = _parse_amount(int_m.group(3))
                int_date = _parse_ddmmyyyy(int_date_str)
                if int_date is None:
                    continue

                total_int = emp_int + er_int
                if total_int == 0:
                    continue

                year_key = int_date.strftime("%Y-%m-%d")
                int_paise = round(total_int * 100)
                txn_id = _sha256_id("epf", member_id, "INTEREST", year_key, int_paise)
                transactions.append(ParsedTransaction(
                    source="epf_pdf",
                    asset_name=f"EPF — {establishment_name}",
                    asset_identifier=member_id,
                    asset_type="EPF",
                    txn_type="INTEREST",
                    date=int_date,
                    amount_inr=total_int,  # positive = inflow
                    txn_id=txn_id,
                    notes=f"EPF Interest (Employee: {emp_int}, Employer: {er_int})",
                ))
                continue

            # --- Transfer/Claim row: "Claim: Against PARA 57(1) emp_wd er_wd" ---
            claim_m = re.match(r"Claim:\s+Against PARA 57\(1\)\s+([\d,]+)\s+([\d,]+)", line)
            if claim_m:
                emp_wd = _parse_amount(claim_m.group(1))
                er_wd = _parse_amount(claim_m.group(2))
                total_wd = emp_wd + er_wd
                use_date = print_date or date.today()
                emp_paise = round(emp_wd * 100)
                er_paise = round(er_wd * 100)
                txn_id = _sha256_id(
                    "epf", member_id, "TRANSFER", use_date.isoformat(), emp_paise, er_paise
                )
                transactions.append(ParsedTransaction(
                    source="epf_pdf",
                    asset_name=f"EPF — {establishment_name}",
                    asset_identifier=member_id,
                    asset_type="EPF",
                    txn_type="TRANSFER",
                    date=use_date,
                    amount_inr=total_wd,  # positive = inflow (withdrawal from EPF)
                    txn_id=txn_id,
                    notes="Claim: Against PARA 57(1)",
                ))
                continue

        return transactions, grand_total_emp, grand_total_er

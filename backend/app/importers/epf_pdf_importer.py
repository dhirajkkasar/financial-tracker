"""
EPF PDF parser for EPFO Member Passbook PDFs.

Parses ONLY page 1 of each passbook (page 2 contains taxable-data breakdowns
with different interest splits — using it would create duplicate/wrong transactions).

Transaction types produced (all on the single EPF asset, identified by member_id):
  - CONTRIBUTION (notes="Employee Share")          → employee EPF contributions
  - CONTRIBUTION (notes="Employer Share")          → employer EPF contributions
  - CONTRIBUTION (notes="Pension Contribution (EPS)") → EPS/pension contributions
  - CONTRIBUTION (notes="Transfer In - Employee Share")  → transfer-in from old employer
  - CONTRIBUTION (notes="Transfer In - Employer Share")  → transfer-in from old employer
  - INTEREST     (notes="Employee Interest")       → annual interest on employee account
  - INTEREST     (notes="Employer Interest")       → annual interest on employer account
  - INTEREST     (notes="EPS Interest")            → annual interest on EPS (usually 0)
  - INTEREST     (notes="TDS Deduction")           → TDS deducted from employee interest
  - TRANSFER     (notes="Claim: Against PARA 57(1)") → EPF withdrawal

Interest rows: produced only when "Int. Updated upto DD/MM/YYYY" is present on page 1.
  If EPS interest is 0, it is still recorded (for data completeness).
  If the interest row is absent (shows "Interest details N/A"), no interest txns are created.

txn_id strategy (SHA-256 based, stable across re-imports):
  - Employee contribution:    SHA256(member_id|CONTRIB_EMP|MMYYYY|emp_paise)
  - Employer contribution:    SHA256(member_id|CONTRIB_ER|MMYYYY|er_paise)
  - Pension contribution:     SHA256(member_id|CONTRIB_EPS|MMYYYY|eps_paise)
  - Transfer-in employee:     SHA256(member_id|TRANSFER_IN_EMP|DD-MM-YYYY|emp_paise)
  - Transfer-in employer:     SHA256(member_id|TRANSFER_IN_ER|DD-MM-YYYY|er_paise)
  - Employee interest:        SHA256(member_id|INTEREST_EMP|YYYY-MM-DD|emp_paise)
  - Employer interest:        SHA256(member_id|INTEREST_ER|YYYY-MM-DD|er_paise)
  - EPS interest:             SHA256(member_id|INTEREST_EPS|YYYY-MM-DD|eps_paise)
  - TDS deduction:            SHA256(member_id|TDS_EMP|YYYY-MM-DD|tds_paise)
  - Transfer/claim:           SHA256(member_id|TRANSFER|print_date|emp_paise|er_paise)
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

from app.importers.base import ImportResult, ParsedTransaction, BaseImporter
from app.importers.registry import register_importer

logger = logging.getLogger(__name__)


def _sha256_id(prefix: str, *parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return prefix + "_" + hashlib.sha256(raw.encode()).hexdigest()


def _parse_amount(s: str) -> float:
    """Parse '2,114' or '-660' or '0' → float."""
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


@register_importer
class EPFPDFImporter(BaseImporter):
    source = "epf"
    asset_type = "EPF"
    format = "pdf"

    """Parses EPFO Member Passbook PDFs (page 1 only)."""

    def __init__(self, **_kwargs):
        pass

    def parse(self, file_bytes: bytes, filename: str = "") -> EPFImportResult:
        result = EPFImportResult(source="epf_pdf")

        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                if not pdf.pages:
                    result.errors.append("PDF has no pages")
                    return result
                # Only parse page 1 — page 2 contains taxable-breakdown data with
                # different interest splits that would create duplicate transactions.
                page1_text = pdf.pages[0].extract_text() or ""
                all_lines = page1_text.splitlines()

            # Extract metadata (also present on page 1)
            member_id = self._extract_member_id(all_lines)
            establishment_name = self._extract_establishment_name(all_lines)
            print_date = self._extract_print_date(all_lines)

            if not member_id:
                result.errors.append("Could not extract Member ID from PDF")
                return result

            result.member_id = member_id
            result.establishment_name = establishment_name or ""
            result.print_date = print_date

            transactions, grand_total_emp, grand_total_er = self._parse_transactions(
                all_lines, member_id, establishment_name or "", print_date
            )

            result.transactions = transactions
            result.grand_total_emp_deposit = grand_total_emp
            result.grand_total_er_deposit = grand_total_er
            result.net_balance_inr = 0.0  # EPF returns are computed from transactions

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
        """Extract establishment name from the passbook header.

        New format: the label line is "... | Establishment ID/Name" with the
        actual "CODE / NAME_PART1" on the previous line and NAME_PART2 on the next.
        Old format: everything on one line "Establishment ID/Name CODE / NAME".
        """
        for i, line in enumerate(lines):
            if "Establishment ID/Name" not in line:
                continue
            # Old format: label and value on same line
            m = re.search(r"Establishment ID/Name\s+\S+\s*/\s*(.+)", line)
            if m:
                return m.group(1).strip()
            # New format: value split across previous line (CODE / NAME_START) and next line (NAME_END)
            parts = []
            if i > 0:
                prev = lines[i - 1].strip()
                m = re.search(r"/\s*(.+)", prev)
                if m:
                    parts.append(m.group(1).strip())
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                _skip = re.search(r"Member|lnL;|UAN|Date of Birth|EPF Passbook|foÙkh", nxt)
                if nxt and not _skip:
                    parts.append(nxt)
            if parts:
                return " ".join(parts)
        return None

    def _extract_print_date(self, lines: list[str]) -> Optional[date]:
        """Extract print date from the passbook.

        Handles both formats:
          Old: '--fooj.k dh lekfIr-- eqfnzr 27-11-2018 17:27:26'
          New: '...eqfnzr/Printed On : 24-03-2026 15:07:02'
        """
        for line in lines:
            m = re.search(r"(?:eqfnzr|Printed On)[^0-9]*(\d{2}-\d{2}-\d{4})", line)
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
        Parse all transaction rows from page 1 of the passbook.

        Returns (transactions, grand_total_emp_deposit, grand_total_er_deposit).

        Interest rows produce 3 separate INTEREST transactions (employee, employer, EPS).
        Transfer-in rows (from old employer) produce CONTRIBUTION transactions.
        TDS deduction rows produce negative INTEREST transactions.
        """
        transactions = []
        grand_total_emp = 0.0
        grand_total_er = 0.0

        # Track the last interest date for associating TDS deductions with a year
        last_interest_date: Optional[date] = None

        asset_name = f"EPF — {establishment_name}"

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # --- Grand Total row (summary, skip) ---
            if re.match(r"Grand Total\b", line):
                gt_m = re.match(r"Grand Total\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", line)
                if gt_m:
                    grand_total_emp = _parse_amount(gt_m.group(1))
                    grand_total_er = _parse_amount(gt_m.group(2))
                continue

            # --- Skip summary/total rows ---
            if re.match(r"Total\s+(Contributions|Transfer|Withdrawals)\b", line, re.IGNORECASE):
                continue

            # --- Contribution row ---
            # Format: "MonthName-YYYY DD-MM-YYYY CR Cont. For Due-Month MMYYYY emp_wages er_wages emp_epf er_epf eps"
            cont_m = re.search(
                r"Cont\.\s+For\s+(?:Due-Month\s+)?(\d{6})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)",
                line,
            )
            if cont_m:
                mmyyyy = cont_m.group(1)
                # groups 2,3 are wages (emp/er) — skip; groups 4,5,6 are EPF emp, EPF er, EPS
                emp_amt = _parse_amount(cont_m.group(4))
                er_amt = _parse_amount(cont_m.group(5))
                eps_amt = _parse_amount(cont_m.group(6))
                txn_date = _parse_mmyyyy(mmyyyy)
                if txn_date is None:
                    continue

                if emp_amt == 0 and er_amt == 0 and eps_amt == 0:
                    continue

                if emp_amt > 0:
                    emp_paise = round(emp_amt * 100)
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=asset_name,
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="CONTRIBUTION",
                        date=txn_date,
                        amount_inr=-emp_amt,
                        txn_id=_sha256_id("epf", member_id, "CONTRIB_EMP", mmyyyy, emp_paise),
                        notes="Employee Share",
                    ))

                if er_amt > 0:
                    er_paise = round(er_amt * 100)
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=asset_name,
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="CONTRIBUTION",
                        date=txn_date,
                        amount_inr=-er_amt,
                        txn_id=_sha256_id("epf", member_id, "CONTRIB_ER", mmyyyy, er_paise),
                        notes="Employer Share",
                    ))

                if eps_amt > 0:
                    eps_paise = round(eps_amt * 100)
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=asset_name,
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="CONTRIBUTION",
                        date=txn_date,
                        amount_inr=-eps_amt,
                        txn_id=_sha256_id("epf", member_id, "CONTRIB_EPS", mmyyyy, eps_paise),
                        notes="Pension Contribution (EPS)",
                    ))
                continue

            # --- Interest row: "Int. Updated upto DD/MM/YYYY emp_int er_int eps_int" ---
            # Note: "OB Int. Updated upto ..." starts with "OB" and is the opening balance —
            # re.match anchors at start so it won't match that line.
            int_m = re.match(
                r"Int\.\s+Updated upto\s+(\d{2}/\d{2}/\d{4})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)",
                line,
            )
            if int_m:
                int_date = _parse_ddmmyyyy(int_m.group(1))
                if int_date is None:
                    continue

                emp_int = _parse_amount(int_m.group(2))
                er_int = _parse_amount(int_m.group(3))
                eps_int = _parse_amount(int_m.group(4))

                # Skip if all zero (interest not yet credited / N/A)
                if emp_int == 0 and er_int == 0 and eps_int == 0:
                    continue

                last_interest_date = int_date
                year_key = int_date.strftime("%Y-%m-%d")

                transactions.append(ParsedTransaction(
                    source="epf_pdf",
                    asset_name=asset_name,
                    asset_identifier=member_id,
                    asset_type="EPF",
                    txn_type="INTEREST",
                    date=int_date,
                    amount_inr=emp_int,
                    txn_id=_sha256_id("epf", member_id, "INTEREST_EMP", year_key, round(emp_int * 100)),
                    notes="Employee Interest",
                ))

                transactions.append(ParsedTransaction(
                    source="epf_pdf",
                    asset_name=asset_name,
                    asset_identifier=member_id,
                    asset_type="EPF",
                    txn_type="INTEREST",
                    date=int_date,
                    amount_inr=er_int,
                    txn_id=_sha256_id("epf", member_id, "INTEREST_ER", year_key, round(er_int * 100)),
                    notes="Employer Interest",
                ))

                # EPS interest: always record when interest row is present, even if 0
                transactions.append(ParsedTransaction(
                    source="epf_pdf",
                    asset_name=asset_name,
                    asset_identifier=member_id,
                    asset_type="EPF",
                    txn_type="INTEREST",
                    date=int_date,
                    amount_inr=eps_int,
                    txn_id=_sha256_id("epf", member_id, "INTEREST_EPS", year_key, round(eps_int * 100)),
                    notes="EPS Interest",
                ))
                continue

            # --- TDS deduction row ---
            # Format: "Deduction of TDS on int on EE Cont Amt above 2.5 L -660 0 0"
            # Only on page 1; appears after the interest row for that year.
            tds_m = re.match(r"Deduction of TDS\b.*?([-\d,]+)\s+([-\d,]+)\s+([-\d,]+)\s*$", line)
            if tds_m:
                emp_tds = _parse_amount(tds_m.group(1))
                er_tds = _parse_amount(tds_m.group(2))
                eps_tds = _parse_amount(tds_m.group(3))
                use_date = last_interest_date or print_date or date.today()
                year_key = use_date.strftime("%Y-%m-%d")

                if emp_tds != 0:
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=asset_name,
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="INTEREST",
                        date=use_date,
                        amount_inr=emp_tds,  # negative = reduces current value
                        txn_id=_sha256_id("epf", member_id, "TDS_EMP", year_key, round(abs(emp_tds) * 100)),
                        notes="TDS Deduction",
                    ))
                if er_tds != 0:
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=asset_name,
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="INTEREST",
                        date=use_date,
                        amount_inr=er_tds,
                        txn_id=_sha256_id("epf", member_id, "TDS_ER", year_key, round(abs(er_tds) * 100)),
                        notes="TDS Deduction",
                    ))
                continue

            # --- Transfer/Claim withdrawal row: "Claim: Against PARA 57(1) emp_wd er_wd" ---
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
                    asset_name=asset_name,
                    asset_identifier=member_id,
                    asset_type="EPF",
                    txn_type="TRANSFER",
                    date=use_date,
                    amount_inr=total_wd,  # positive = inflow (withdrawal from EPF to member)
                    txn_id=txn_id,
                    notes="Claim: Against PARA 57(1)",
                ))
                continue

            # --- Transfer-in row (from old employer) ---
            # Format: "Month-YYYY DD-MM-YYYY CR [description] emp_wages er_wages emp_epf er_epf eps"
            # These are CR rows that do NOT contain "Cont. For".
            # We extract the last 5 number tokens as [emp_wages, er_wages, emp_epf, er_epf, eps].
            cr_m = re.match(r"[A-Za-z]{3}-\d{4}\s+(\d{2}-\d{2}-\d{4})\s+CR\b", line)
            if cr_m and "Cont. For" not in line:
                txn_date = _parse_ddmmyyyy(cr_m.group(1))
                if txn_date is None:
                    continue

                tokens = re.findall(r"[\d,]+", line)
                if len(tokens) < 5:
                    continue  # not enough numbers (e.g. a label-only CR line)

                last5 = tokens[-5:]
                emp_epf = _parse_amount(last5[2])
                er_epf = _parse_amount(last5[3])
                eps_epf = _parse_amount(last5[4])

                if emp_epf == 0 and er_epf == 0 and eps_epf == 0:
                    continue

                date_key = txn_date.isoformat()

                if emp_epf > 0:
                    emp_paise = round(emp_epf * 100)
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=asset_name,
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="CONTRIBUTION",
                        date=txn_date,
                        amount_inr=-emp_epf,
                        txn_id=_sha256_id("epf", member_id, "TRANSFER_IN_EMP", date_key, emp_paise),
                        notes="Transfer In - Employee Share",
                    ))

                if er_epf > 0:
                    er_paise = round(er_epf * 100)
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=asset_name,
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="CONTRIBUTION",
                        date=txn_date,
                        amount_inr=-er_epf,
                        txn_id=_sha256_id("epf", member_id, "TRANSFER_IN_ER", date_key, er_paise),
                        notes="Transfer In - Employer Share",
                    ))

                if eps_epf > 0:
                    eps_paise = round(eps_epf * 100)
                    transactions.append(ParsedTransaction(
                        source="epf_pdf",
                        asset_name=asset_name,
                        asset_identifier=member_id,
                        asset_type="EPF",
                        txn_type="CONTRIBUTION",
                        date=txn_date,
                        amount_inr=-eps_epf,
                        txn_id=_sha256_id("epf", member_id, "TRANSFER_IN_EPS", date_key, eps_paise),
                        notes="Transfer In - Pension (EPS)",
                    ))
                continue

        return transactions, grand_total_emp, grand_total_er

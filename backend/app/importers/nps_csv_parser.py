import csv
import hashlib
import io
import logging
from datetime import datetime
from typing import Optional

from app.importers.base import ParsedTransaction, ImportResult

logger = logging.getLogger(__name__)


class NPSImporter:
    """Parses NPS transaction statement CSV (multi-section format)."""

    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
        result = ImportResult(source="nps")
        try:
            text = file_bytes.decode("utf-8-sig")
            lines = text.strip().split("\n")
            tier = self._detect_tier(lines)
            txn_section = self._find_transaction_section(lines)
            if txn_section is None:
                result.warnings.append("No 'Transaction Details' section found")
                return result
            schemes = self._parse_scheme_blocks(txn_section)
            for scheme_name, rows in schemes:
                for row in rows:
                    txn = self._parse_transaction_row(row, scheme_name, tier)
                    if txn is not None:
                        result.transactions.append(txn)
        except Exception as e:
            result.errors.append(f"Failed to parse NPS file: {e}")
        return result

    def _detect_tier(self, lines: list[str]) -> str:
        for line in lines[:5]:
            if "Tier II" in line or "Tier 2" in line:
                return "II"
            if "Tier I" in line or "Tier 1" in line:
                return "I"
        return "I"

    def _find_transaction_section(self, lines: list[str]) -> Optional[list[str]]:
        for i, line in enumerate(lines):
            if line.strip().startswith("Transaction Details"):
                return lines[i + 1:]
        return None

    def _parse_scheme_blocks(
        self, lines: list[str]
    ) -> list[tuple[str, list[dict]]]:
        """Returns [(scheme_name, [row_dicts]), ...]"""
        schemes: list[tuple[str, list[dict]]] = []
        current_scheme: Optional[str] = None
        current_rows: list[dict] = []
        header_seen = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check if this is a scheme name line
            if self._is_scheme_name(stripped):
                if current_scheme is not None and current_rows:
                    schemes.append((current_scheme, current_rows))
                current_scheme = stripped
                current_rows = []
                header_seen = False
                continue

            # Check if this is the header line
            if stripped.startswith("Date,Description"):
                header_seen = True
                continue

            if header_seen and current_scheme and "," in stripped:
                parts = self._split_csv_line(stripped)
                if len(parts) >= 2:
                    current_rows.append(
                        {
                            "date": parts[0].strip(),
                            "description": parts[1].strip(),
                            "amount": parts[2].strip() if len(parts) > 2 else "",
                            "nav": parts[3].strip() if len(parts) > 3 else "",
                            "units": parts[4].strip() if len(parts) > 4 else "",
                        }
                    )

        if current_scheme is not None and current_rows:
            schemes.append((current_scheme, current_rows))

        return schemes

    def _is_scheme_name(self, line: str) -> bool:
        upper = line.upper()
        return (
            ("SCHEME" in upper or "FUND" in upper)
            and "TIER" in upper
            and not line.startswith("Date")
        )

    def _split_csv_line(self, line: str) -> list[str]:
        reader = csv.reader(io.StringIO(line))
        return next(reader, [])

    def _parse_amount(self, s: str) -> Optional[float]:
        if not s:
            return None
        s = s.strip()
        negative = s.startswith("(") and s.endswith(")")
        if negative:
            s = s[1:-1]
        try:
            val = float(s)
            return -val if negative else val
        except ValueError:
            return None

    def _parse_transaction_row(
        self, row: dict, scheme_name: str, tier: str
    ) -> Optional[ParsedTransaction]:
        desc = row["description"]

        # Skip opening/closing balance
        if "Opening balance" in desc or "Closing Balance" in desc:
            return None

        # Parse date
        try:
            txn_date = datetime.strptime(row["date"], "%d-%b-%Y").date()
        except ValueError:
            return None

        amount = self._parse_amount(row["amount"])
        units = self._parse_amount(row["units"])
        nav = self._parse_amount(row["nav"])

        if amount is None:
            return None

        # Determine transaction type
        if "Contribution" in desc:
            txn_type = "CONTRIBUTION"
            # Contributions are outflows -- amount should be negative
            if amount > 0:
                amount = -amount
        elif "Billing" in desc:
            # Billing charges: skip from transactions
            # (not a contribution, not meaningful for portfolio tracking)
            return None
        else:
            # Unknown type -- skip
            return None

        # Generate stable txn_id via SHA-256
        hash_input = f"{scheme_name}|{txn_date}|{desc}|{amount}"
        txn_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        txn_id = f"nps_{txn_hash}"

        notes = f"Tier {tier}"

        return ParsedTransaction(
            source="nps",
            asset_name=scheme_name,
            asset_identifier=scheme_name,
            asset_type="NPS",
            txn_type=txn_type,
            date=txn_date,
            units=abs(units) if units is not None else None,
            price_per_unit=nav,
            amount_inr=amount,
            txn_id=txn_id,
            notes=notes,
        )

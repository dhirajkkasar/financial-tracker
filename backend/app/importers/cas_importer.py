import hashlib
import io
import logging
import re
from datetime import datetime
from typing import Optional

import pdfplumber

from app.importers.base import ParsedTransaction, ParsedFundSnapshot, ImportResult, BaseImporter
from app.importers.registry import register_importer
from app.engine.mf_scheme_lookup import lookup_by_isin
from app.engine.mf_classifier import classify_mf

logger = logging.getLogger(__name__)


@register_importer
class CASImporter(BaseImporter):
    source = "cas"
    asset_type = "MF"
    format = "pdf"
    """Parses CAMS/KFintech Consolidated Account Statement PDFs."""

    FOLIO_PATTERN = re.compile(r"Folio No:\s*([\d\s/]+)")
    ISIN_PATTERN = re.compile(r"ISIN:\s*(\w+)")
    DATE_LINE_PATTERN = re.compile(r"^(\d{2}-[A-Za-z]{3}-\d{4})\s+(.+)")
    NUMBER_TOKEN = re.compile(r"[\d,]+\.\d+")
    STAMP_DUTY_PATTERN = re.compile(r"\*\*\*\s*Stamp Duty\s*\*\*\*")
    SCHEME_PREFIX_PATTERN = re.compile(r"^[A-Z0-9]+[A-Z]-")
    CLOSING_BALANCE_PATTERN = re.compile(
        r"Closing Unit Balance:\s*([\d,]+\.?\d*)"
        r"\s+NAV on (\d{2}-[A-Za-z]{3}-\d{4}):\s*INR\s*([\d,]+\.?\d*)"
        r"\s+Total Cost Value:\s*([\d,]+\.?\d*)"
        r"\s+Market Value on \d{2}-[A-Za-z]{3}-\d{4}:\s*INR\s*([\d,]+\.?\d*)"
    )

    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
        result = ImportResult(source="cas")
        try:
            text = self._extract_text(file_bytes)
            lines = text.split("\n")
            self._parse_lines(lines, result)
        except Exception as e:
            result.errors.append(f"Failed to parse CAS PDF: {e}")
            logger.warning("CAS parse error: %s", e)
        print(f"Parsed {len(result.transactions)} transactions and {len(result.snapshots)} snapshots from CAS")
        print(result.snapshots)
        return result

    def _extract_text(self, file_bytes: bytes) -> str:
        all_text = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)
        return "\n".join(all_text)

    def _parse_lines(self, lines: list[str], result: ImportResult):
        current_folio: Optional[str] = None
        current_isin: Optional[str] = None
        current_scheme_name: Optional[str] = None
        in_transactions = False

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # Check for folio line
            folio_match = self.FOLIO_PATTERN.search(stripped)
            if folio_match:
                current_folio = folio_match.group(1).strip()
                # Reset scheme info for this folio section
                current_isin = None
                current_scheme_name = None
                in_transactions = False
                continue

            # Check for ISIN — can appear on the scheme name line or a subsequent line
            isin_match = self.ISIN_PATTERN.search(stripped)
            if isin_match and current_folio and not in_transactions:
                current_isin = isin_match.group(1)
                current_scheme_name = self._extract_scheme_name(stripped, lines, i)
                in_transactions = False
                continue

            # Opening balance → start of transaction rows
            if "Opening Unit Balance:" in stripped:
                in_transactions = True
                continue

            # Closing balance → end of transaction section; extract snapshot
            print("********************")
            print(stripped)
            print("********************")
            if "Closing Unit Balance:" in stripped:
                in_transactions = False
                snap = self._parse_closing_balance(
                    stripped, current_isin, current_scheme_name
                )
                print(f"Parsed snapshot: {snap}")
                if snap:
                    result.snapshots.append(snap)
                continue

            # No transactions marker
            if "No transactions during this statement period" in stripped:
                in_transactions = False
                continue

            # Skip stamp duty lines
            if self.STAMP_DUTY_PATTERN.search(stripped):
                continue

            # Parse transaction row
            if in_transactions and current_folio and current_isin:
                txn = self._parse_transaction_line(
                    stripped, current_folio, current_isin, current_scheme_name
                )
                if txn:
                    result.transactions.append(txn)

    def _extract_scheme_name(self, isin_line: str, all_lines: list[str], line_idx: int) -> str:
        """Extract clean scheme name from the line containing the ISIN."""
        # The scheme name is the part before "- ISIN:" or before "ISIN:"
        # Sometimes ISIN is on the same line as scheme name, sometimes on next line
        text = isin_line

        # If ISIN is on a separate line from the scheme name, look at previous lines
        # for the scheme name (between Folio/Nominee line and this line)
        # But typically ISIN is embedded in the scheme line itself.

        # Split at ISIN
        parts = re.split(r"\s*-?\s*ISIN:", text)
        name = parts[0] if parts else text

        # Remove registrar info
        name = re.split(r"\s*Registrar\s*:", name)[0]

        # Remove scheme code prefix (e.g., "HHMCDG-", "K1155D-", "B92-")
        name = self.SCHEME_PREFIX_PATTERN.sub("", name)

        # Remove (Non-Demat) / (Demat) markers
        name = re.sub(r"\s*\((?:Non-)?Demat\)", "", name)

        # Remove trailing " -" or leading/trailing whitespace
        name = name.strip().rstrip("-").strip()

        return name

    def _parse_transaction_line(
        self, line: str, folio: str, isin: str, scheme_name: Optional[str]
    ) -> Optional[ParsedTransaction]:
        """Parse a transaction line like:
        27-Jan-2026 SIP Purchase-BSE - Instalment No - 18/348 Online 9,999.50 524.055 19.081 16,784.565
        """
        date_match = self.DATE_LINE_PATTERN.match(line)
        if not date_match:
            return None

        try:
            txn_date = datetime.strptime(date_match.group(1), "%d-%b-%Y").date()
        except ValueError:
            return None

        remainder = date_match.group(2)

        # Find all numeric tokens in the remainder
        numbers = list(self.NUMBER_TOKEN.finditer(remainder))
        if len(numbers) < 4:
            return None

        # Last 4 numbers are: amount, units, price, balance
        last_four = numbers[-4:]
        amount_str = last_four[0].group().replace(",", "")
        units_str = last_four[1].group().replace(",", "")
        price_str = last_four[2].group().replace(",", "")
        # balance not stored but used for verification if needed

        amount = float(amount_str)
        units = float(units_str)
        price = float(price_str)

        # Description is everything before the first of the last 4 numbers
        desc_end = last_four[0].start()
        description = remainder[:desc_end].strip()

        # Map transaction type from description
        txn_type = self._map_transaction_type(description)

        # Sign convention: outflows negative, inflows positive
        if txn_type in ("BUY", "SIP", "SWITCH_IN"):
            amount_inr = -amount
        elif txn_type in ("REDEMPTION", "DIVIDEND", "SWITCH_OUT"):
            amount_inr = amount
        else:
            amount_inr = -amount  # default outflow

        # Stable txn_id via SHA-256
        amount_paise = round(amount * 100)
        hash_input = f"{folio}|{isin}|{txn_date}|{amount_paise}|{units}|{txn_type}"
        txn_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        txn_id = f"cas_{txn_hash}"

        mfapi_scheme_code = None
        scheme_category = None
        asset_class = None
        lookup = lookup_by_isin(isin)
        if lookup:
            mfapi_scheme_code, scheme_category = lookup
            asset_class = classify_mf(scheme_category).value

        return ParsedTransaction(
            source="cas",
            asset_name=scheme_name or isin,
            asset_identifier=isin,
            isin=isin,
            asset_type="MF",
            txn_type=txn_type,
            date=txn_date,
            units=units,
            price_per_unit=price,
            amount_inr=amount_inr,
            txn_id=txn_id,
            notes=description,
            mfapi_scheme_code=mfapi_scheme_code,
            scheme_category=scheme_category,
            asset_class=asset_class,
        )

    def _parse_closing_balance(
        self, line: str, isin: Optional[str], scheme_name: Optional[str]
    ) -> Optional[ParsedFundSnapshot]:
        if not isin:
            print(f"Cannot parse closing balance without ISIN for line: {line}")
            return None
        m = self.CLOSING_BALANCE_PATTERN.search(line)
        if not m:
            print(f"Closing balance pattern not matched for line: {line}")
            return None
        try:
            closing_units = float(m.group(1).replace(",", ""))
            nav_date = datetime.strptime(m.group(2), "%d-%b-%Y").date()
            nav_price = float(m.group(3).replace(",", ""))
            total_cost = float(m.group(4).replace(",", ""))
            market_value = float(m.group(5).replace(",", ""))
        except (ValueError, IndexError) as e:
            print(f"Error parsing closing balance: {e}")
            return None
        return ParsedFundSnapshot(
            isin=isin,
            asset_name=scheme_name or isin,
            date=nav_date,
            closing_units=closing_units,
            nav_price_inr=nav_price,
            market_value_inr=market_value,
            total_cost_inr=total_cost,
        )

    def _map_transaction_type(self, description: str) -> str:
        desc_upper = description.upper()
        # SIP / Systematic must be checked before generic "PURCHASE"
        if "SIP" in desc_upper:
            return "SIP"
        if "SYSTEMATIC" in desc_upper:
            return "SIP"
        if "PURCHASE SYSTEMATIC" in desc_upper:
            return "SIP"
        if "REDEMPTION" in desc_upper:
            return "REDEMPTION"
        if "SWITCH IN" in desc_upper or "SWITCH-IN" in desc_upper:
            return "SWITCH_IN"
        if "SWITCH OUT" in desc_upper or "SWITCH-OUT" in desc_upper:
            return "SWITCH_OUT"
        if "DIVIDEND" in desc_upper:
            return "DIVIDEND"
        if "PURCHASE" in desc_upper:
            return "BUY"
        return "BUY"

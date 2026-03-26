import csv
import hashlib
import io
import logging
from datetime import datetime

from app.importers.base import ParsedTransaction, ImportResult

logger = logging.getLogger(__name__)


class FidelityRSUImporter:
    """Parses Fidelity RSU holding CSV exports (current holdings format).

    Filename format: {MARKET}_{TICKER}.csv  e.g. NASDAQ_AMZN.csv
    Relevant columns: Date acquired, Quantity, Cost basis, Cost basis/share
    All USD amounts; exchange_rates maps "YYYY-MM" → float (USD/INR).
    txn_id is a SHA-256 hash of ticker|date|quantity|cost_per_share — stable across re-imports.
    """

    def __init__(self, exchange_rates: dict[str, float] | None = None):
        self.exchange_rates = exchange_rates or {}

    _MONTH_ABBREVS_STATIC = {
        "jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec",
    }

    @classmethod
    def extract_required_month_years(cls, file_bytes: bytes) -> list[str]:
        """Return sorted unique YYYY-MM strings from 'Date acquired' column."""
        months: set[str] = set()
        text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            date_str = (row.get("Date acquired") or "").strip()
            if not date_str or date_str[:3].lower() not in cls._MONTH_ABBREVS_STATIC:
                continue
            try:
                d = datetime.strptime(date_str, "%b-%d-%Y")
                months.add(d.strftime("%Y-%m"))
            except ValueError:
                pass
        return sorted(months)

    @staticmethod
    def _parse_ticker_from_filename(filename: str) -> tuple[str, str]:
        """'NASDAQ_AMZN.csv' → ('NASDAQ', 'AMZN'). Returns ('', stem) on bad format."""
        stem = filename.rsplit(".", 1)[0]
        parts = stem.split("_", 1)
        if len(parts) == 2:
            return parts[0].upper(), parts[1].upper()
        return "", stem.upper()

    # Valid 3-letter month abbreviations as the start of a date string
    _MONTH_ABBREVS = {
        "jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec",
    }

    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
        result = ImportResult(source="fidelity_rsu")
        market, ticker = self._parse_ticker_from_filename(filename)
        if not ticker:
            result.errors.append(
                "Cannot determine ticker from filename. Expected: MARKET_TICKER.csv"
            )
            return result

        text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader):
            date_str = (row.get("Date acquired") or "").strip()
            # Skip blank rows and footer rows — only process rows that start with a 3-letter month abbreviation
            if not date_str or date_str[:3].lower() not in self._MONTH_ABBREVS:
                continue
            try:
                txn = self._parse_row(row, ticker, market)
                result.transactions.append(txn)
            except Exception as e:
                result.errors.append(f"Row {i + 2}: {e}")
        return result

    def _parse_row(self, row: dict, ticker: str, market: str) -> ParsedTransaction:
        date_str = row["Date acquired"].strip()
        vest_date = datetime.strptime(date_str, "%b-%d-%Y").date()
        quantity = float(row["Quantity"].replace(",", ""))
        cost_basis_total = float(row["Cost basis"].replace(",", "").lstrip("$"))
        cost_basis_per_share = float(row["Cost basis/share"].replace(",", "").lstrip("$"))

        month_year = vest_date.strftime("%Y-%m")
        forex_rate = self.exchange_rates.get(month_year)
        if forex_rate is None:
            raise ValueError(f"No exchange rate provided for {month_year}")

        amount_inr = -(cost_basis_total * forex_rate)  # VEST = outflow (negative)
        txn_id = self._make_txn_id(ticker, vest_date.isoformat(), quantity, cost_basis_per_share)

        return ParsedTransaction(
            source="fidelity_rsu",
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type="VEST",
            date=vest_date,
            units=quantity,
            price_per_unit=cost_basis_per_share,
            forex_rate=forex_rate,
            amount_inr=amount_inr,
            txn_id=txn_id,
            notes=f"RSU vest via Fidelity ({market})",
        )

    @staticmethod
    def _make_txn_id(ticker: str, date_iso: str, quantity: float, cost_per_share: float) -> str:
        """Stable txn_id: SHA-256 of pipe-delimited key fields."""
        q_int = round(quantity * 10000)   # avoid float formatting variance
        c_int = round(cost_per_share * 100)
        raw = f"fidelity_rsu|{ticker}|{date_iso}|{q_int}|{c_int}"
        return "fidelity_rsu_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

import hashlib
import io
import logging
import re
from datetime import datetime

import pdfplumber

from app.importers.base import ParsedTransaction, ImportResult, BaseImporter
from app.importers.registry import register_importer

logger = logging.getLogger(__name__)

# Regex for sale rows:
# "Mar-17-2025 Mar-17-2025 36.0000 $7,070.44 $7,070.24 -$0.20 USD RS"
# "Sep-15-2025 Sep-15-2025 36.0000 $8,346.14 $8,346.14 + $0.00 USD RS"
# gain/loss can be "-$X", "+$X", or "+ $X" with optional space
_SALE_ROW_RE = re.compile(
    r"(\w{3}-\d{2}-\d{4})\s+"     # date sold
    r"(\w{3}-\d{2}-\d{4})\s+"     # date acquired
    r"([\d,]+\.?\d*)\s+"           # quantity
    r"\$([\d,]+\.?\d*)\s+"         # cost basis
    r"\$([\d,]+\.?\d*)\s+"         # proceeds
    r"[+\-]?\s*\$[\d,]+\.?\d*\s+" # gain/loss (ignored)
    r"USD\s+(\w+)"                  # stock source
)

# Ticker line: "AMZN: AMAZON.COM INC" or "AMZN: Amazon.com, Inc."
_TICKER_RE = re.compile(r"^([A-Z]{1,6}):\s+.+")


@register_importer
class FidelityPDFImporter(BaseImporter):
    source = "fidelity_sale"
    asset_type = "STOCK_US"
    format = "pdf"
    """Parses Fidelity NetBenefits transaction summary PDFs.

    Extracts rows from the 'Stock sales' section.
    All USD amounts; exchange_rates maps "YYYY-MM" -> float (USD/INR).
    Sale transactions are tagged as 'Tax cover sale' in notes.
    txn_id is SHA-256 of ticker|date_sold|date_acquired|quantity — stable across re-imports.
    """

    def __init__(self, exchange_rates: dict[str, float] | None = None):
        self.exchange_rates = exchange_rates or {}

    @staticmethod
    def extract_required_month_years(file_bytes: bytes) -> list[str]:
        """Return sorted unique YYYY-MM strings from 'Date sold' column in Stock sales section."""
        months: set[str] = set()
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            in_sales = False
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    if "Stock sales" in line:
                        in_sales = True
                    if in_sales:
                        m = _SALE_ROW_RE.search(line)
                        if m:
                            try:
                                d = datetime.strptime(m.group(1), "%b-%d-%Y")
                                months.add(d.strftime("%Y-%m"))
                            except ValueError:
                                pass
        return sorted(months)

    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
        result = ImportResult(source="fidelity_sale")
        ticker: str | None = None
        in_sales = False

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    line = line.strip()
                    if "Stock sales" in line:
                        in_sales = True
                        continue
                    if in_sales and not ticker:
                        m = _TICKER_RE.match(line)
                        if m:
                            ticker = m.group(1)
                    if in_sales and ticker:
                        m = _SALE_ROW_RE.search(line)
                        if m:
                            try:
                                txn = self._parse_match(m, ticker)
                                result.transactions.append(txn)
                            except ValueError as e:
                                result.errors.append(f"Row parse error: {e}")

        if not ticker:
            result.errors.append("Could not find ticker in PDF (expected 'TICK: Company Name' line)")
        return result

    def _parse_match(self, m: re.Match, ticker: str) -> ParsedTransaction:
        date_sold_str, date_acq_str = m.group(1), m.group(2)
        quantity_str, _cost_str, proceeds_str = m.group(3), m.group(4), m.group(5)

        date_sold = datetime.strptime(date_sold_str, "%b-%d-%Y").date()
        date_acquired = datetime.strptime(date_acq_str, "%b-%d-%Y").date()
        quantity = float(quantity_str.replace(",", ""))
        proceeds_usd = float(proceeds_str.replace(",", ""))

        month_year = date_sold.strftime("%Y-%m")
        forex_rate = self.exchange_rates.get(month_year)
        if forex_rate is None:
            raise ValueError(f"No exchange rate provided for {month_year}")

        amount_inr = proceeds_usd * forex_rate  # SELL = inflow (positive)
        price_per_unit_usd = proceeds_usd / quantity if quantity else None
        txn_id = self._make_txn_id(ticker, date_sold.isoformat(), date_acquired.isoformat(), quantity)

        return ParsedTransaction(
            source="fidelity_sale",
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type="SELL",
            date=date_sold,
            units=quantity,
            price_per_unit=price_per_unit_usd,
            forex_rate=forex_rate,
            amount_inr=amount_inr,
            txn_id=txn_id,
            notes=f"Tax cover sale (acquired {date_acquired.isoformat()})",
        )

    @staticmethod
    def _make_txn_id(ticker: str, date_sold: str, date_acquired: str, quantity: float) -> str:
        q_int = round(quantity * 10000)
        raw = f"fidelity_sale|{ticker}|{date_sold}|{date_acquired}|{q_int}"
        return "fidelity_sale_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

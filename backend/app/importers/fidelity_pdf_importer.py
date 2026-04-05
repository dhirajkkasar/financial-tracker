import hashlib
import io
import logging
import re
import uuid
from datetime import datetime

import pdfplumber

from app.importers.base import ParsedTransaction, ImportResult, BaseImporter, ValidationResult
from app.importers.helpers import ExchangeRateValidationHelper
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
    All USD amounts; constructor accepts exchange_rates dict mapping "YYYY-MM" → float (USD/INR).
    Validates exchange_rates completeness via validate() method after parsing.
    Sale transactions generate both BUY and SELL ParsedTransaction entries.
    txn_id is SHA-256 of ticker|date_sold|date_acquired|quantity for SELL, 
    ticker|date_acquired|quantity for BUY — stable across re-imports.
    """

    def __init__(self, filename: str = "", user_inputs: str | None = None):
        """Initialize with filename and user_inputs (JSON string of exchange_rates).
        
        Args:
            filename: PDF filename (optional, for logging/tracking)
            user_inputs: JSON string mapping "YYYY-MM" strings to exchange rates (USD/INR).
                        Will be parsed to dict. Exchange_rates are validated via validate() method.
        """
        self.filename = filename
        self.exchange_rates = ExchangeRateValidationHelper.parse_exchange_rates_json(user_inputs)

    def validate(self, result: ImportResult) -> ValidationResult:
        """Post-parse validation: verify exchange_rates completeness.
        
        Args:
            result: ImportResult from parse()
        Returns:
            ValidationResult with errors if exchange_rates are missing for required months
        """
        return ExchangeRateValidationHelper.validate_exchange_rates(result, self.exchange_rates)

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
                                sale_date = datetime.strptime(m.group(1), "%b-%d-%Y")
                                buy_date = datetime.strptime(m.group(2), "%b-%d-%Y")
                                formatted_sale_month = sale_date.strftime("%Y-%m")
                                formatted_buy_month = buy_date.strftime("%Y-%m")
                                months.add(formatted_sale_month)
                                if formatted_buy_month != formatted_sale_month:
                                    months.add(formatted_buy_month)
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
                                buy_txn, sell_txn = self._parse_match(m, ticker)
                                result.transactions.append(buy_txn)
                                result.transactions.append(sell_txn)
                            except ValueError as e:
                                print(f"ERROR parsing row for ticker {ticker}: {e}")
                                result.errors.append(f"Row parse error: {e}")

        if not ticker:
            result.errors.append("Could not find ticker in PDF (expected 'TICK: Company Name' line)")
        return result

    def _parse_match(self, m: re.Match, ticker: str) -> tuple[ParsedTransaction, ParsedTransaction]:
        date_sold_str, date_acq_str = m.group(1), m.group(2)
        quantity_str, cost_str, proceeds_str = m.group(3), m.group(4), m.group(5)

        date_sold = datetime.strptime(date_sold_str, "%b-%d-%Y").date()
        date_acquired = datetime.strptime(date_acq_str, "%b-%d-%Y").date()
        quantity = float(quantity_str.replace(",", ""))
        proceeds_usd = float(proceeds_str.replace(",", ""))
        cost_usd = float(cost_str.replace(",", "")) if cost_str else 0.0

        # For backward compatibility: if exchange_rates were provided to constructor, use them
        # Otherwise, leave amount_inr as placeholder (will be calculated during commit with validated exchange_rates)
        date_sold_month_year = date_sold.strftime("%Y-%m")
        date_acquired_month_year = date_acquired.strftime("%Y-%m")
        date_sold_forex_rate = self.exchange_rates.get(date_sold_month_year)
        date_acquired_forex_rate = self.exchange_rates.get(date_acquired_month_year)
        
        print(f"DEBUG: Forex rates - Sold Month-Year: {date_sold_month_year} Rate: {date_sold_forex_rate}, Acquired Month-Year: {date_acquired_month_year} Rate: {date_acquired_forex_rate}")
        if date_sold_forex_rate is None and self.exchange_rates:
            # Exchange_rates provided but missing this month
            raise ValueError(f"No exchange rate provided for {date_sold_month_year}")
        
        if date_acquired_forex_rate is None and self.exchange_rates:
            # Exchange_rates provided but missing this month
            raise ValueError(f"No exchange rate provided for {date_acquired_month_year}")

        sale_amount_inr = proceeds_usd * date_sold_forex_rate if date_sold_forex_rate else 0.0
        acquire_amount_inr = cost_usd * date_acquired_forex_rate if date_acquired_forex_rate else 0.0
        
        sale_price_per_unit_usd = round(proceeds_usd / quantity, 4) if quantity else 0.0
        acquire_price_per_unit_usd = round(cost_usd / quantity, 4) if quantity else 0.0
        sale_txn_id = self._make_txn_id(ticker, date_sold.isoformat(), date_acquired.isoformat(), quantity, False)
        acquire_txn_id = self._make_txn_id(ticker, date_acquired.isoformat(), date_acquired.isoformat(), quantity, True)
        lot_id = uuid.uuid4()

        buy_txn = ParsedTransaction(
            source="fidelity_sale",
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type="BUY",
            date=date_acquired,
            units=quantity,
            price_per_unit=acquire_price_per_unit_usd,
            forex_rate=date_acquired_forex_rate,
            # amount_inr is negative for BUY (cash outflow)
            amount_inr=-acquire_amount_inr,
            txn_id=acquire_txn_id,
            lot_id=str(lot_id),
            notes=f"Tax cover buy (sold {date_sold.isoformat()})",
        )

        sell_txn = ParsedTransaction(
            source="fidelity_sale",
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type="SELL",
            date=date_sold,
            units=quantity,
            price_per_unit=sale_price_per_unit_usd,
            forex_rate=date_sold_forex_rate,
            # amount_inr is positive for SELL (cash inflow)
            amount_inr=sale_amount_inr,
            txn_id=sale_txn_id,
            lot_id=str(lot_id),
            notes=f"Tax cover sale (acquired {date_acquired.isoformat()})",
        )

        return buy_txn, sell_txn

    @staticmethod
    def _make_txn_id(ticker: str, date_sold: str, date_acquired: str, quantity: float, buy_txn: bool) -> str:
        q_int = round(quantity * 10000)
        if buy_txn:
            raw = f"fidelity_buy|{ticker}|{date_acquired}|{q_int}"
            return "fidelity_buy_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        raw = f"fidelity_sale|{ticker}|{date_sold}|{date_acquired}|{q_int}"
        return "fidelity_sale_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


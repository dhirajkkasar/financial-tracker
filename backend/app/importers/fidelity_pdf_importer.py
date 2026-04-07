import hashlib
import io
import logging
import re
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
    Sale transactions generate SELL-only ParsedTransaction entries with acquisition metadata.
    FidelityPreCommitProcessor resolves specific lot_ids before DB writes.
    txn_id: SHA-256 of ticker|date_sold|date_acquired|quantity — stable across re-imports.
    """

    def __init__(self, filename: str = "", user_inputs: str | None = None):
        """Initialize with filename and user_inputs (JSON string of exchange_rates).

        Args:
            filename: PDF filename (optional, for logging/tracking)
            user_inputs: JSON string mapping "YYYY-MM" strings to exchange rates (USD/INR).
                        Parsed to dict. Validated via validate() method.
        """
        self.filename = filename
        self._user_inputs = user_inputs
        self.exchange_rates = ExchangeRateValidationHelper.parse_exchange_rates_json(user_inputs)

    def validate(self, result: ImportResult, user_inputs: str | None = None) -> ValidationResult:
        """Post-parse validation: verify exchange_rates completeness.

        Args:
            result: ImportResult from parse()
            user_inputs: Optional JSON string of exchange_rates; if provided, overrides constructor value.
        Returns:
            ValidationResult with errors if exchange_rates are missing for required months
        """
        if result.errors:
            return ValidationResult(is_valid=False, errors=result.errors, required_inputs={})

        if not result.transactions:
            return ValidationResult(is_valid=True, errors=[], required_inputs={})

        if user_inputs is not None:
            exchange_rates = ExchangeRateValidationHelper.parse_exchange_rates_json(user_inputs)
            if exchange_rates is None:
                return ValidationResult(
                    is_valid=False,
                    errors=['exchange_rates must be valid JSON, e.g. {"2025-03": 86.5}'],
                    required_inputs={},
                )
        else:
            exchange_rates = self.exchange_rates

        if exchange_rates is None:
            return ValidationResult(
                is_valid=False,
                errors=["exchange_rates is required. Provide a JSON string like {\"2025-03\": 86.5}"],
                required_inputs={},
            )

        return ExchangeRateValidationHelper.validate_exchange_rates(result, exchange_rates)

    @staticmethod
    def extract_required_month_years(file_bytes: bytes) -> list[str]:
        """Return sorted unique YYYY-MM strings from 'Date sold' and 'Date acquired' columns."""
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
                                months.add(sale_date.strftime("%Y-%m"))
                                months.add(buy_date.strftime("%Y-%m"))
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
                                sell_txn = self._parse_match(m, ticker)
                                result.transactions.append(sell_txn)
                            except ValueError as e:
                                print(f"ERROR parsing row for ticker {ticker}: {e}")
                                result.errors.append(f"Row parse error: {e}")

        if not ticker:
            result.errors.append("Could not find ticker in PDF (expected 'TICK: Company Name' line)")
        return result

    def _parse_match(self, m: re.Match, ticker: str) -> ParsedTransaction:
        date_sold_str, date_acq_str = m.group(1), m.group(2)
        quantity_str, cost_str, proceeds_str = m.group(3), m.group(4), m.group(5)

        date_sold = datetime.strptime(date_sold_str, "%b-%d-%Y").date()
        date_acquired = datetime.strptime(date_acq_str, "%b-%d-%Y").date()
        quantity = float(quantity_str.replace(",", ""))
        proceeds_usd = float(proceeds_str.replace(",", ""))
        cost_usd = float(cost_str.replace(",", "")) if cost_str else 0.0

        date_sold_month_year = date_sold.strftime("%Y-%m")
        date_acquired_month_year = date_acquired.strftime("%Y-%m")
        date_sold_forex_rate = self.exchange_rates.get(date_sold_month_year) if self.exchange_rates else None
        date_acquired_forex_rate = self.exchange_rates.get(date_acquired_month_year) if self.exchange_rates else None

        if date_sold_forex_rate is None and self.exchange_rates:
            raise ValueError(f"No exchange rate provided for {date_sold_month_year}")
        if date_acquired_forex_rate is None and self.exchange_rates:
            raise ValueError(f"No exchange rate provided for {date_acquired_month_year}")

        sale_amount_inr = proceeds_usd * date_sold_forex_rate if date_sold_forex_rate else 0.0
        acquire_amount_inr = cost_usd * date_acquired_forex_rate if date_acquired_forex_rate else 0.0

        sale_price_per_unit_usd = round(proceeds_usd / quantity, 4) if quantity else 0.0
        sell_txn_id = self._make_txn_id(ticker, date_sold.isoformat(), date_acquired.isoformat(), quantity)

        return ParsedTransaction(
            source="fidelity_sale",
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type="SELL",
            date=date_sold,
            units=quantity,
            price_per_unit=sale_price_per_unit_usd,
            forex_rate=date_sold_forex_rate,
            amount_inr=sale_amount_inr,
            txn_id=sell_txn_id,
            lot_id=None,                                   # FidelityPreCommitProcessor assigns this
            acquisition_date=date_acquired,
            acquisition_cost=acquire_amount_inr,
            acquisition_forex_rate=date_acquired_forex_rate,
            notes=f"Acquired {date_acquired.isoformat()}",
        )

    @staticmethod
    def _make_txn_id(ticker: str, date_sold: str, date_acquired: str, quantity: float) -> str:
        q_int = round(quantity * 10000)
        raw = f"fidelity_sale|{ticker}|{date_sold}|{date_acquired}|{q_int}"
        return "fidelity_sale_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

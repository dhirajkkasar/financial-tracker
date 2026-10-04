"""IBKR Activity Flex Query — Trades CSV importer.

Expected Flex Query: Activity Flex Query, Format=CSV, Trades section with at
least Symbol, TradeID, DateTime, TransactionType, Quantity, TradePrice,
Proceeds, Taxes, CurrencyPrimary, AssetClass, ISIN. Optional: IBCommission,
IBCommissionCurrency, Buy/Sell.

Design (locked with user Oct 2026):
- STK COMMON + ETF -> STOCK_US (identifier=ticker for YFinance price path).
- Buy/Sell column primary, Quantity sign fallback. Units stored as abs().
- txn_id = native ibkr_<TradeID>, stable across re-imports.
- Monthly USD/INR JSON (--exchange-rates), same validator as Fidelity.
- BUY amount_inr = -(|Proceeds| + |Commission| + |Taxes|) * rate (outflow).
- SELL amount_inr = (|Proceeds| - |Commission| - |Taxes|) * rate (inflow).
- Non-USD rows rejected (v1); non-ExchTrade / non-STK rows skipped w/ warning.
"""

import csv
import hashlib
import io
import logging
from datetime import datetime

from app.importers.base import ParsedTransaction, ImportResult, BaseImporter, ValidationResult
from app.importers.helpers import ExchangeRateValidationHelper
from app.importers.registry import register_importer

logger = logging.getLogger(__name__)


@register_importer
class IBKRTradesImporter(BaseImporter):
    source = "ibkr"
    asset_type = "STOCK_US"
    format = "csv"

    def __init__(self, filename: str = "", user_inputs: str | None = None):
        self.filename = filename
        self._user_inputs = user_inputs
        self.exchange_rates = ExchangeRateValidationHelper.parse_exchange_rates_json(user_inputs)

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------
    def validate(self, result: ImportResult) -> ValidationResult:
        if result.errors:
            return ValidationResult(is_valid=False, errors=result.errors, required_inputs={})
        if not result.transactions:
            return ValidationResult(is_valid=True, errors=[], required_inputs={})
        if self.exchange_rates is None:
            if self._user_inputs is not None:
                return ValidationResult(
                    is_valid=False,
                    errors=['exchange_rates must be valid JSON, e.g. {"2026-05": 86.0}'],
                    required_inputs={},
                )
            required_months = sorted({t.date.strftime("%Y-%m") for t in result.transactions})
            months_hint = ", ".join(required_months) if required_months else "none"
            return ValidationResult(
                is_valid=False,
                errors=[f"exchange_rates is required for months: {months_hint}. "
                        'Provide a JSON string like {"2026-05": 86.0}'],
                required_inputs={"required_months": required_months, "provided_months": []},
            )
        return ExchangeRateValidationHelper.validate_exchange_rates(result, self.exchange_rates)

    # ------------------------------------------------------------------
    # months helper (CLI prompts before API call)
    # ------------------------------------------------------------------
    @staticmethod
    def extract_required_month_years(file_bytes: bytes) -> list[str]:
        months: set[str] = set()
        text = file_bytes.decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(text)):
            try:
                d = IBKRTradesImporter._parse_ibkr_date((row.get("DateTime") or "").strip())
                months.add(d.strftime("%Y-%m"))
            except ValueError:
                continue
        return sorted(months)

    # ------------------------------------------------------------------
    # parse
    # ------------------------------------------------------------------
    def parse(self, file_bytes: bytes) -> ImportResult:
        result = ImportResult(source="ibkr")
        text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader):
            try:
                txn = self._parse_row(row)
                if txn is None:  # skipped non-trade row
                    result.warnings.append(f"Row {i + 2}: skipped non-trade {row.get('TransactionType')}")
                    continue
                result.transactions.append(txn)
            except Exception as e:
                result.errors.append(f"Row {i + 2}: {e}")
        result.transactions.sort(key=lambda t: (t.date, t.txn_id))
        return result

    # ------------------------------------------------------------------
    # row
    # ------------------------------------------------------------------
    def _parse_row(self, row: dict) -> ParsedTransaction | None:
        txn_kind = (row.get("TransactionType") or "").strip()
        asset_class = (row.get("AssetClass") or "").strip().upper()
        if txn_kind != "ExchTrade" or asset_class != "STK":
            return None

        currency = (row.get("CurrencyPrimary") or "").strip().upper()
        if currency != "USD":
            raise ValueError(f"unsupported currency '{row.get('CurrencyPrimary')}' (v1 supports USD only)")

        symbol = (row.get("Symbol") or "").strip().upper()
        if not symbol:
            raise ValueError("missing Symbol")
        isin = (row.get("ISIN") or "").strip()
        trade_id = (row.get("TradeID") or "").strip()

        txn_date = self._parse_ibkr_date((row.get("DateTime") or "").strip())
        quantity = self._parse_number(row.get("Quantity"), "Quantity")
        trade_price = self._parse_number(row.get("TradePrice"), "TradePrice")
        proceeds = self._parse_number(row.get("Proceeds", "0") or "0", "Proceeds")
        taxes = self._parse_number(row.get("Taxes", "0") or "0", "Taxes")
        commission = self._parse_number(row.get("IBCommission", "0") or "0", "IBCommission")

        buy_sell = (row.get("Buy/Sell") or "").strip().upper()
        if buy_sell == "BUY":
            txn_type = "BUY"
        elif buy_sell == "SELL":
            txn_type = "SELL"
        elif quantity > 0:
            txn_type = "BUY"
        elif quantity < 0:
            txn_type = "SELL"
        else:
            raise ValueError("zero Quantity with no Buy/Sell marker")

        units = abs(quantity)
        gross_usd = abs(proceeds)
        fees_usd = abs(commission) + abs(taxes)

        month = txn_date.strftime("%Y-%m")
        forex_rate = self.exchange_rates.get(month) if self.exchange_rates else None
        if forex_rate is None and self.exchange_rates:
            raise ValueError(f"No exchange rate provided for {month}")
        amount_inr = 0.0
        if forex_rate:
            if txn_type == "BUY":
                amount_inr = -((gross_usd + fees_usd) * forex_rate)
            else:
                amount_inr = max((gross_usd - fees_usd), 0.0) * forex_rate

        if trade_id:
            txn_id = f"ibkr_{trade_id}"
        else:
            raw = f"ibkr|{symbol}|{txn_date.isoformat()}|{round(units * 10000)}|{round(trade_price * 100)}|{txn_type}"
            txn_id = "ibkr_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        notes = f"IBKR {txn_kind} {isin}".strip()
        return ParsedTransaction(
            source="ibkr",
            asset_name=symbol,
            asset_identifier=symbol,
            asset_type="STOCK_US",
            txn_type=txn_type,
            date=txn_date,
            units=units,
            price_per_unit=abs(trade_price),
            forex_rate=forex_rate,
            amount_inr=amount_inr,
            txn_id=txn_id,
            isin=isin or None,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_ibkr_date(s: str):
        """IBKR Flex DateTime: '20260522;115526' -> date. Also accepts YYYY-MM-DD."""
        s = (s or "").strip()
        head = s.split(";")[0].strip()
        for fmt in ("%Y%m%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(head, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"unparseable DateTime '{s}'")

    @staticmethod
    def _parse_number(v, field: str) -> float:
        s = str(v if v is not None else "").strip().replace(",", "").replace("$", "")
        if not s:
            return 0.0 if field in ("Proceeds", "Taxes", "IBCommission") else (_ for _ in ()).throw(ValueError(f"missing {field}"))
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"invalid {field} '{v}'")

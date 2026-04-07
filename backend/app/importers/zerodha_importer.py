import csv
import io
import logging
from datetime import datetime

from app.importers.base import ParsedTransaction, ImportResult, BaseImporter
from app.importers.registry import register_importer

logger = logging.getLogger(__name__)


@register_importer
class ZerodhaImporter(BaseImporter):
    source = "zerodha"
    asset_type = "STOCK_IN"
    format = "csv"
    """Parses Zerodha tradebook CSV files."""

    def __init__(self, **_kwargs):
        pass

    # Gold ETFs traded on NSE — classified as GOLD (price via NSE ticker, shown in Gold tab)
    _GOLD_ETF_SYMBOLS: frozenset[str] = frozenset({
        "GOLDBEES", "GOLDSHARE", "IPGETF", "PGULD", "GOLDCASE",
        "BSLGOLDETF", "LICMFGOLD", "KOTAKGOLD", "HDFCGOLD",
        "AXISGOLD", "NIPPONIGOLD", "SBIGOLD", "GOLD1D",
    })

    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
        result = ImportResult(source="zerodha")
        try:
            text = file_bytes.decode("utf-8-sig")  # handle BOM
            reader = csv.DictReader(io.StringIO(text))
            for i, row in enumerate(reader):
                try:
                    txn = self._parse_row(row)
                    result.transactions.append(txn)
                except Exception as e:
                    result.errors.append(f"Row {i+2}: {e}")
        except Exception as e:
            result.errors.append(f"Failed to read CSV: {e}")
        return result

    def _classify_asset_type(self, symbol: str, isin: str) -> str:
        """Infer asset_type from symbol/ISIN for Zerodha equity trades."""
        sym = symbol.strip().upper()
        # Sovereign Gold Bonds: NSE symbols start with 'SGB'
        if sym.startswith("SGB"):
            return "GOLD"
        # Gold ETFs: exact match against known tickers
        if sym in self._GOLD_ETF_SYMBOLS:
            return "GOLD"
        return "STOCK_IN"

    def _parse_row(self, row: dict) -> ParsedTransaction:
        symbol = row["symbol"].strip()
        isin = row["isin"].strip()
        trade_date = datetime.strptime(row["trade_date"].strip(), "%Y-%m-%d").date()
        trade_type = row["trade_type"].strip().upper()  # "buy" -> "BUY"
        quantity = float(row["quantity"])
        price = float(row["price"])
        trade_id = row["trade_id"].strip()
        exchange = row.get("exchange", "").strip()

        amount = quantity * price
        if trade_type == "BUY":
            amount_inr = -amount  # outflow
        else:
            amount_inr = amount   # inflow (SELL)

        txn_type = "BUY" if trade_type == "BUY" else "SELL"
        asset_type = self._classify_asset_type(symbol, isin)

        return ParsedTransaction(
            source="zerodha",
            asset_name=symbol,
            asset_identifier=isin,
            isin=isin,
            asset_type=asset_type,
            txn_type=txn_type,
            date=trade_date,
            units=quantity,
            price_per_unit=price,
            amount_inr=amount_inr,
            txn_id=f"zerodha_{trade_id}",
            exchange=exchange,
        )

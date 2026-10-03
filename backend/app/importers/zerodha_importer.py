import csv
import hashlib
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
            text = self._decode_bytes(file_bytes)
            reader = csv.DictReader(io.StringIO(text))
            # Normalise headers case-insensitively (lower+strip) so
            # "Symbol", " SYMBOL ", "symbol" all resolve.
            if reader.fieldnames:
                norm_names = { (n or "").strip().lower(): n for n in reader.fieldnames }
                reader.fieldnames = [(n or "").strip().lower() for n in reader.fieldnames]
            else:
                norm_names = {}
            for i, row in enumerate(reader):
                # row keys are already lower-cased; normalise values lazily in _parse_row
                try:
                    txn = self._parse_row(row)
                    result.transactions.append(txn)
                except Exception as e:
                    result.errors.append(f"Row {i+2}: {e}")
            # Sort parsed transactions by date before returning (stable chronological order)
            result.transactions.sort(key=lambda t: (t.date, t.txn_id))
        except Exception as e:
            result.errors.append(f"Failed to read CSV: {e}")
        return result

    @staticmethod
    def _decode_bytes(file_bytes: bytes) -> str:
        """Try utf-8-sig first (handles BOM), fall back with errors='replace'."""
        try:
            return file_bytes.decode("utf-8-sig")
        except (UnicodeDecodeError, ValueError):
            return file_bytes.decode("utf-8-sig", errors="replace")

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
        symbol = (row.get("symbol") or "").strip()
        isin = (row.get("isin") or "").strip()
        if not symbol:
            raise ValueError("missing symbol")
        if not isin:
            raise ValueError("missing isin")
        trade_date = self._parse_trade_date((row.get("trade_date") or "").strip())
        raw_trade_type = (row.get("trade_type") or "").strip().upper()
        quantity = self._parse_number(row.get("quantity", ""), "quantity")
        price = self._parse_number(row.get("price", ""), "price")
        trade_id = (row.get("trade_id") or "").strip()
        exchange = (row.get("exchange") or "").strip()

        amount = quantity * price
        if raw_trade_type == "BUY":
            txn_type = "BUY"
            amount_inr = -amount  # outflow
        elif raw_trade_type in ("SELL", "SALE", "REDEMPTION"):
            txn_type = "SELL"
            amount_inr = amount   # inflow (SELL)
        else:
            raise ValueError(f"unknown trade_type '{row.get('trade_type')}' (expected BUY/SELL)")
        asset_type = self._classify_asset_type(symbol, isin)

        if trade_id:
            txn_id = f"zerodha_{trade_id}"
        else:
            # Fallback to content hash when trade_id is empty
            extras = f"{symbol}|{isin}|{trade_date.isoformat()}|{quantity}|{price}|{txn_type}|{exchange}"
            txn_id = f"zerodha_{hashlib.sha256(extras.encode()).hexdigest()[:12]}"

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
            txn_id=txn_id,
            exchange=exchange,
        )

    @staticmethod
    def _parse_trade_date(s: str):
        """Accept %Y-%m-%d and ISO order_execution_time (%Y-%m-%dT%H:%M:%S)."""
        s = (s or "").strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        # ISO fallback: fromisoformat handles "YYYY-MM-DDTHH:MM:SS" and variants
        try:
            return datetime.fromisoformat(s).date()
        except (ValueError, TypeError):
            raise ValueError(f"unparseable trade_date '{s}'")

    @staticmethod
    def _parse_number(v, field: str) -> float:
        """Strip commas/$/whitespace before float conversion."""
        s = str(v if v is not None else "").strip().replace(",", "").replace("$", "").replace("₹", "").strip()
        if not s:
            raise ValueError(f"missing {field}")
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"invalid {field} '{v}'")

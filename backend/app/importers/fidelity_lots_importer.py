"""Fidelity lots importers — open lots (holdings snapshot) + closed lots (sale history).

These two Fidelity NetBenefits "View lots" CSV exports are the source of truth
for US-stock VEST/BUY/SELL transactions. They replace the retired PDF sale
importer and its DB-scanning pre-commit lot resolver:

- Open lots: one row per UNSOLD remainder lot
  (Date acquired / Quantity / Cost basis / Cost basis-share / Grant date / Share source).
  Each row emits one VEST (RS) or BUY (otherwise) for the remaining units.
- Closed lots: one row per SOLD lot
  (Date acquired / Quantity / Date sold / Proceeds / Cost basis / Gain-loss / Term).
  Each row emits an acquisition leg (VEST/BUY, dated at acquisition) plus the
  SELL (dated at sale), sharing one deterministic lot_id.

Lot identity is derived purely at parse time — no DB lookup, no import-order
dependency, no synthetic-lot guessing:

- lot_id = UUID5(f'fidelity-lot|{ticker}|{acq_iso}|{cbs_cents}'), so the open
  remainder, the closed sold portions, and the SELLs of one economic lot all
  share a lot_id across both files and across re-imports.
- txn_ids are SHA-256 hashes of the row's natural key (ticker, dates,
  quantity, unit cost) — re-importing the same file yields only duplicates.

Idempotency notes:
- Closed rows are immutable history (a sold lot never changes) → pure dedup.
- Open rows are a snapshot: a remainder shrinks as shares sell. The open VEST
  txn_id therefore INCLUDES quantity, and commit prunes stale
  `fidelity_open_*` rows for the ticker (see ImportOrchestrator). Re-importing
  an unchanged file inserts nothing and prunes nothing.

user_inputs JSON: {"ticker": "AMZN", "exchange_rates": {"YYYY-MM": rate},
                   "sources": {"YYYY-MM-DD": "RS"}} — `sources` is closed-only
and optional; lots default to RS (→ VEST) with a warning when defaulted.
All amounts in the files are USD; exchange_rates convert to INR.
"""
import csv
import hashlib
import io
import json as _json
import logging
import re
import uuid
from datetime import datetime, date

from app.importers.base import ParsedTransaction, ImportResult, BaseImporter, ValidationResult
from app.importers.helpers.exchange_rate_validation_helper import ExchangeRateValidationHelper
from app.importers.registry import register_importer

logger = logging.getLogger(__name__)

_LOT_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

# Fidelity share-source codes: RS = RSU/PSU/RSA (employer grant → VEST).
# Everything else (SP = ESPP purchase, NQ/ISO = option exercise, SA, DO)
# is an acquisition by purchase/exercise → BUY.
_RS_SOURCES = {"RS"}

_OPEN_TXN_PREFIX = "fidelity_open_"
_CLOSED_TXN_PREFIX = "fidelity_closed_"
_SOLD_TXN_PREFIX = "fidelity_sold_"

# Public aliases for the commit-time snapshot-prune in ImportOrchestrator.
OPEN_TXN_PREFIX = _OPEN_TXN_PREFIX
CLOSED_TXN_PREFIX = _CLOSED_TXN_PREFIX
SOLD_TXN_PREFIX = _SOLD_TXN_PREFIX

_MONTH_ABBREVS = frozenset({
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
})

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text or "")


def _norm_header(name: str) -> str:
    """Lowercase alphanumeric header key ('Date sold or transferred' → 'datesoldortransferred')."""
    return re.sub(r"[^a-z0-9]", "", _strip_tags(name).lower())


def _parse_fidelity_date(raw: str) -> date:
    """Parse 'Sep-15-2026' and 'SEP/15/2026' (either separator, any case)."""
    s = (raw or "").strip()
    parts = re.split(r"[-/]", s)
    if len(parts) != 3 or parts[0][:3].lower() not in _MONTH_ABBREVS:
        raise ValueError(f"Unparseable Fidelity date: {raw!r}")
    canon = f"{parts[0][:3].title()}-{parts[1].zfill(2)}-{parts[2]}"
    return datetime.strptime(canon, "%b-%d-%Y").date()


def _parse_usd(raw: str) -> float:
    return float((raw or "").replace("$", "").replace(",", "").strip() or 0.0)


def _read_rows(file_bytes: bytes) -> list[dict]:
    """Decode a Fidelity lots CSV (BOM-tolerant), strip HTML from headers,
    drop blank/footer rows, return rows keyed by normalized headers."""
    # Strip tags from the raw text first: the closed-lots header embeds a
    # <span style="..."> whose commas would otherwise shatter CSV columns.
    text = _strip_tags(file_bytes.decode("utf-8-sig"))
    lines = [ln for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("The values") and ln.strip() != ","]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    norm_names = [_norm_header(h or "") for h in (reader.fieldnames or [])]
    rows: list[dict] = []
    for raw_row in reader:
        row = {norm: (raw_row[orig] or "") for norm, orig in zip(norm_names, reader.fieldnames or [])}
        if not (row.get("dateacquired") or "").strip():
            continue
        rows.append(row)
    return rows


def _lot_id(ticker: str, acq_iso: str, cbs_cents: int) -> str:
    return str(uuid.uuid5(_LOT_NAMESPACE, f"fidelity-lot|{ticker}|{acq_iso}|{cbs_cents}"))


def _txn_id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _parse_user_inputs(user_inputs: str | None) -> tuple[str, dict, dict]:
    """Return (ticker, exchange_rates, sources). Missing/invalid → (\"\", None, {})."""
    if not user_inputs:
        return "", None, {}
    try:
        parsed = _json.loads(user_inputs)
    except Exception:
        logger.warning("Failed to parse user_inputs JSON: %s", user_inputs)
        return "", None, {}
    if not isinstance(parsed, dict):
        return "", None, {}
    ticker = str(parsed.get("ticker") or "").upper().strip()
    rates = parsed.get("exchange_rates")
    sources = parsed.get("sources") or {}
    if not isinstance(rates, dict):
        rates = None
    if not isinstance(sources, dict):
        sources = {}
    norm_sources = {str(k): str(v).upper() for k, v in sources.items()}
    return ticker, rates, norm_sources


def _acq_type(source: str) -> str:
    return "VEST" if (source or "").upper() in _RS_SOURCES else "BUY"


class _FidelityLotsBase(BaseImporter):
    """Shared ticker/rates/sources handling for the two lots importers."""

    def __init__(self, filename: str = "", user_inputs: str | None = None):
        self.filename = filename
        self.ticker, self.exchange_rates, self.sources = _parse_user_inputs(user_inputs)

    def _base_validate(self, result: ImportResult) -> ValidationResult | None:
        """Ticker + rates validation. Returns None when valid, else the failure."""
        if result.errors:
            return ValidationResult(is_valid=False, errors=result.errors, required_inputs={})
        if not result.transactions:
            return ValidationResult(is_valid=True, errors=[], required_inputs={})
        if not self.ticker:
            return ValidationResult(
                is_valid=False,
                errors=['user_inputs must include "ticker", e.g. {"ticker": "AMZN", "exchange_rates": {...}}'],
                required_inputs={},
            )
        if self.exchange_rates is None:
            required_months = sorted({t.date.strftime("%Y-%m") for t in result.transactions})
            return ValidationResult(
                is_valid=False,
                errors=['user_inputs must include "exchange_rates", e.g. {"ticker": "AMZN", '
                        '"exchange_rates": {"2025-03": 86.5}}'],
                required_inputs={"required_months": required_months, "provided_months": []},
            )
        return None

    def _rate(self, month: str) -> float | None:
        return self.exchange_rates.get(month) if self.exchange_rates else None


@register_importer
class FidelityOpenLotsImporter(_FidelityLotsBase):
    source = "fidelity_open"
    asset_type = "STOCK_US"
    format = "csv"
    """Parses the Fidelity 'open lots' holdings snapshot (USD export).

    One row → one VEST (RS source) or BUY acquisition for the remaining units.
    txn_id includes quantity: a shrunken remainder in a later snapshot yields a
    new row while commit prunes the stale one (see ImportOrchestrator).
    """

    @staticmethod
    def extract_required_month_years(file_bytes: bytes) -> list[str]:
        months: set[str] = set()
        for row in _read_rows(file_bytes):
            try:
                months.add(_parse_fidelity_date(row["dateacquired"]).strftime("%Y-%m"))
            except ValueError:
                pass
        return sorted(months)

    def validate(self, result: ImportResult, user_inputs: str | None = None) -> ValidationResult:
        if user_inputs is not None:
            self.ticker, self.exchange_rates, self.sources = _parse_user_inputs(user_inputs)
        failed = self._base_validate(result)
        if failed is not None:
            return failed
        return ExchangeRateValidationHelper.validate_exchange_rates(result, self.exchange_rates)

    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
        result = ImportResult(source=self.source)
        for i, row in enumerate(_read_rows(file_bytes)):
            try:
                result.transactions.append(self._parse_row(row))
            except Exception as e:
                result.errors.append(f"Row {i + 2}: {e}")
        return result

    def _parse_row(self, row: dict) -> ParsedTransaction:
        ticker = self.ticker or "UNKNOWN"
        acq = _parse_fidelity_date(row["dateacquired"])
        qty = _parse_usd(row.get("quantity", ""))
        cost_total = _parse_usd(row.get("costbasis", ""))
        cost_share = _parse_usd(row.get("costbasisshare", ""))
        if qty <= 0:
            raise ValueError(f"Non-positive quantity: {row.get('quantity')!r}")
        if cost_share <= 0 and qty:
            cost_share = cost_total / qty
        source = (row.get("sharesource") or "RS").strip().upper() or "RS"
        month = acq.strftime("%Y-%m")
        fx = self._rate(month)
        if fx is None and self.exchange_rates:
            raise ValueError(f"No exchange rate provided for {month}")
        amount_inr = -(cost_total * fx) if fx else 0.0
        acq_type = _acq_type(source)
        cbs_cents = round(cost_share * 100)
        qty_int = round(qty * 10000)
        return ParsedTransaction(
            source=self.source,
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type=acq_type,
            date=acq,
            units=qty,
            price_per_unit=round(cost_share, 4),
            forex_rate=fx,
            amount_inr=amount_inr,
            txn_id=_txn_id(_OPEN_TXN_PREFIX, "fidelity_open", ticker, acq.isoformat(),
                           str(cbs_cents), str(qty_int)),
            lot_id=_lot_id(ticker, acq.isoformat(), cbs_cents),
            notes=f"Fidelity open lot — {source} vested {acq.isoformat()}",
        )


@register_importer
class FidelityClosedLotsImporter(_FidelityLotsBase):
    source = "fidelity_closed"
    asset_type = "STOCK_US"
    format = "csv"
    """Parses the Fidelity 'closed lots' sale history (USD export).

    One row → an acquisition leg (VEST/BUY at the acquisition date and cost
    basis) plus the SELL (at the sale date and proceeds), sharing one lot_id
    with each other and with the matching open-lot remainder. Same-day rows are
    sell-to-cover pairs (gain ≈ 0). Closed rows carry no source column, so the
    acquisition type comes from user_inputs `sources` ({acq_iso: code}),
    defaulting to RS (→ VEST) with a warning.
    """

    @staticmethod
    def extract_required_month_years(file_bytes: bytes) -> list[str]:
        months: set[str] = set()
        for row in _read_rows(file_bytes):
            for key in ("dateacquired", "datesoldortransferred"):
                try:
                    months.add(_parse_fidelity_date(row[key]).strftime("%Y-%m"))
                except (ValueError, KeyError):
                    pass
        return sorted(months)

    def validate(self, result: ImportResult, user_inputs: str | None = None) -> ValidationResult:
        if user_inputs is not None:
            self.ticker, self.exchange_rates, self.sources = _parse_user_inputs(user_inputs)
        failed = self._base_validate(result)
        if failed is not None:
            return failed
        return ExchangeRateValidationHelper.validate_exchange_rates(result, self.exchange_rates)

    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
        result = ImportResult(source=self.source)
        defaulted: set[str] = set()
        for i, row in enumerate(_read_rows(file_bytes)):
            try:
                vest_leg, sell = self._parse_row(row)
                result.transactions.extend([vest_leg, sell])
                if vest_leg.notes.endswith("[source defaulted to RS]"):
                    defaulted.add(vest_leg.date.isoformat())
            except Exception as e:
                result.errors.append(f"Row {i + 2}: {e}")
        for acq_iso in sorted(defaulted):
            result.warnings.append(
                f"Lot acquired {acq_iso}: no source in user_inputs — defaulted to RS (VEST). "
                "Pass \"sources\" to override."
            )
        return result

    def _parse_row(self, row: dict) -> tuple[ParsedTransaction, ParsedTransaction]:
        ticker = self.ticker or "UNKNOWN"
        acq = _parse_fidelity_date(row["dateacquired"])
        sold = _parse_fidelity_date(row["datesoldortransferred"])
        qty = _parse_usd(row.get("quantity", ""))
        proceeds = _parse_usd(row.get("proceeds", ""))
        cost_total = _parse_usd(row.get("costbasis", ""))
        if qty <= 0:
            raise ValueError(f"Non-positive quantity: {row.get('quantity')!r}")
        cost_share = cost_total / qty
        source = self.sources.get(acq.isoformat(), "RS")
        defaulted = acq.isoformat() not in self.sources
        acq_month, sold_month = acq.strftime("%Y-%m"), sold.strftime("%Y-%m")
        acq_fx = self._rate(acq_month)
        sold_fx = self._rate(sold_month)
        if acq_fx is None and self.exchange_rates:
            raise ValueError(f"No exchange rate provided for {acq_month}")
        if sold_fx is None and self.exchange_rates:
            raise ValueError(f"No exchange rate provided for {sold_month}")
        acq_type = _acq_type(source)
        cbs_cents = round(cost_share * 100)
        qty_int = round(qty * 10000)
        lot = _lot_id(ticker, acq.isoformat(), cbs_cents)
        vest_leg = ParsedTransaction(
            source=self.source,
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type=acq_type,
            date=acq,
            units=qty,
            price_per_unit=round(cost_share, 4),
            forex_rate=acq_fx,
            amount_inr=-(cost_total * acq_fx) if acq_fx else 0.0,
            txn_id=_txn_id(_CLOSED_TXN_PREFIX, "fidelity_closed", ticker, acq.isoformat(),
                           str(cbs_cents), str(qty_int), sold.isoformat()),
            lot_id=lot,
            notes=(f"Fidelity closed lot — {source} vested {acq.isoformat()}, "
                   f"sold {sold.isoformat()}"),
        )
        sell = ParsedTransaction(
            source=self.source,
            asset_name=ticker,
            asset_identifier=ticker,
            asset_type="STOCK_US",
            txn_type="SELL",
            date=sold,
            units=qty,
            price_per_unit=round(proceeds / qty, 4) if qty else 0.0,
            forex_rate=sold_fx,
            amount_inr=(proceeds * sold_fx) if sold_fx else 0.0,
            txn_id=_txn_id(_SOLD_TXN_PREFIX, "fidelity_sold", ticker, acq.isoformat(),
                           sold.isoformat(), str(qty_int)),
            lot_id=lot,
            notes=(f"Fidelity closed lot — sold {sold.isoformat()}, "
                   f"acquired {acq.isoformat()}"),
        )
        if defaulted:
            vest_leg.notes += " [source defaulted to RS]"
        return vest_leg, sell

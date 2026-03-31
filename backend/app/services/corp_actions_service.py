import re
import logging
import requests
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.models.asset import Asset, AssetType
from app.models.transaction import Transaction, TransactionType
from app.repositories.transaction_repo import TransactionRepository

logger = logging.getLogger(__name__)

NSE_BASE = "https://www.nseindia.com"
NSE_CORP_ACTIONS_URL = (
    NSE_BASE + "/api/corporates-corporateActions"
    "?index=equities&symbol={symbol}&from_date={from_dt}&to_date={to_dt}"
)
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
NSE_DATE_FORMAT_PARAM = "%d-%m-%Y"    # for query params: 01-01-2020
NSE_DATE_FORMAT_RESP  = "%d-%b-%Y"    # for response exDate: 09-JAN-2020


def parse_corp_action_subject(subject: str) -> dict | None:
    """Parse NSE corporate action subject string into a structured dict.

    Returns:
        {"kind": "BONUS", "ratio": float}  — new units per existing unit
        {"kind": "SPLIT", "ratio": float}  — new units per old unit (old_fv / new_fv)
        {"kind": "DIVIDEND", "per_share_inr": float}
        None — for unrecognised / unsupported actions (Buyback, Rights, etc.)
    """
    # BONUS: e.g. "Bonus 1:1", "Bonus Issue 2:1", "Bonus 1:2"
    bonus_match = re.search(r"(?i)bonus\b.*?(\d+)\s*:\s*(\d+)", subject)
    if bonus_match:
        new_shares = int(bonus_match.group(1))
        existing_shares = int(bonus_match.group(2))
        return {"kind": "BONUS", "ratio": new_shares / existing_shares}

    # SPLIT: e.g. "Sub-Division / Split From Rs 10/- To Rs 2/-"
    split_match = re.search(
        r"(?i)(?:sub.?division|split).*?from\s+rs\.?\s*([\d.]+).*?to\s+rs\.?\s*([\d.]+)",
        subject,
    )
    if split_match:
        old_fv = float(split_match.group(1))
        new_fv = float(split_match.group(2))
        return {"kind": "SPLIT", "ratio": old_fv / new_fv}

    # DIVIDEND: e.g. "Interim Dividend - Rs 3 Per Share", "Dividend Re. 1 Per Share"
    # Matches both "Rs." (≥₹1) and "Re." (sub-₹1) rupee notations used by NSE.
    div_match = re.search(r"(?i)dividend.*?r[se]\.?\s*([\d.]+)", subject)
    if div_match:
        per_share = float(div_match.group(1))
        return {"kind": "DIVIDEND", "per_share_inr": per_share}

    return None


ADD_TYPES = {"BUY", "SIP", "VEST", "BONUS"}
SUB_TYPES = {"SELL", "REDEMPTION"}


def is_held_on_date(txns: list[Transaction], target_date: date) -> bool:
    """Return True if the asset was held (net positive units) at target_date."""
    net = 0.0
    for t in txns:
        if t.date > target_date:
            continue
        if t.type.value in ADD_TYPES:
            net += t.units or 0.0
        elif t.type.value in SUB_TYPES:
            net -= t.units or 0.0
    return net > 0


def units_held_at_date(txns: list[Transaction], target_date: date) -> float:
    """Return the net units held at (up to and including) target_date. Never negative."""
    net = 0.0
    for t in txns:
        if t.date > target_date:
            continue
        if t.type.value in ADD_TYPES:
            net += t.units or 0.0
        elif t.type.value in SUB_TYPES:
            net -= t.units or 0.0
    return max(0.0, net)


class NSECorpActionFetcher:
    def __init__(self):
        self._session = requests.Session()
        try:
            self._session.get(NSE_BASE, headers=NSE_HEADERS, timeout=10)
        except Exception as e:
            logger.warning("NSE session init failed: %s", e)

    def fetch(self, symbol: str, from_date: date, to_date: date) -> list[dict]:
        """Returns list of raw NSE corporate action dicts. Returns [] on any error."""
        url = NSE_CORP_ACTIONS_URL.format(
            symbol=symbol,
            from_dt=from_date.strftime(NSE_DATE_FORMAT_PARAM),
            to_dt=to_date.strftime(NSE_DATE_FORMAT_PARAM),
        )
        try:
            resp = self._session.get(url, headers=NSE_HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                return []
            return data
        except Exception as e:
            logger.warning("NSE corp actions fetch failed for %s: %s", symbol, e)
            return []

    @staticmethod
    def parse_ex_date(ex_date_str: str) -> date | None:
        """Parse NSE ex_date format '09-JAN-2020' → date(2020, 1, 9). Returns None on failure."""
        try:
            return datetime.strptime(ex_date_str.strip(), NSE_DATE_FORMAT_RESP).date()
        except (ValueError, AttributeError):
            return None


class CorpActionsService:
    def __init__(self, db: Session):
        self.db = db
        self.txn_repo = TransactionRepository(db)
        self.fetcher = NSECorpActionFetcher()

    def process_all_stocks(self) -> dict:
        """Fetch and apply corp actions for ALL active STOCK_IN assets."""
        assets = self.db.query(Asset).filter(
            Asset.asset_type == AssetType.STOCK_IN,
            Asset.is_active == True,
        ).all()
        result = _empty_result()
        for asset in assets:
            ar = self.process_asset(asset)
            for k in result:
                result[k] += ar[k]
        return result

    def process_asset_by_id(self, asset_id: int) -> dict:
        """Fetch and apply corp actions for one asset by ID. Validates type."""
        from app.middleware.error_handler import NotFoundError, ValidationError
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise NotFoundError(f"Asset {asset_id} not found")
        if asset.asset_type != AssetType.STOCK_IN:
            raise ValidationError("Corp actions only apply to STOCK_IN assets")
        return self.process_asset(asset)

    def process_asset(self, asset: Asset) -> dict:
        """Fetch and apply corp actions for one asset. Returns result dict."""
        result = _empty_result()
        isin = asset.identifier
        symbol = asset.name  # NSE uses ticker as symbol

        if not isin and not symbol:
            return result

        txns = self.txn_repo.list_by_asset(asset.id)
        if not txns:
            return result

        # Date range: earliest BUY to today (or latest SELL date if fully exited)
        buy_dates = [t.date for t in txns if t.type.value in {"BUY", "SIP", "VEST"}]
        if not buy_dates:
            return result
        from_date = min(buy_dates)
        to_date = date.today()

        raw_actions = self.fetcher.fetch(symbol, from_date, to_date)

        for action in raw_actions:
            ex_date_str = action.get("exDate") or action.get("ex_date") or ""
            subject = action.get("subject") or action.get("purpose") or ""

            ex_date = self.fetcher.parse_ex_date(ex_date_str)
            if ex_date is None:
                continue
            if not is_held_on_date(txns, ex_date):
                continue

            parsed = parse_corp_action_subject(subject)
            if parsed is None:
                continue

            kind = parsed["kind"]
            if kind == "BONUS":
                self._apply_bonus(asset, isin, txns, ex_date, parsed["ratio"], result)
            elif kind == "SPLIT":
                self._apply_split(asset, isin, txns, ex_date, parsed["ratio"], result)
                # Reload txns so subsequent bonus/dividend in same batch see updated units.
                txns = self.txn_repo.list_by_asset(asset.id)
            elif kind == "DIVIDEND":
                self._apply_dividend(asset, isin, txns, ex_date, parsed["per_share_inr"], result)

        return result

    def _apply_bonus(self, asset, isin, txns, ex_date, ratio, result):
        txn_id = f"corp_bonus_{isin}_{ex_date.isoformat()}"
        if self.txn_repo.get_by_txn_id(txn_id):
            result["bonus_skipped"] += 1
            return

        held = units_held_at_date(txns, ex_date)
        bonus_units = round(held * ratio, 6)
        if bonus_units <= 0:
            return

        self.txn_repo.create(
            txn_id=txn_id,
            asset_id=asset.id,
            type=TransactionType.BONUS,
            date=ex_date,
            units=bonus_units,
            price_per_unit=0.0,
            amount_inr=0,
            charges_inr=0,
            notes=f"Corporate action: Bonus {ratio}:1 (NSE)",
        )
        result["bonus_created"] += 1
        logger.info(
            "BONUS created: %s isin=%s ex_date=%s units=%.4f",
            asset.name, isin, ex_date, bonus_units,
        )

    def _apply_split(self, asset, isin, txns, ex_date, ratio, result):
        marker_id = f"corp_split_{isin}_{ex_date.isoformat()}"
        if self.txn_repo.get_by_txn_id(marker_id):
            result["split_skipped"] += 1
            return

        updated = 0
        # Rescale all buy-side AND sell-side transactions before ex_date so that
        # unit counts remain consistent after the split (e.g. BUY 10 → 50 and
        # SELL 5 → 25 for a 5:1 split).
        for t in txns:
            if t.date >= ex_date:
                continue
            if t.type.value in ("BUY", "SIP", "VEST"):
                t.units = (t.units or 0.0) * ratio
                t.price_per_unit = (
                    (t.price_per_unit or 0.0) / ratio
                    if (t.price_per_unit or 0.0) > 0
                    else 0.0
                )
                updated += 1
            elif t.type.value in ("SELL", "REDEMPTION"):
                t.units = (t.units or 0.0) * ratio
                t.price_per_unit = (
                    (t.price_per_unit or 0.0) / ratio
                    if (t.price_per_unit or 0.0) > 0
                    else 0.0
                )
                updated += 1

        self.txn_repo.create(
            txn_id=marker_id,
            asset_id=asset.id,
            type=TransactionType.SPLIT,
            date=ex_date,
            units=None,
            price_per_unit=None,
            amount_inr=0,
            charges_inr=0,
            notes=(
                f"Corporate action: Split ratio {ratio}:1 (NSE). "
                f"Updated {updated} transactions."
            ),
        )
        self.db.commit()
        result["split_applied"] += 1
        logger.info(
            "SPLIT applied: %s isin=%s ex_date=%s ratio=%.1f updated=%d",
            asset.name, isin, ex_date, ratio, updated,
        )

    def _apply_dividend(self, asset, isin, txns, ex_date, per_share_inr, result):
        txn_id = f"corp_div_{isin}_{ex_date.isoformat()}"
        if self.txn_repo.get_by_txn_id(txn_id):
            result["dividend_skipped"] += 1
            return

        held = units_held_at_date(txns, ex_date)
        if held <= 0:
            return
        total_inr = held * per_share_inr
        amount_paise = round(total_inr * 100)

        self.txn_repo.create(
            txn_id=txn_id,
            asset_id=asset.id,
            type=TransactionType.DIVIDEND,
            date=ex_date,
            units=held,
            price_per_unit=per_share_inr,
            amount_inr=amount_paise,
            charges_inr=0,
            notes=f"Corporate action: Dividend ₹{per_share_inr}/share (auto-imported from NSE)",
        )
        result["dividend_created"] += 1
        logger.info(
            "DIVIDEND created: %s isin=%s ex_date=%s per_share=%.2f total=%.2f",
            asset.name, isin, ex_date, per_share_inr, total_inr,
        )


def _empty_result() -> dict:
    return {
        "bonus_created": 0, "bonus_skipped": 0,
        "split_applied": 0, "split_skipped": 0,
        "dividend_created": 0, "dividend_skipped": 0,
    }
